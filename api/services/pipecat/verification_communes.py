"""[.mark] Check the town a caller names, before the model reads it.

Why this module exists
----------------------
"Beauvais" was transcribed "Beauvet" (2026-09-15), then "Bovet" (2026-09-16).
A keyword list per shop does not carry over to the next client, so the town is
recognised against the national list of communes (``api/services/communes/``)
and a note is added to the caller's message:

    c'est à Beauvet [Vérification de la commune : « Beauvet » correspond à
    Beauvais (60000, Oise). Utilise ce nom sans le faire répéter.]

Decisions of 2026-09-16
-----------------------
- D1: AFTER the user aggregator, right before the model. The model and the
  variable extraction (which reads the context) see the note; the recorded
  transcript does not -- the aggregator emits it from the text it wrote,
  before any downstream step runs.
- D5: only at steps that extract a variable named ``commune``, starting with
  ``commune_`` or with ``adresse``. Switch per agent, ON by default.
- D6: the instruction to the agent lives in the note; no prompt is edited.
- D7: the keyboard bench is annotated too (``annoter_message_tape``), so a
  keyboard campaign behaves like a call.
- T7: provisional contexts (``speculation=True``) are annotated as well.
  Dormant today (Flux's eager end of turn is not enabled), covered anyway.
- T8: every check is recorded in the call's gathered context, under
  ``communes_verifiees``: the note is not in the transcript, and without this
  record a bench cannot be scored.

⛔ What it must never do
- Hold the audio: the analysis (about 10 ms) and the first read of the list
  run in a worker thread.
- Cost the call: any failure leaves the message as it was, with a warning.
- Annotate twice: a message that already carries the marker is left alone.
"""

from __future__ import annotations

import asyncio
from typing import Callable

from loguru import logger

from api.schemas.organization_preferences import AdresseEtablissement
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.communes.analyse import SURE, Detection, analyser
from api.services.communes.base import BaseCommunes, charger_base, obtenir_base
from api.services.communes.mention import deja_mentionne, mentionner
from pipecat.frames.frames import Frame, LLMContextFrame, StartFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

CLE_INTERRUPTEUR = "verification_communes"
CLE_TRACE = "communes_verifiees"


def etape_concernee(noeud) -> bool:
    """Does this step collect a town? One rule for every agent, by variable name."""
    for variable in getattr(noeud, "extraction_variables", None) or []:
        nom = (getattr(variable, "name", None) or "").strip().lower()
        if nom == "commune" or nom.startswith("commune_") or nom.startswith("adresse"):
            return True
    return False


def interrupteur_allume(run_configs: dict | None) -> bool:
    """The agent's switch, read alone through the schema (a stored null = default = on).

    ⛔ Only this key: the whole configuration read here would let any other
    setting stored out of bounds kill the call (counter-review of 2026-09-15).
    """
    try:
        return WorkflowConfigurationDefaults.model_validate(
            {CLE_INTERRUPTEUR: (run_configs or {}).get(CLE_INTERRUPTEUR)}
        ).verification_communes
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.warning(f"[.mark] Town check switch unreadable, left on: {erreur!r}")
        return True


def _lecture(detection: Detection, base: BaseCommunes, rang: int) -> dict:
    c = detection.lectures[rang].commune
    return {
        "nom": c.nom,
        "code_insee": c.insee,
        "departement": base.nom_departement(c.dep),
        "codes_postaux": list(c.cps),
    }


def trace_de(detection: Detection, base: BaseCommunes, etape: str | None) -> dict:
    """What the bench reads back: heard, verdict, town kept, proposals."""
    return {
        "etape": etape,
        "entendu": detection.entendu,
        "statut": "sure" if detection.statut == SURE else "a_confirmer",
        "commune_retenue": _lecture(detection, base, 0) if detection.statut == SURE else None,
        "propositions": [_lecture(detection, base, i) for i in range(min(3, len(detection.lectures)))],
    }


def _analyser_et_mentionner(texte: str, adresse: AdresseEtablissement | None):
    """Blocking: runs in a worker thread. Returns (annotated text, detections, base)."""
    base = charger_base()
    magasin = base.coordonnees(adresse.code_insee) if adresse else None
    detections = analyser(texte, base, magasin)
    return mentionner(texte, detections, base), detections, base


