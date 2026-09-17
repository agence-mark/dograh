"""[.mark] Read the caller's numbers and towns in ONE step, right before the model.

Why this module exists
----------------------
Two steps used to read the caller: the conversion of dictated numbers, BEFORE
the user aggregator (2026-09-15), and the town check, AFTER it (2026-09-16).
The bench of 2026-09-16 showed they never met: the conversion froze ONE
reading of a postal code ("soixante sept cent quarante" -> 67140) and the town
check never saw a postal code said in words. The plan nombres-dictes (N1)
replaces both with this single step, the only place that has at once the
caller's words, the current step, the list of communes and the call's record.

What the model reads (who does what, by switch)
-----------------------------------------------
+----------------------+-------------------------------+-------------------------------------+
|                      | conversion off                | conversion on                       |
+======================+===============================+=====================================+
| town check off       | no step (build_pipeline gets  | numbers in digits, amount and       |
|                      | None: the list of before)     | reference notes, ``nombres_lus``    |
+----------------------+-------------------------------+-------------------------------------+
| town check on        | words kept; the reader helps  | everything                          |
|                      | the towns only (postal codes, |                                     |
|                      | departments, N6); town note   |                                     |
+----------------------+-------------------------------+-------------------------------------+

- Town notes only at steps that collect a town (``etape_concernee``, 2026-09-16),
  by the agent's variable names (``variables_commune``, 2026-09-17): the call
  and the keyboard read the same setting.
- Reference notes only at steps that collect a variable starting with
  ``reference`` (N4). Digits at every step.
- 🔒 N1: the recorded transcript keeps the caller's WORDS. The aggregator
  records the text it wrote before this step changes the context message;
  the model, the variable extraction and the call's context read the digits.
- French only: for another language the reader does not run, and the town
  check works as on 2026-09-16 (five digits only).
- No effect in realtime mode (no transcription step).

⛔ What it must never do
- Hold the audio: reading and analysis run in a worker thread (T10).
- Cost the call: any failure leaves the message as it was, with a warning (T9).
- Read twice: a message already examined, or already carrying a note, is left
  alone; a context sent again after a tool call is not rewritten again (T8).
- T7 caveat, as in the town check: a provisional context (``speculation``) is
  read and its record marked ``provisoire``, but a confirmed early answer
  writes the real message without passing here. Dormant (Flux's eager end of
  turn is not enabled).
"""

from __future__ import annotations

import asyncio
from typing import Callable

from loguru import logger

from api.schemas.organization_preferences import AdresseEtablissement
from api.services.communes.base import charger_base, obtenir_base
from api.services.communes.mention import deja_mentionne as commune_deja_mentionnee
from api.services.communes.mention import mentionner
from api.services.communes.sons import precharger as precharger_sons
from api.services.nombres import lecture as lecteur
from api.services.nombres.lecture import (
    CODE_POSTAL,
    MONTANT,
    LectureMessage,
    analyser_message,
    reecrire,
)
from api.services.nombres.mention import deja_mentionne as nombres_deja_mentionnes
from api.services.nombres.mention import mentionner_nombres
from api.services.pipecat.conversion_nombres import (
    conversion_allumee,
    langue_agent_francaise,
)
from api.services.pipecat.verification_communes import (
    CLE_TRACE,
    VARIABLES_PAR_DEFAUT,
    annoter_texte,
    etape_concernee,
    interrupteur_allume,
    trace_de,
    variables_commune,
)
from pipecat.frames.frames import Frame, LLMContextFrame, StartFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

CLE_TRACE_NOMBRES = "nombres_lus"


def etape_reference(noeud) -> bool:
    """Does this step collect a reference? (N4) By variable name, like the towns."""
    for variable in getattr(noeud, "extraction_variables", None) or []:
        if (getattr(variable, "name", None) or "").strip().lower().startswith("reference"):
            return True
    return False


def _nom_etape(noeud) -> str | None:
    return getattr(noeud, "name", None)


