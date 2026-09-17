"""[.mark] Correct the names of the trade in the caller's message, before anything reads it.

Why this step, and why HERE
---------------------------
The transcription writes "édile camembert" and the model repeats it. This step
compares the caller's words with the organization's trade vocabulary
(``api/services/lexique/``): a sure name is written properly, a doubtful one
gets a note asking the agent to confirm it (L5).

It sits right AFTER the user aggregator and its gate, and right BEFORE
``lecture_appelant`` (T8): the names are written properly before the numbers
and the towns are read, so "Supra" or "Royal" never become communes, and the
notes those two add are never read as brand names (T17).

⛔ What it must never do
- Hold the audio: the analysis runs in a worker thread (T6).
- Cost the call: any failure leaves the message as it was, with a warning.
- Read twice: a message already examined, or already carrying its note, is
  left alone (T9) -- a context is sent again after a tool call.
- 🔒 The recorded transcript keeps the caller's WORDS: the aggregator writes it
  before this step changes the context message (same rule as the numbers, L5).
- Rewrite a town: a heard word that is the name of a commune is never a brand
  (T16), and without the list of communes nothing is read at all.
"""

from __future__ import annotations

import asyncio
from typing import Callable

from loguru import logger

from api.schemas.lexique_metier import LexiqueMetier
from api.services.communes.base import base_si_chargee, obtenir_base
from api.services.communes.sons import precharger as precharger_sons
from api.services.lexique.analyse import Index, analyser
from api.services.lexique.correction import corriger, deja_mentionne, partie_de_lappelant
from api.services.lexique.ecoute import prononciations_du_lexique
from api.services.lexique.reglages import interrupteur_allume
from pipecat.frames.frames import Frame, LLMContextFrame, StartFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

CLE_TRACE = "lexique_reconnu"
CLE_TRACE_LEXIQUE = "lexique_metier"

__all__ = [
    "CLE_TRACE",
    "CLE_TRACE_LEXIQUE",
    "ReconnaissanceLexiqueProcessor",
    "annoter_message_tape",
    "construire_index",
    "creer_reconnaissance_lexique",
    "interrupteur_allume",
    "trace_du_lexique",
]


def noms_a_reconnaitre(lexique: LexiqueMetier) -> list:
    return [terme for terme in lexique.termes if terme.type == "nom"]


def construire_index(lexique: LexiqueMetier, avec_sons: bool = True) -> Index | None:
    """The vocabulary ready to compare, or None when it cannot be built.

    Blocking (the list of communes, the keys, the pronunciation engine): call
    it in a worker thread.
    """
    try:
        base = base_si_chargee()
        return Index.construire(lexique, base.par_nom if base is not None else None, avec_sons=avec_sons)
    except Exception as erreur:  # noqa: BLE001 -- the call goes on without the vocabulary
        logger.warning(f"[.mark] Trade vocabulary not prepared, names left as heard: {erreur!r}")
        return None


def _trace(detection, etape: str | None) -> dict:
    """What a bench reads back for one name (T10)."""
    return {
        "etape": etape,
        "entendu": detection.entendu,
        "statut": detection.statut,
        "terme": detection.terme,
        "propositions": [
            {"terme": p.terme, "categorie": p.categorie, "score": p.score}
            for p in detection.propositions[:3]
        ],
        "par_son": detection.par_son,
    }


def trace_du_lexique(
    lexique: LexiqueMetier, envoyes_a_flux: list[str], liste_tronquee: bool
) -> dict:
    """What the call ran with (T10): sizes, and the terms sent to the transcription."""
    return {
        "termes": len(lexique.termes),
        "noms": len(noms_a_reconnaitre(lexique)),
        "envoyes_a_flux": list(envoyes_a_flux),
        "liste_tronquee": bool(liste_tronquee),
        "prononciations": len(prononciations_du_lexique(lexique)),
    }


async def corriger_texte(
    texte: str,
    index: Index | None,
    *,
    etape: str | None = None,
    consigner: Callable[..., None] | None = None,
    avec_sons: bool = True,
    provisoire: bool = False,
) -> str:
    """``texte`` with the trade names written properly, or ``texte`` unchanged. Never raises."""
    try:
        if not texte or index is None or index.vide or deja_mentionne(texte):
            return texte
        appelant, notes = partie_de_lappelant(texte)
        if not appelant:
            return texte
        lectures = await asyncio.to_thread(analyser, appelant, index, avec_sons)
        if not lectures:
            return texte
        corrige = corriger(appelant, lectures)
        if consigner is not None:
            for detection in lectures:
                try:
                    entree = _trace(detection, etape)
                    if provisoire:
                        # A provisional context may be followed by the real one:
                        # marked, so a bench does not count the reading twice.
                        entree["provisoire"] = True
                    consigner(entree, CLE_TRACE)
                except Exception as erreur:  # noqa: BLE001
                    logger.warning(f"[.mark] Trade name not recorded: {erreur!r}")
        # The notes of the other readers are glued back, untouched (T17).
        return f"{corrige} {notes}" if notes else corrige
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.warning(f"[.mark] Trade vocabulary failed, message kept as is: {erreur!r}")
        return texte