async def annoter_texte(
    texte: str,
    adresse: AdresseEtablissement | None,
    etape: str | None,
    consigner: Callable[[dict], None] | None,
    provisoire: bool = False,
) -> str:
    """``texte`` with its town notes, or ``texte`` unchanged. Never raises."""
    try:
        if not texte or deja_mentionne(texte):
            return texte
        annote, detections, base = await asyncio.to_thread(_analyser_et_mentionner, texte, adresse)
        if consigner is not None:
            for detection in detections:
                try:
                    entree = trace_de(detection, base, etape)
                    if provisoire:
                        # A provisional context may be followed by the real one:
                        # marked, so a bench does not count the check twice.
                        entree["provisoire"] = True
                    consigner(entree)
                except Exception as erreur:  # noqa: BLE001
                    logger.warning(f"[.mark] Town check not recorded: {erreur!r}")
        return annote
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.warning(f"[.mark] Town check failed, message kept as is: {erreur!r}")
        return texte


def _nom_etape(noeud) -> str | None:
    return getattr(noeud, "name", None)


class VerificationCommunesProcessor(FrameProcessor):
    """Annotates the caller's last message with the towns it names."""

    def __init__(
        self,
        *,
        adresse: AdresseEtablissement | None,
        etape_courante: Callable[[], object],
        consigner: Callable[[dict], None] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._adresse = adresse
        self._etape_courante = etape_courante
        self._consigner = consigner
        # (id, content) of messages already examined: a context is sent to the
        # model again after a tool call, and must not be analysed again.
        self._examines: set[tuple[int, str]] = set()

    async def _precharger(self):
        try:
            await obtenir_base()
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[.mark] List of communes not preloaded: {erreur!r}")

    async def _annoter_contexte(self, frame: LLMContextFrame):
        noeud = self._etape_courante()
        if not etape_concernee(noeud):
            return
        messages = frame.context.messages
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("role") == "user":
                break
        else:
            return
        contenu = message.get("content")
        if not isinstance(contenu, str) or deja_mentionne(contenu):
            return
        cle = (id(message), contenu)
        if cle in self._examines:
            return
        self._examines.add(cle)
        annote = await annoter_texte(
            contenu, self._adresse, _nom_etape(noeud), self._consigner, provisoire=frame.speculation
        )
        if annote != contenu:
            message["content"] = annote
            self._examines.add((id(message), annote))

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            # Read the list before the first turn needs it, off the loop.
            self.create_task(self._precharger())
        elif isinstance(frame, LLMContextFrame) and direction == FrameDirection.DOWNSTREAM:
            try:
                await self._annoter_contexte(frame)
            except Exception as erreur:  # noqa: BLE001 -- the call must go on
                logger.warning(f"[.mark] Town check failed, context kept as is: {erreur!r}")
        await self.push_frame(frame, direction)


def creer_verification_communes(
    run_configs: dict | None,
    adresse: AdresseEtablissement | None,
    etape_courante: Callable[[], object],
    consigner: Callable[[dict], None] | None = None,
) -> VerificationCommunesProcessor | None:
    """The step for this agent, or ``None`` when its switch is off (D5)."""
    if not interrupteur_allume(run_configs):
        return None
    return VerificationCommunesProcessor(
        adresse=adresse, etape_courante=etape_courante, consigner=consigner
    )


def consigner_dans(contexte_recueilli: Callable[[], dict]) -> Callable[[dict], None]:
    """A recorder that appends to the call's gathered context (T8)."""

    def consigner(entree: dict) -> None:
        contexte_recueilli().setdefault(CLE_TRACE, []).append(entree)

    return consigner


async def annoter_message_tape(
    texte: str,
    run_configs: dict | None,
    adresse: AdresseEtablissement | None,
    noeud,
    consigner: Callable[[dict], None] | None,
) -> str:
    """D7, keyboard bench: the typed message, annotated like a call's. Never raises."""
    try:
        if not interrupteur_allume(run_configs) or not etape_concernee(noeud):
            return texte
        return await annoter_texte(texte, adresse, _nom_etape(noeud), consigner)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Town check failed on the keyboard, message kept: {erreur!r}")
        return texte
