"""[.mark] Chantier correctifs-apres-banc-commun, lot V : les correctifs officiels de la voix Soniox.

Le Pipecat que Dograh épingle (1.12) a trois défauts de la voix Soniox, corrigés dans Pipecat 1.13.
⛔ Le sous-module n'est jamais modifié (R2) : les correctifs vivent ici, dans un mélange qui se pose
sur ``SonioxTTSService`` (voir ``MarkSonioxTTSService``). Quand le pointeur montera en 1.13, ces
surcharges deviennent sans effet et se retirent avec leur ligne du registre.

| Origine officielle | Défaut vu au banc | Ce que fait ce fichier |
|---|---|---|
| PR #6011 (``1d1fe9b39``), keepalive partagé | ``408 request_timeout`` : la boucle du keepalive s'arrêtait à la première erreur d'envoi et ne repartait jamais | la boucle continue après une erreur d'envoi |
| PR #6008 (``7102e958a``), contextes et flux | ``invalid_stream_state`` / « Stream not found » : un texte partait sur un flux jamais configuré (reconnexion) et les contextes de l'ancienne connexion restaient ouverts | le flux est configuré avant son premier texte ; une nouvelle connexion ferme les contextes ouverts et fait continuer le tour sous un nouvel identifiant ; un crochet qui échoue ne casse plus la lecture |
| ``58d99e98f``, erreurs par code HTTP | toute erreur Soniox était « inconnue » | l'erreur porte la catégorie de son code (``429`` = limite, ``402`` = crédit, ``401`` = clé) |

En plus (limite de 3 flux simultanés du projet Soniox, D22) : la voix de la fabrique des sons peut
**emprunter la connexion** de la voix de l'appel au lieu d'en ouvrir une seconde. Les deux voix se
partagent alors une seule connexion ; chaque flux garde son identifiant et ses messages reviennent à la
voix qui l'a ouvert. Voix de l'appel absente ou non connectée : la fabrique ouvre sa propre connexion,
comme avant.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger
from websockets.protocol import State

from pipecat.frames.frames import ErrorFrame, TTSStoppedFrame
from pipecat.utils.errors import ErrorCategory, classify_http_status_code


def categorie_de_l_erreur_soniox(code: Any) -> ErrorCategory | None:
    """``58d99e98f`` : la catégorie du ``error_code`` d'un message d'erreur Soniox (un code HTTP).

    Rend ``None`` quand le code manque ou n'est pas un nombre : l'erreur reste « inconnue »."""
    if isinstance(code, int) and not isinstance(code, bool):
        return classify_http_status_code(code)
    return None


class _FileDeMessages:
    """Les messages d'un flux emprunté, dans l'ordre. ``None`` = la connexion prêtée est finie."""

    def __init__(self) -> None:
        self.file: asyncio.Queue[str | None] = asyncio.Queue()

    def __aiter__(self) -> AsyncIterator[str]:
        return self._lire()

    async def _lire(self) -> AsyncIterator[str]:
        while True:
            message = await self.file.get()
            if message is None:
                return
            yield message


class ConnexionEmpruntee:
    """La « connexion » d'une voix qui emprunte celle de la voix de l'appel.

    Même forme qu'une connexion websocket pour ce que le connecteur lui demande (``state``, ``send``,
    ``close``, lecture des messages) : l'envoi passe par la connexion prêteuse, la lecture vient de la
    file que la prêteuse alimente (voir ``_FluxDeMessages``)."""

    def __init__(self, preteuse: CorrectifsVoixSonioxMixin, emprunteuse: CorrectifsVoixSonioxMixin) -> None:
        self._preteuse = preteuse
        self._emprunteuse = emprunteuse
        self.messages = _FileDeMessages()

    @property
    def state(self) -> State:
        reelle = self._preteuse._websocket
        return reelle.state if reelle is not None else State.CLOSED

    async def send(self, message: str) -> None:
        reelle = self._preteuse._websocket
        if reelle is None:
            raise RuntimeError("connexion de la voix de l'appel fermée")
        await reelle.send(message)

    async def close(self) -> None:
        self._preteuse._rendre_la_connexion(self._emprunteuse)

    def __aiter__(self) -> AsyncIterator[str]:
        return self.messages.__aiter__()


class _FluxDeMessages:
    """Ce que ``_receive_messages`` du connecteur lit : la connexion, avec deux services en plus.

    · les messages d'un flux emprunté sont rendus à la voix qui l'a ouvert, et ne vont pas à celle-ci ;
    · avant un message d'erreur, le code est noté pour que ``push_error`` lui donne sa catégorie."""

    def __init__(self, service: CorrectifsVoixSonioxMixin, source: Any) -> None:
        self._service = service
        self._source = source

    @property
    def state(self) -> State:
        return self._source.state

    async def send(self, message: str) -> None:
        await self._source.send(message)

    async def close(self) -> None:
        await self._source.close()

    def __aiter__(self) -> AsyncIterator[str]:
        return self._lire()

    async def _lire(self) -> AsyncIterator[str]:
        async for message in self._source:
            if not self._service._aiguiller(message):
                yield message