def _trace_nombre(nombre, choix, etape: str | None) -> dict:
    """What the bench reads back for one number (T7)."""
    retenu = choix.code if (nombre.type == CODE_POSTAL and choix is not None) else None
    if nombre.type == CODE_POSTAL:
        lectures = list(nombre.lectures_cp)
    elif nombre.type == MONTANT:
        lectures = list(nombre.montants)
    else:
        lectures = []
    return {
        "etape": etape,
        "entendu": nombre.entendu,
        "type": nombre.type,
        "ecrit": retenu or nombre.ecrit,
        "lectures": lectures,
        "retenu": retenu,
        "statut": choix.statut if choix is not None else None,
    }


def _lire(texte: str, adresse: AdresseEtablissement | None, trace_communes: list, conversion: bool,
          communes: bool, references: bool, etape_adresse: bool = True, trace_nombres: list | None = None):
    """Blocking: runs in a worker thread. Returns (text for the model, town records, number records)."""
    try:
        base = charger_base()
        magasin = base.coordonnees(adresse.code_insee) if adresse else None
        lecture = analyser_message(
            texte, base, magasin, trace_communes, etape_adresse=etape_adresse, trace_nombres=trace_nombres
        )
    except Exception as erreur:  # noqa: BLE001
        # Without the list of communes (or its analysis), the numbers are still
        # written as digits: the fix of 2026-09-15 does not depend on the towns.
        logger.warning(f"[.mark] Town analysis failed, numbers read without it: {erreur!r}")
        base = None
        lecture = LectureMessage(nombres=lecteur.lire_nombres(texte), detections=[], choix={})
    lu = reecrire(texte, lecture.nombres, lecture.choix_cp) if conversion else texte
    if communes and base is not None:
        lu = mentionner(lu, lecture.detections, base)
    if conversion:
        lu = mentionner_nombres(lu, lecture.nombres, avec_references=references)
    return lu, lecture, base


async def lire_texte(
    texte: str,
    *,
    conversion: bool,
    verification: bool,
    langue_francaise: bool,
    adresse: AdresseEtablissement | None,
    noeud,
    consigner: Callable[..., None] | None,
    provisoire: bool = False,
    variables: tuple[str, ...] = VARIABLES_PAR_DEFAUT,
) -> str:
    """``texte`` as the model must read it, or ``texte`` unchanged. Never raises.

    ``variables``: the agent's names of the variables that collect a town.
    """
    try:
        if not texte or commune_deja_mentionnee(texte) or nombres_deja_mentionnes(texte):
            return texte
        etape_adresse = etape_concernee(noeud, variables)
        communes = verification and etape_adresse
        etape = _nom_etape(noeud)
        if not langue_francaise:
            # The reader is French only: the town check of 2026-09-16, unchanged.
            if not communes:
                return texte
            return await annoter_texte(
                texte, adresse, etape, (lambda e: consigner(e, CLE_TRACE)) if consigner else None, provisoire
            )
        if not conversion and not communes:
            return texte
        lire_trace = getattr(consigner, "lire", None)
        trace_communes = lire_trace(CLE_TRACE) if callable(lire_trace) else []
        # V4 (plan voix-et-communes): a postal code said at an earlier turn.
        trace_nombres = lire_trace(CLE_TRACE_NOMBRES) if callable(lire_trace) else []
        lu, lecture, base = await asyncio.to_thread(
            _lire, texte, adresse, trace_communes, conversion, communes, etape_reference(noeud),
            etape_adresse, trace_nombres,
        )
        if consigner is not None:
            entrees: list[tuple[str, dict]] = []
            if communes:
                entrees += [(CLE_TRACE, trace_de(d, base, etape)) for d in lecture.detections]
            if conversion:
                entrees += [
                    (CLE_TRACE_NOMBRES, _trace_nombre(n, lecture.choix.get(n.debut), etape))
                    for n in lecture.nombres
                ]
            for cle, entree in entrees:
                try:
                    if provisoire:
                        # A provisional context may be followed by the real one:
                        # marked, so a bench does not count the reading twice.
                        entree["provisoire"] = True
                    consigner(entree, cle)
                except Exception as erreur:  # noqa: BLE001
                    logger.warning(f"[.mark] Caller reading not recorded: {erreur!r}")
        return lu
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.warning(f"[.mark] Caller reading failed, message kept as is: {erreur!r}")
        return texte


