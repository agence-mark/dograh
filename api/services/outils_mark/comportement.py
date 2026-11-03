"""[.mark] U3 sexies point 3 : le comportement commun aux types qui appellent l'extérieur.

Phrase avant l'outil (Auto, Toujours, Jamais ; texte ou enregistrement), mode d'exécution (immédiat, après la phrase,
en arrière-plan pour un outil qui lit), interruption par l'appelant, son pendant l'outil, délai, seuil de patience et
phrase d'attente, phrase de repli. Les valeurs par défaut gardent le comportement d'avant.

Le son pendant l'outil est un enregistrement joué UNE fois au-delà du seuil de patience (le mélangeur audio du fork ne
sait pas boucler un son par outil).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

SEUIL_AUTO_S = 0.8  # « Auto » : la phrase n'est dite que si l'outil n'a pas fini à ce seuil
MODES_PHRASE = ("auto", "toujours", "jamais")


def mode_de_la_phrase(config: dict[str, Any]) -> str:
    """``auto``, ``toujours`` ou ``jamais``. Sans réglage : ``toujours`` si une phrase est écrite (comme avant), sinon ``jamais``."""
    mode = config.get("phrase_avant_mode")
    if mode in MODES_PHRASE:
        return mode
    return "toujours" if a_une_phrase(config) else "jamais"


def a_une_phrase(config: dict[str, Any]) -> bool:
    if config.get("customMessageType") == "audio":
        return bool(config.get("customMessageRecordingId"))
    return bool(str(config.get("customMessage") or "").strip())


async def dire_la_phrase(moteur: Any, config: dict[str, Any], *, attendre: bool) -> bool:
    """Dit la phrase écrite (texte ou enregistrement). ``attendre`` : rend la main quand elle est finie. ⛔ Ne lève jamais."""
    try:
        muet = not bool(config.get("interruption_appelant"))
        if config.get("customMessageType") == "audio":
            pk = config.get("customMessageRecordingId")
            if not pk or not getattr(moteur, "_fetch_recording_audio", None):
                return False
            lecture = await moteur.queue_speech(recording_pk=int(pk), mute_user=muet)
        else:
            texte = str(config.get("customMessage") or "").strip()
            if not texte:
                return False
            lecture = await moteur.queue_speech(texte, mute_user=muet)
        if attendre and hasattr(lecture, "wait"):
            await lecture.wait()
        return True
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[outils] phrase avant l'outil non dite : {erreur!r}")
        return False


class Attente:
    """Phrase d'attente et son pendant l'outil : dits une fois, par le code, seulement si l'outil n'a pas fini au seuil."""

    def __init__(self, moteur: Any, config: dict[str, Any]):
        self._moteur = moteur
        self._phrase = str(config.get("phrase_attente") or "").strip()
        self._son = config.get("son_pendant_enregistrement_id")
        self._muet = not bool(config.get("interruption_appelant"))
        try:
            self._seuil_s = max(0, min(15000, int(config.get("seuil_patience_ms", 1200)))) / 1000
        except (TypeError, ValueError):
            self._seuil_s = 1.2
        self._tache: asyncio.Task | None = None
        self.dite = False

    def demarrer(self) -> None:
        if self._phrase or self._son:
            self._tache = asyncio.get_running_loop().create_task(self._attendre())

    async def _attendre(self) -> None:
        await asyncio.sleep(self._seuil_s)
        self.dite = True
        try:
            if self._phrase:
                await self._moteur.queue_text_message(self._phrase, mute_user=self._muet)
            if self._son:
                await self._moteur.queue_speech(recording_pk=int(self._son), mute_user=self._muet)
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[outils] attente non dite : {erreur!r}")

    def arreter(self) -> None:
        if self._tache is not None and not self._tache.done():
            self._tache.cancel()


def est_un_echec(resultat: Any) -> bool:
    return isinstance(resultat, dict) and (
        resultat.get("status") == "error" or resultat.get("error") not in (None, "", False)
    )


async def executer_avec_comportement(
    moteur: Any,
    config: dict[str, Any],
    nom: str,
    appel: Callable[[], Awaitable[Any]],
    *,
    fiche: dict[str, Any] | None = None,
) -> Any:
    """Lance ``appel`` selon le comportement de l'outil et rend ce que le modèle reçoit.

    * ``arriere_plan`` : rend tout de suite ``{"status": "en_cours"}``, et le résultat arrive dans la fiche sous
      ``resultat_<outil>`` ; seulement pour un outil qui lit (le schéma le refuse sinon, ici aussi).
    * phrase avant : ``toujours`` (dite d'abord ; ``apres_la_phrase`` attend sa fin), ``auto`` (seulement si l'outil
      dépasse ``SEUIL_AUTO_S``), ``jamais``.
    * patience : phrase d'attente et son, au seuil réglé.
    * repli : si l'outil échoue, la phrase de repli est dite et signalée au modèle (``said_to_caller``)."""
    mode = mode_de_la_phrase(config)
    apres = config.get("mode_execution") == "apres_la_phrase"

    if config.get("mode_execution") == "arriere_plan":
        if mode == "toujours":
            await dire_la_phrase(moteur, config, attendre=False)

        async def en_fond() -> None:
            try:
                resultat = await appel()
            except Exception as erreur:  # noqa: BLE001
                resultat = {"status": "error", "error": type(erreur).__name__}
            if isinstance(fiche, dict):
                fiche[f"resultat_{nom}"] = resultat

        tache = asyncio.get_running_loop().create_task(en_fond())
        _TACHES.add(tache)
        tache.add_done_callback(_TACHES.discard)
        return {"status": "en_cours", "message": "The tool runs in the background; its result will be in the call record."}

    if mode == "toujours":
        await dire_la_phrase(moteur, config, attendre=apres)

    attente = Attente(moteur, config)
    attente.demarrer()
    try:
        if mode == "auto":
            tache = asyncio.ensure_future(appel())
            fait, _ = await asyncio.wait({tache}, timeout=SEUIL_AUTO_S)
            if not fait:
                await dire_la_phrase(moteur, config, attendre=apres)
            resultat = await tache
        else:
            resultat = await appel()
    finally:
        attente.arreter()

    repli = str(config.get("phrase_repli") or "").strip()
    if repli and est_un_echec(resultat):
        try:
            await moteur.queue_text_message(repli, mute_user=not bool(config.get("interruption_appelant")))
            resultat = {**resultat, "said_to_caller": repli}
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[outils] phrase de repli non dite : {erreur!r}")
    return resultat


# Les travaux en arrière-plan restent référencés jusqu'à leur fin (sinon le ramasse-miettes peut les couper).
_TACHES: set[asyncio.Task] = set()