class CorrectifsVoixSonioxMixin:
    """Les correctifs de la voix Soniox (voir l'en-tête du fichier). Se pose AVANT ``SonioxTTSService``."""

    # --- état ajouté (créé à la demande : le constructeur du connecteur n'est pas touché) -------------

    @property
    def _flux_empruntes(self) -> dict[str, ConnexionEmpruntee]:
        return self.__dict__.setdefault("_mark_flux_empruntes", {})

    @property
    def _preteuse(self) -> CorrectifsVoixSonioxMixin | None:
        return self.__dict__.get("_mark_preteuse")

    # --- 58d99e98f : erreurs classées par code HTTP -------------------------------------------------

    def _aiguiller(self, message: str) -> bool:
        """Appelé pour chaque message reçu. Rend ``True`` si le message a été remis à une autre voix."""
        if '"error_code"' in message:
            try:
                self.__dict__["_mark_code_d_erreur"] = json.loads(message).get("error_code")
            except (ValueError, AttributeError):
                self.__dict__["_mark_code_d_erreur"] = None
        flux = self._flux_empruntes
        if flux and '"stream_id"' in message:
            try:
                stream_id = json.loads(message).get("stream_id")
            except (ValueError, AttributeError):
                return False
            liaison = flux.get(stream_id) if isinstance(stream_id, str) else None
            if liaison is not None:
                liaison.messages.file.put_nowait(message)
                self.__dict__.pop("_mark_code_d_erreur", None)
                return True
        return False

    async def push_error(self, error_msg: str, exception=None, fatal: bool = False, category=None, **kwargs):
        """La catégorie du code d'erreur Soniox qui vient d'être lu, quand l'appelant n'en donne pas."""
        code = self.__dict__.pop("_mark_code_d_erreur", None)
        if category is None and exception is None:
            category = categorie_de_l_erreur_soniox(code)
        return await super().push_error(
            error_msg=error_msg, exception=exception, fatal=fatal, category=category, **kwargs
        )

    def _get_websocket(self):
        """Ce que le connecteur lit et écrit : la connexion, avec l'aiguillage des messages."""
        if self._websocket:
            return _FluxDeMessages(self, self._websocket)
        raise Exception("Websocket not connected")

    # --- PR #6011 : le keepalive ne s'arrête plus à la première erreur -----------------------------

    async def _keepalive_task_handler(self):
        """Le message « keep_alive » toutes les ``KEEPALIVE_INTERVAL_SECONDS`` secondes, sans fin.

        Le connecteur 1.12 sortait de la boucle à la première erreur d'envoi, et la tâche, finie mais
        jamais remplacée, laissait la connexion s'endormir (``408 request_timeout``). Ici un envoi qui
        échoue est journalisé et la boucle continue : la reconnexion reprend sur la même tâche. Une voix
        qui emprunte la connexion de l'autre n'envoie rien (la prêteuse garde la connexion en vie)."""
        from pipecat.services.soniox.tts import KEEPALIVE_INTERVAL_SECONDS

        while True:
            await asyncio.sleep(KEEPALIVE_INTERVAL_SECONDS)
            try:
                if isinstance(self._websocket, ConnexionEmpruntee):
                    continue
                if self._websocket and self._websocket.state is State.OPEN:
                    await self._websocket.send(json.dumps({"keep_alive": True}))
                    logger.trace(f"{self}: sent Soniox keepalive")
            except Exception as e:  # noqa: BLE001 -- la boucle ne doit jamais s'arrêter
                logger.warning(f"{self} keepalive error: {e}")

    # --- PR #6008 : flux configuré avant son premier texte ----------------------------------------

    async def run_tts(self, text: str, context_id: str):
        """Le flux est configuré avant son premier texte, même quand la connexion est neuve.

        Un identifiant de flux vu pour la première fois sur une connexion (après une reconnexion) sans
        configuration était refusé par Soniox (``invalid_stream_state``). ``_send_config`` ne renvoie
        rien si le flux est déjà configuré : un flux ouvert à l'avance n'est pas touché."""
        try:
            if not self._websocket or self._websocket.state is State.CLOSED:
                await self._connect()
            try:
                await self._send_config(context_id)
            except Exception as e:  # noqa: BLE001 -- même issue qu'un envoi de texte qui échoue
                yield ErrorFrame(error=f"Unknown error occurred: {e}", exception=e)
                yield TTSStoppedFrame(context_id=context_id)
                await self._disconnect()
                await self._connect()
                return
        except Exception as e:  # noqa: BLE001
            yield ErrorFrame(error=f"Unknown error occurred: {e}", exception=e)
            return
        async for frame in super().run_tts(text, context_id):
            yield frame

    async def _websocket_connect(self, uri: str, **kwargs):
        """PR #6008 : une nouvelle connexion ferme les contextes ouverts de l'ancienne.

        Soniox garde l'état des flux par connexion : l'audio dû sur l'ancienne n'arrive jamais. Chaque
        contexte ouvert est fermé (l'audio déjà reçu se joue) et un tour en cours continue sous un nouvel
        identifiant, donc sur un flux neuf. La première connexion n'a rien à fermer."""
        for context_id in self.get_audio_contexts():
            await self.remove_audio_context(context_id)
        if self._turn_context_id:
            self._turn_context_id = None
            self._turn_context_id = self.create_context_id()
        return await super()._websocket_connect(uri, **kwargs)

    async def on_audio_context_interrupted(self, context_id: str):
        """PR #6008 : un crochet qui échoue ne saute plus le redémarrage de la lecture."""
        try:
            await super().on_audio_context_interrupted(context_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{self} on_audio_context_interrupted failed for {context_id}: {e}")

    async def on_audio_context_completed(self, context_id: str):
        """PR #6008 : un crochet qui échoue ne met plus fin à la lecture de l'appel."""
        try:
            await super().on_audio_context_completed(context_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{self} on_audio_context_completed failed for {context_id}: {e}")

    # --- Fabrique des sons : une seule connexion par appel -----------------------------------------

    def partager_la_connexion_de(self, voix_de_l_appel: Any) -> bool:
        """Emprunte la connexion de la voix de l'appel pour ses flux. Rend ``True`` si c'est fait.

        Rien n'est emprunté si l'autre voix n'est pas une voix Soniox de chez nous, si c'est la même, ou
        si sa connexion n'est pas ouverte : la voix ouvrira alors la sienne, comme avant."""
        if not isinstance(voix_de_l_appel, CorrectifsVoixSonioxMixin) or voix_de_l_appel is self:
            return False
        if voix_de_l_appel._preteuse is not None:
            return False
        reelle = voix_de_l_appel._websocket
        if reelle is None or reelle.state is not State.OPEN:
            return False
        self.__dict__["_mark_preteuse"] = voix_de_l_appel
        return True

    def _connexion_pretee(self) -> ConnexionEmpruntee | None:
        """La connexion prêtée si l'on emprunte et que la prêteuse est ouverte, sinon ``None``."""
        preteuse = self._preteuse
        if preteuse is None:
            return None
        reelle = preteuse._websocket
        if reelle is None or reelle.state is not State.OPEN:
            return None
        return ConnexionEmpruntee(preteuse, self)

    async def _connect_websocket(self):
        if self._preteuse is not None:
            if isinstance(self._websocket, ConnexionEmpruntee) and self._websocket.state is State.OPEN:
                return
            liaison = self._connexion_pretee()
            if liaison is not None:
                self._websocket = liaison
                self._preteuse._flux_a_rendre.add(self)
                logger.debug(f"{self}: connexion de la voix de l'appel empruntée")
                await self._call_event_handler("on_connected")
                return
            # La prêteuse n'est plus ouverte : cette voix ouvre la sienne, comme avant.
            self.__dict__.pop("_mark_preteuse", None)
        await super()._connect_websocket()

    @property
    def _flux_a_rendre(self) -> set:
        return self.__dict__.setdefault("_mark_emprunteuses", set())

    async def _send_config(self, context_id: str):
        """Un flux ouvert sur une connexion empruntée est inscrit chez la prêteuse avant son premier envoi."""
        liaison = self._websocket
        if isinstance(liaison, ConnexionEmpruntee) and context_id not in self._configured_contexts:
            liaison._preteuse._flux_empruntes[context_id] = liaison
        await super()._send_config(context_id)

    def _rendre_la_connexion(self, emprunteuse: CorrectifsVoixSonioxMixin) -> None:
        """Appelé à la fermeture d'une connexion empruntée : ses flux ne reçoivent plus rien."""
        for stream_id, liaison in list(self._flux_empruntes.items()):
            if liaison._emprunteuse is emprunteuse:
                del self._flux_empruntes[stream_id]
        self._flux_a_rendre.discard(emprunteuse)

    async def _disconnect_websocket(self):
        """Quand la connexion réelle se ferme, les voix qui l'empruntaient sont prévenues (fin des messages)."""
        for emprunteuse in list(self._flux_a_rendre):
            for liaison in {id(l): l for l in self._flux_empruntes.values() if l._emprunteuse is emprunteuse}.values():
                liaison.messages.file.put_nowait(None)
        self._flux_empruntes.clear()
        self._flux_a_rendre.clear()
        await super()._disconnect_websocket()
