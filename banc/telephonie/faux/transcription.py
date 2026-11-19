"""Fausse transcription : le protocole WebSocket de Soniox, tel que le fork le parle.

Lu dans pipecat/src/pipecat/services/soniox/stt.py : le client envoie un premier
message JSON de configuration, puis le son de l'appelant en blocs binaires (PCM
16 bits), des messages {"type": "keepalive"} et, pour finir, un message vide. Le
serveur rend des messages {"tokens": [...]} ; un mot provisoire ouvre le tour de
l'appelant, et le mot définitif "<end>" le ferme.

Le faux n'écoute pas les mots : il regarde le niveau du son. Un bloc sonore
ouvre un tour, le premier bloc de silence le ferme, et le texte rendu est celui
du tour dans les réglages. Même son reçu, mêmes messages rendus.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from aiohttp import WSMsgType, web
from journal import Journal
from reglages import ReglagesCourants
from son import niveau

# En dessous de ce niveau moyen (sur 32 768), un bloc est compté comme du
# silence. Le ton de l'appelant du banc est autour de 5 600.
SEUIL_SON = 300.0
MOT_DE_FIN_DE_TOUR = "<end>"


class Signal(Enum):
    DEBUT_DE_PAROLE = "debut_de_parole"
    REPRISE_DE_PAROLE = "reprise_de_parole"
    PREMIER_SILENCE = "premier_silence"


@dataclass
class Ecoute:
    """Ce que le faux sait d'une connexion : ni réseau, ni horloge."""

    frequence_echantillonnage: int = 8000
    tour: int = 0
    en_parole: bool = False
    fin_de_tour_due: bool = False
    octets_recus: int = 0

    def recevoir(self, bloc: bytes) -> Signal | None:
        self.octets_recus += len(bloc)
        sonore = niveau(bloc) >= SEUIL_SON
        if sonore and not self.en_parole:
            self.en_parole = True
            if self.fin_de_tour_due:
                # La parole reprend avant la fin de tour : c'est le même tour.
                self.fin_de_tour_due = False
                return Signal.REPRISE_DE_PAROLE
            self.tour += 1
            return Signal.DEBUT_DE_PAROLE
        if not sonore and self.en_parole:
            self.en_parole = False
            self.fin_de_tour_due = True
            return Signal.PREMIER_SILENCE
        return None

    def fin_de_tour_rendue(self) -> None:
        self.fin_de_tour_due = False

    @property
    def position_ms(self) -> int:
        """Durée de son reçue depuis le début de la connexion."""
        return self.octets_recus * 1000 // (2 * self.frequence_echantillonnage)


def texte_du_tour(paroles: tuple[str, ...], tour: int) -> str:
    return paroles[(tour - 1) % len(paroles)]


def mots(texte: str, *, definitifs: bool, position_ms: int) -> list[dict[str, Any]]:
    """Les mots d'un texte au format de Soniox. Chaque mot après le premier
    porte son espace : le fork recolle les textes sans rien ajouter."""
    return [
        {
            "text": mot if rang == 0 else f" {mot}",
            "start_ms": position_ms,
            "end_ms": position_ms,
            "confidence": 1.0,
            "is_final": definitifs,
            "language": "fr",
        }
        for rang, mot in enumerate(texte.split())
    ]


def message(jetons: list[dict[str, Any]], position_ms: int) -> str:
    return json.dumps(
        {
            "tokens": jetons,
            "final_audio_proc_ms": position_ms,
            "total_audio_proc_ms": position_ms,
        },
        ensure_ascii=False,
    )


class FausseTranscription:
    def __init__(self, reglages: ReglagesCourants, journal: Journal) -> None:
        self._reglages = reglages
        self._journal = journal
        self._connexions = 0

    async def flux(self, requete: web.Request) -> web.WebSocketResponse:
        liaison = web.WebSocketResponse()
        await liaison.prepare(requete)
        self._connexions += 1
        connexion = self._connexions
        ecoute = Ecoute()
        premier_mot: asyncio.Task[None] | None = None
        fin_de_tour: asyncio.Task[None] | None = None
        dernier_son_ns = 0

        def noter(evenement: str, **details: Any) -> None:
            self._journal.noter(
                "transcription", evenement, connexion=connexion, **details
            )

        async def rendre_premier_mot(tour: int) -> None:
            reglages = self._reglages.valeur
            await asyncio.sleep(reglages.delai_premier_mot_ms / 1000)
            texte = texte_du_tour(reglages.paroles, tour)
            jetons = mots(texte, definitifs=False, position_ms=ecoute.position_ms)[:1]
            await liaison.send_str(message(jetons, ecoute.position_ms))
            noter("premier_mot_rendu", tour=tour)

        async def rendre_fin_de_tour(tour: int) -> None:
            reglages = self._reglages.valeur
            await asyncio.sleep(reglages.delai_fin_de_tour_ms / 1000)
            if premier_mot is not None:
                premier_mot.cancel()
            texte = texte_du_tour(reglages.paroles, tour)
            jetons = mots(texte, definitifs=True, position_ms=ecoute.position_ms)
            jetons.append(
                {
                    "text": MOT_DE_FIN_DE_TOUR,
                    "start_ms": ecoute.position_ms,
                    "end_ms": ecoute.position_ms,
                    "confidence": 1.0,
                    "is_final": True,
                }
            )
            ecoute.fin_de_tour_rendue()
            await liaison.send_str(message(jetons, ecoute.position_ms))
            noter("fin_de_tour_rendue", tour=tour, texte=texte)

        noter("connexion_ouverte")
        try:
            async for recu in liaison:
                if recu.type == WSMsgType.BINARY:
                    signal = ecoute.recevoir(recu.data)
                    if ecoute.en_parole:
                        dernier_son_ns = time.time_ns()
                    if signal is Signal.DEBUT_DE_PAROLE:
                        noter("debut_de_parole", tour=ecoute.tour)
                        premier_mot = asyncio.create_task(
                            rendre_premier_mot(ecoute.tour)
                        )
                    elif signal is Signal.REPRISE_DE_PAROLE:
                        if fin_de_tour is not None:
                            fin_de_tour.cancel()
                        noter("reprise_de_parole", tour=ecoute.tour)
                    elif signal is Signal.PREMIER_SILENCE:
                        noter(
                            "premier_silence",
                            tour=ecoute.tour,
                            dernier_son_ns=dernier_son_ns,
                        )
                        fin_de_tour = asyncio.create_task(
                            rendre_fin_de_tour(ecoute.tour)
                        )
                elif recu.type == WSMsgType.TEXT:
                    if recu.data == "":
                        # Fin du son annoncée par le client : Soniox répond « fini ».
                        await liaison.send_str(
                            json.dumps({"tokens": [], "finished": True})
                        )
                        break
                    contenu = json.loads(recu.data)
                    if "sample_rate" in contenu:
                        ecoute.frequence_echantillonnage = int(contenu["sample_rate"])
                        # La clé reçue n'est ni lue ni écrite.
                        noter(
                            "configuration_recue",
                            modele=contenu.get("model"),
                            format=contenu.get("audio_format"),
                            frequence=contenu.get("sample_rate"),
                            fin_de_tour_par_le_fournisseur=contenu.get(
                                "enable_endpoint_detection"
                            ),
                        )
        finally:
            for tache in (premier_mot, fin_de_tour):
                if tache is not None:
                    tache.cancel()
            noter("connexion_fermee", tours=ecoute.tour, son_recu_ms=ecoute.position_ms)
        return liaison