class ReconnaissanceLexiqueProcessor(FrameProcessor):
    """Writes the trade names properly in the caller's last message."""

    def __init__(
        self,
        *,
        lexique: LexiqueMetier,
        etape_courante: Callable[[], object],
        consigner: Callable[..., None] | None = None,
        avec_sons: bool = True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._lexique = lexique
        self._etape_courante = etape_courante
        self._consigner = consigner
        self._avec_sons = avec_sons
        self._index: Index | None = None
        # (id, content) of messages already examined: a context is sent to the
        # model again after a tool call, and must not be read again.
        self._examines: set[tuple[int, str]] = set()

    async def _preparer(self):
        try:
            # The list of communes first (a name of commune is never a brand),
            # then the keys and the sounds of the vocabulary: about 400 ms, once,
            # off the event loop and before the first turn needs them (T7).
            await obtenir_base()
            if self._avec_sons:
                await asyncio.to_thread(precharger_sons)
            self._index = await asyncio.to_thread(construire_index, self._lexique, self._avec_sons)
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[.mark] Trade vocabulary not prepared: {erreur!r}")

    def _nom_etape(self) -> str | None:
        try:
            return getattr(self._etape_courante(), "name", None)
        except Exception:  # noqa: BLE001
            return None

    async def _lire_contexte(self, frame: LLMContextFrame):
        messages = frame.context.messages
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("role") == "user":
                break
        else:
            return
        contenu = message.get("content")
        if not isinstance(contenu, str):
            return
        cle = (id(message), contenu)
        if cle in self._examines:
            return
        corrige = await corriger_texte(
            contenu,
            self._index,
            etape=self._nom_etape(),
            consigner=self._consigner,
            avec_sons=self._avec_sons,
            provisoire=bool(getattr(frame, "speculation", False)),
        )
        # Marked AFTER the reading: an interruption that cancels this task
        # during the await leaves the message unmarked, so the next context
        # that carries it is read again (rule of the caller reading).
        self._examines.add(cle)
        if corrige != contenu:
            message["content"] = corrige
            self._examines.add((id(message), corrige))

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            self.create_task(self._preparer())
        elif isinstance(frame, LLMContextFrame) and direction == FrameDirection.DOWNSTREAM:
            try:
                await self._lire_contexte(frame)
            except Exception as erreur:  # noqa: BLE001 -- the call must go on
                logger.warning(f"[.mark] Trade vocabulary failed, context kept as is: {erreur!r}")
        await self.push_frame(frame, direction)


def creer_reconnaissance_lexique(
    run_configs: dict | None,
    lexique: LexiqueMetier,
    etape_courante: Callable[[], object],
    consigner: Callable[..., None] | None = None,
    avec_sons: bool = True,
) -> ReconnaissanceLexiqueProcessor | None:
    """The step for this agent, or ``None``: switch off, or no name to recognise."""
    if not interrupteur_allume(run_configs) or not noms_a_reconnaitre(lexique):
        return None
    return ReconnaissanceLexiqueProcessor(
        lexique=lexique,
        etape_courante=etape_courante,
        consigner=consigner,
        avec_sons=avec_sons,
    )


async def annoter_message_tape(
    texte: str,
    run_configs: dict | None,
    lexique: LexiqueMetier,
    noeud,
    consigner: Callable[..., None] | None = None,
    avec_sons: bool = True,
) -> str:
    """The keyboard bench: a typed message read like a call's (L10). Never raises."""
    try:
        if not interrupteur_allume(run_configs) or not noms_a_reconnaitre(lexique):
            return texte
        await obtenir_base()
        index = await asyncio.to_thread(construire_index, lexique, avec_sons)
        return await corriger_texte(
            texte,
            index,
            etape=getattr(noeud, "name", None),
            consigner=consigner,
            avec_sons=avec_sons,
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Trade vocabulary failed on the keyboard, message kept: {erreur!r}")
        return texte