class LectureAppelantProcessor(FrameProcessor):
    """Rewrites and annotates the caller's last message before the model reads it."""

    def __init__(
        self,
        *,
        conversion: bool,
        verification: bool,
        langue_francaise: bool,
        adresse: AdresseEtablissement | None,
        etape_courante: Callable[[], object],
        consigner: Callable[..., None] | None = None,
        variables: tuple[str, ...] = VARIABLES_PAR_DEFAUT,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._variables = variables
        self._conversion = conversion
        self._verification = verification
        self._langue_francaise = langue_francaise
        self._adresse = adresse
        self._etape_courante = etape_courante
        self._consigner = consigner
        # (id, content) of messages already examined: a context is sent to the
        # model again after a tool call, and must not be read again.
        self._examines: set[tuple[int, str]] = set()

    async def _precharger(self):
        try:
            await obtenir_base()
            # The pronunciation engine too: its first start (about 650 ms) would
            # otherwise delay the first address turn of the call (review of 2026-09-17).
            await asyncio.to_thread(precharger_sons)
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[.mark] List of communes not preloaded: {erreur!r}")

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
        lu = await lire_texte(
            contenu,
            conversion=self._conversion,
            verification=self._verification,
            langue_francaise=self._langue_francaise,
            adresse=self._adresse,
            noeud=self._etape_courante(),
            consigner=self._consigner,
            provisoire=frame.speculation,
            variables=self._variables,
        )
        # Marked AFTER the reading: an interruption that cancels this task
        # during the await leaves the message unmarked, so the next context
        # that carries it is read again (review of 2026-09-16).
        self._examines.add(cle)
        if lu != contenu:
            message["content"] = lu
            self._examines.add((id(message), lu))

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            # Read the list before the first turn needs it, off the loop.
            self.create_task(self._precharger())
        elif isinstance(frame, LLMContextFrame) and direction == FrameDirection.DOWNSTREAM:
            try:
                await self._lire_contexte(frame)
            except Exception as erreur:  # noqa: BLE001 -- the call must go on
                logger.warning(f"[.mark] Caller reading failed, context kept as is: {erreur!r}")
        await self.push_frame(frame, direction)


def creer_lecture_appelant(
    run_configs: dict | None,
    stt_config,
    adresse: AdresseEtablissement | None,
    etape_courante: Callable[[], object],
    consigner: Callable[..., None] | None = None,
) -> LectureAppelantProcessor | None:
    """The step for this agent, or ``None`` when both switches are off (T3)."""
    conversion = conversion_allumee(run_configs)
    verification = interrupteur_allume(run_configs)
    if not conversion and not verification:
        return None
    return LectureAppelantProcessor(
        conversion=conversion,
        verification=verification,
        langue_francaise=langue_agent_francaise(stt_config),
        adresse=adresse,
        etape_courante=etape_courante,
        consigner=consigner,
        variables=variables_commune(run_configs),
    )


async def lire_message_tape(
    texte: str,
    run_configs: dict | None,
    stt_config,
    adresse: AdresseEtablissement | None,
    noeud,
    consigner: Callable[..., None] | None,
) -> str:
    """R5, keyboard bench: the typed message, read like a call's. Never raises."""
    try:
        return await lire_texte(
            texte,
            conversion=conversion_allumee(run_configs),
            verification=interrupteur_allume(run_configs),
            langue_francaise=langue_agent_francaise(stt_config),
            adresse=adresse,
            noeud=noeud,
            consigner=consigner,
            variables=variables_commune(run_configs),
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Caller reading failed on the keyboard, message kept: {erreur!r}")
        return texte
