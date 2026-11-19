"""Sonde du banc de téléphonie : que fait Asterisk de la commande de vidage ?

Asterisk (chan_websocket) garde en file le son qu'on lui envoie et le joue au
rythme du téléphone. Quand l'appelant coupe la parole, le son déjà en file
continue d'être joué, sauf si on demande à Asterisk de vider sa file.

La sonde tient la place du fork pour un appel de mesure, sans agent ni
fournisseur :

1. elle prend l'appel par ARI et demande le canal média avec les mêmes
   paramètres que le fork (api/services/telephony/ari_manager.py:841-855) ;
2. Asterisk ouvre le flux audio vers elle ;
3. elle envoie un son continu, puis s'arrête à l'instant T0 et envoie, ou non,
   une commande ;
4. elle écrit T0 et tout ce qu'Asterisk lui a répondu dans un fichier de mesures.

L'instant où le son cesse côté téléphone est relevé à part, sur les paquets
reçus par le simulateur SIPp (analyser.py).
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

import aiohttp
from aiohttp import web

journal = logging.getLogger("sonde")

ADRESSE_ARI = os.environ.get("BANC_ARI_ADRESSE", "http://asterisk:8088")
UTILISATEUR_ARI = os.environ["BANC_ARI_UTILISATEUR"]
MOT_DE_PASSE_ARI = os.environ["BANC_ARI_MOT_DE_PASSE"]
APPLICATION = "sonde"
CLIENT_WEBSOCKET = "sonde"  # section de websocket_client.conf
PORT_ECOUTE = 8090
FICHIER_MESURES = Path(os.environ.get("BANC_FICHIER_MESURES", "/resultats/sonde.jsonl"))

FREQUENCE_ECHANTILLONNAGE = 8000
# Le transport de Pipecat envoie des blocs de 40 ms, un toutes les 40 ms
# (pipecat/src/pipecat/transports/websocket/fastapi.py:468 et :616-625).
DUREE_BLOC_S = 0.040
OCTETS_PAR_BLOC = int(
    FREQUENCE_ECHANTILLONNAGE * DUREE_BLOC_S
)  # ulaw : 1 octet par mesure

DUREE_SON_CADENCE_S = 3.0
# Mode continu : un flux qui ne s'arrête pas, comme celui du fork (le mixeur de
# sortie envoie du silence entre deux phrases de l'agent), ponctué de coupures.
ATTENTE_AVANT_COUPURES_S = 2.0
NOMBRE_DE_COUPURES = 10
ECART_ENTRE_COUPURES_S = 1.0
DUREE_SON_RAFALE_S = 5.0
ATTENTE_AVANT_T0_RAFALE_S = 1.0
ATTENTE_APRES_PONT_S = 0.5
ECOUTE_APRES_T0_S = 6.0


class Mode(str, Enum):
    """Comment le son est envoyé à Asterisk."""

    CADENCE = "cadence"  # au rythme réel, comme le fait le fork
    RAFALE = "rafale"  # tout d'un coup : la file d'Asterisk se remplit
    CONTINU = "continu"  # flux ininterrompu avec plusieurs coupures de parole


class FormatControle(str, Enum):
    """Format des messages de contrôle demandé à Asterisk pour l'appel."""

    DEFAUT = "defaut"  # rien de demandé : chan_websocket.conf décide (texte brut)
    JSON = "json"  # demandé par f(json) dans transport_data
    TEXTE = "texte"  # demandé par f(plain-text) dans transport_data


@dataclass(frozen=True)
class Variante:
    """Une mesure : comment on envoie, et ce qu'on dit à T0."""

    mode: Mode
    commande: str | None
    format_controle: FormatControle = FormatControle.DEFAUT


COMMANDE_JSON = json.dumps({"command": "FLUSH_MEDIA"}, separators=(",", ":"))

# L'extension appelée par SIPp choisit la variante.
VARIANTES: dict[str, Variante] = {
    # Au rythme réel : la question « le lot 1 s'entend-il ? »
    "9100": Variante(Mode.CADENCE, None),
    "9101": Variante(Mode.CADENCE, "FLUSH_MEDIA"),
    # En rafale : la question « quel nom et quel format Asterisk accepte-t-il ? »
    "9110": Variante(Mode.RAFALE, None),
    "9111": Variante(Mode.RAFALE, "FLUSH_MEDIA"),
    "9112": Variante(Mode.RAFALE, "MEDIA_FLUSH"),
    "9113": Variante(Mode.RAFALE, COMMANDE_JSON),
    "9114": Variante(Mode.RAFALE, COMMANDE_JSON, FormatControle.JSON),
    "9115": Variante(Mode.RAFALE, "FLUSH_MEDIA", FormatControle.JSON),
    # Le format imposé par l'appel l'emporte-t-il sur le réglage d'Asterisk ?
    "9116": Variante(Mode.RAFALE, "FLUSH_MEDIA", FormatControle.TEXTE),
    # En continu : la question « la file d'Asterisk grossit-elle à chaque coupure ? »
    "9120": Variante(Mode.CONTINU, None),
    "9121": Variante(Mode.CONTINU, "FLUSH_MEDIA"),
}


@dataclass
class Appel:
    """Ce que la sonde sait d'un appel en cours."""

    canal_appelant: str
    extension: str
    mesure: str
    canal_media: str
    pont: str = ""
    pont_pret: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass
class Releve:
    """Une ligne du fichier de mesures."""

    mesure: str
    extension: str
    mode: str
    commande: str | None
    format_controle: str
    parametres_recus: dict[str, str]
    t_debut_son_ns: int = 0
    t_fin_envoi_ns: int = 0
    t0_ns: int = 0
    octets_envoyes: int = 0
    octets_recus: int = 0
    messages_recus: list[dict[str, object]] = field(default_factory=list)
    erreur: str = ""


def encoder_ulaw(echantillon: int) -> int:
    """Encode une mesure de 16 bits signée en G.711 loi mu."""
    biais, plafond = 0x84, 32635
    signe = 0x80 if echantillon < 0 else 0x00
    valeur = min(abs(echantillon), plafond) + biais
    exposant = 7
    masque = 0x4000
    while exposant > 0 and not valeur & masque:
        exposant -= 1
        masque >>= 1
    mantisse = (valeur >> (exposant + 3)) & 0x0F
    return ~(signe | (exposant << 4) | mantisse) & 0xFF


def fabriquer_ton(
    duree_s: float, frequence_hz: float = 440.0, amplitude: int = 8000
) -> bytes:
    """Un son pur, facile à distinguer du silence dans les paquets reçus."""
    nombre = int(duree_s * FREQUENCE_ECHANTILLONNAGE)
    pas = 2.0 * math.pi * frequence_hz / FREQUENCE_ECHANTILLONNAGE
    return bytes(
        encoder_ulaw(int(amplitude * math.sin(pas * i))) for i in range(nombre)
    )


def decouper(son: bytes) -> list[bytes]:
    return [son[i : i + OCTETS_PAR_BLOC] for i in range(0, len(son), OCTETS_PAR_BLOC)]


def ajouter_ligne(fichier: Path, ligne: str) -> None:
    fichier.parent.mkdir(parents=True, exist_ok=True)
    with fichier.open("a", encoding="utf-8") as sortie:
        sortie.write(ligne)


class Sonde:
    def __init__(self) -> None:
        self._appels: dict[str, Appel] = {}  # par canal appelant
        self._par_canal_media: dict[str, Appel] = {}
        self._session: aiohttp.ClientSession | None = None
        self._ecriture = asyncio.Lock()

    # ------------------------------------------------------------------ ARI

    async def _ari(self, methode: str, chemin: str, **parametres: str) -> dict:
        assert self._session is not None
        async with self._session.request(
            methode, f"{ADRESSE_ARI}/ari{chemin}", params=parametres
        ) as reponse:
            texte = await reponse.text()
            if reponse.status not in (200, 201, 204):
                journal.warning(
                    "ARI %s %s -> %s : %s", methode, chemin, reponse.status, texte
                )
                return {}
            return json.loads(texte) if texte else {}

    async def ecouter_ari(self) -> None:
        """Reste connectée aux événements d'Asterisk, et se reconnecte s'il redémarre."""
        adresse = ADRESSE_ARI.replace("http", "ws", 1) + "/ari/events"
        while True:
            try:
                assert self._session is not None
                # L'identité passe par l'en-tête de la session, jamais par
                # l'adresse : une adresse finit dans les journaux.
                async with self._session.ws_connect(
                    adresse, params={"app": APPLICATION}
                ) as flux:
                    journal.info(
                        "Connectée aux événements ARI, application %s", APPLICATION
                    )
                    async for message in flux:
                        if message.type is aiohttp.WSMsgType.TEXT:
                            await self._traiter_evenement(json.loads(message.data))
            except (aiohttp.ClientError, OSError) as erreur:
                journal.info(
                    "ARI injoignable (%s), nouvel essai dans 2 s",
                    type(erreur).__name__,
                )
            await asyncio.sleep(2)

    async def _traiter_evenement(self, evenement: dict) -> None:
        nature = evenement.get("type")
        canal = evenement.get("channel", {})
        identifiant = canal.get("id", "")

        if nature == "StasisStart":
            if identifiant in self._par_canal_media:
                await self._relier(self._par_canal_media[identifiant])
            elif canal.get("state") == "Ring":
                arguments = evenement.get("args", [])
                extension = arguments[0] if arguments else ""
                mesure = (
                    arguments[1] if len(arguments) > 1 and arguments[1] else "sans-nom"
                )
                await self._prendre_appel(identifiant, extension, mesure)
        elif nature in ("StasisEnd", "ChannelDestroyed"):
            appel = self._appels.pop(identifiant, None)
            if appel:
                await self._liberer(appel)

    async def _prendre_appel(
        self, canal_appelant: str, extension: str, mesure: str
    ) -> None:
        variante = VARIANTES.get(extension)
        if variante is None:
            journal.warning("Extension %s sans variante : appel raccroché", extension)
            await self._ari("DELETE", f"/channels/{canal_appelant}")
            return

        appel = Appel(
            canal_appelant=canal_appelant,
            extension=extension,
            mesure=mesure,
            canal_media=f"sonde-media-{uuid.uuid4().hex[:12]}",
        )
        self._appels[canal_appelant] = appel
        self._par_canal_media[appel.canal_media] = appel

        await self._ari("POST", f"/channels/{canal_appelant}/answer")

        # v(...) : paramètres ajoutés par Asterisk à l'adresse du flux audio,
        # exactement comme le fait le fork pour ses trois identifiants.
        donnees = f"v(extension={extension},appel={canal_appelant},mesure={mesure})"
        if variante.format_controle is FormatControle.JSON:
            donnees = "f(json)" + donnees
        elif variante.format_controle is FormatControle.TEXTE:
            donnees = "f(plain-text)" + donnees
        await self._ari(
            "POST",
            "/channels/externalMedia",
            app=APPLICATION,
            external_host=CLIENT_WEBSOCKET,
            format="ulaw",
            transport="websocket",
            encapsulation="none",
            connection_type="client",
            direction="both",
            transport_data=donnees,
            channelId=appel.canal_media,
        )

    async def _relier(self, appel: Appel) -> None:
        """Pont de mixage entre l'appelant et le canal média, comme le fork."""
        pont = await self._ari(
            "POST", "/bridges", type="mixing", name=f"sonde-{appel.canal_appelant}"
        )
        appel.pont = pont.get("id", "")
        if not appel.pont:
            return
        await self._ari(
            "POST",
            f"/bridges/{appel.pont}/addChannel",
            channel=f"{appel.canal_appelant},{appel.canal_media}",
        )
        appel.pont_pret.set()

    async def _liberer(self, appel: Appel) -> None:
        self._par_canal_media.pop(appel.canal_media, None)
        await self._ari("DELETE", f"/channels/{appel.canal_media}")
        if appel.pont:
            await self._ari("DELETE", f"/bridges/{appel.pont}")

    # ----------------------------------------------------------- flux audio

    async def recevoir_flux(self, requete: web.Request) -> web.WebSocketResponse:
        """Le flux audio qu'Asterisk ouvre vers la sonde pour un appel."""
        parametres = dict(requete.query)
        flux = web.WebSocketResponse(protocols=("media",))
        await flux.prepare(requete)

        extension = parametres.get("extension", "")
        variante = VARIANTES.get(extension)
        appel = self._appels.get(parametres.get("appel", ""))
        releve = Releve(
            mesure=parametres.get("mesure", "sans-nom"),
            extension=extension,
            mode=variante.mode.value if variante else "",
            commande=variante.commande if variante else None,
            format_controle=variante.format_controle.value if variante else "",
            parametres_recus=parametres,
        )
        debut_annonce = asyncio.Event()
        lecture = asyncio.create_task(self._lire(flux, releve, debut_annonce))

        try:
            if variante is None or appel is None:
                releve.erreur = (
                    "paramètres v(...) absents ou inconnus dans l'adresse du flux"
                )
            else:
                await asyncio.wait_for(debut_annonce.wait(), timeout=5)
                await asyncio.wait_for(appel.pont_pret.wait(), timeout=5)
                await asyncio.sleep(ATTENTE_APRES_PONT_S)
                await self._jouer(flux, variante, releve)
                await asyncio.sleep(ECOUTE_APRES_T0_S)
        except TimeoutError:
            releve.erreur = "MEDIA_START ou pont non reçu en 5 s"
        except ConnectionError as erreur:
            releve.erreur = f"flux fermé pendant la mesure : {erreur}"
        finally:
            await self._ecrire(releve)
            lecture.cancel()
        return flux

    async def _lire(
        self, flux: web.WebSocketResponse, releve: Releve, debut_annonce: asyncio.Event
    ) -> None:
        async for message in flux:
            if message.type is aiohttp.WSMsgType.TEXT:
                releve.messages_recus.append(
                    {"t_ns": time.time_ns(), "texte": message.data}
                )
                if "MEDIA_START" in message.data:
                    debut_annonce.set()
            elif message.type is aiohttp.WSMsgType.BINARY:
                releve.octets_recus += len(message.data)

    async def _jouer(
        self, flux: web.WebSocketResponse, variante: Variante, releve: Releve
    ) -> None:
        if variante.mode is Mode.CONTINU:
            await self._jouer_en_continu(flux, variante, releve)
            return
        if variante.mode is Mode.CADENCE:
            blocs = decouper(fabriquer_ton(DUREE_SON_CADENCE_S))
            releve.t_debut_son_ns = time.time_ns()
            await self._envoyer_au_rythme_reel(flux, blocs)
        else:
            blocs = decouper(fabriquer_ton(DUREE_SON_RAFALE_S))
            releve.t_debut_son_ns = time.time_ns()
            for bloc in blocs:
                await flux.send_bytes(bloc)
        releve.octets_envoyes = sum(len(bloc) for bloc in blocs)
        releve.t_fin_envoi_ns = time.time_ns()

        if variante.mode is Mode.RAFALE:
            await asyncio.sleep(ATTENTE_AVANT_T0_RAFALE_S)

        # T0 : l'instant de la coupure. Plus aucun son ne part après lui.
        releve.t0_ns = time.time_ns()
        if variante.commande is not None:
            await flux.send_str(variante.commande)

    async def _jouer_en_continu(
        self, flux: web.WebSocketResponse, variante: Variante, releve: Releve
    ) -> None:
        """Un flux continu ponctué de coupures de parole, comme dans le fork.

        Le fork ne cesse jamais d'envoyer : son mixeur de sortie comble les
        silences de l'agent (pipecat/src/pipecat/transports/base_output.py:920-952).
        À chaque coupure, le transport envoie ce que rend le sérialiseur puis
        remet son horloge à zéro (pipecat/.../websocket/fastapi.py:526-532), ce
        qui fait partir le bloc suivant sans attendre.

        Après chaque coupure, la sonde demande à Asterisk la longueur de sa
        file (GET_STATUS) : la réponse est dans les messages reçus.
        """
        horloge = {"prochain_envoi": 0.0}
        duree = (
            ATTENTE_AVANT_COUPURES_S + NOMBRE_DE_COUPURES * ECART_ENTRE_COUPURES_S + 1.0
        )
        blocs = decouper(fabriquer_ton(duree))
        releve.t_debut_son_ns = time.time_ns()

        async def envoyer() -> None:
            for bloc in blocs:
                await flux.send_bytes(bloc)
                releve.octets_envoyes += len(bloc)
                attente = max(0.0, horloge["prochain_envoi"] - time.monotonic())
                await asyncio.sleep(attente)
                if attente == 0:
                    horloge["prochain_envoi"] = time.monotonic() + DUREE_BLOC_S
                else:
                    horloge["prochain_envoi"] += DUREE_BLOC_S

        envoi = asyncio.create_task(envoyer())
        try:
            await asyncio.sleep(ATTENTE_AVANT_COUPURES_S)
            await flux.send_str("GET_STATUS")
            for _ in range(NOMBRE_DE_COUPURES):
                await asyncio.sleep(ECART_ENTRE_COUPURES_S / 2)
                if variante.commande is not None:
                    await flux.send_str(variante.commande)
                horloge["prochain_envoi"] = 0.0
                await asyncio.sleep(ECART_ENTRE_COUPURES_S / 2)
                await flux.send_str("GET_STATUS")
        finally:
            envoi.cancel()
        releve.t_fin_envoi_ns = time.time_ns()
        # T0 : le flux s'arrête, sans commande. Ce qui reste dans la file
        # d'Asterisk est ce que l'appelant entend encore.
        releve.t0_ns = time.time_ns()

    @staticmethod
    async def _envoyer_au_rythme_reel(
        flux: web.WebSocketResponse, blocs: list[bytes]
    ) -> None:
        """Même horloge que FastAPIWebsocketOutputTransport._write_audio_sleep."""
        prochain_envoi = 0.0
        for bloc in blocs:
            await flux.send_bytes(bloc)
            attente = max(0.0, prochain_envoi - time.monotonic())
            await asyncio.sleep(attente)
            if attente == 0:
                prochain_envoi = time.monotonic() + DUREE_BLOC_S
            else:
                prochain_envoi += DUREE_BLOC_S

    async def _ecrire(self, releve: Releve) -> None:
        ligne = json.dumps(asdict(releve), ensure_ascii=False) + "\n"
        async with self._ecriture:
            await asyncio.to_thread(ajouter_ligne, FICHIER_MESURES, ligne)
        journal.info(
            "Mesure %s (%s) écrite, %d message(s) reçu(s) %s",
            releve.mesure,
            releve.extension,
            len(releve.messages_recus),
            f", erreur : {releve.erreur}" if releve.erreur else "",
        )

    # ---------------------------------------------------------------- cycle

    async def demarrer(self, application: web.Application) -> None:
        self._session = aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(UTILISATEUR_ARI, MOT_DE_PASSE_ARI)
        )
        application["ecoute_ari"] = asyncio.create_task(self.ecouter_ari())

    async def arreter(self, application: web.Application) -> None:
        application["ecoute_ari"].cancel()
        if self._session:
            await self._session.close()


def creer_application() -> web.Application:
    sonde = Sonde()
    application = web.Application()
    application.router.add_get("/media", sonde.recevoir_flux)
    application.on_startup.append(sonde.demarrer)
    application.on_cleanup.append(sonde.arreter)
    return application


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    web.run_app(creer_application(), host="0.0.0.0", port=PORT_ECOUTE, print=None)
