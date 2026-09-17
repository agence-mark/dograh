"""[.mark] Check the town a caller names, before the model reads it.

⚠️ Since the plan nombres-dictes (2026-09-16), the step that runs in the call
and on the keyboard is ``lecture_appelant.py``: it reads numbers and towns
together, so a postal code said in words reaches the town check. What stays
here is shared by that step: which steps collect a town, the switch, the
record, and the check of 2026-09-16 used as is when the agent is not French.

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
  Since 2026-09-17 these names are a setting of the agent (``variables_commune``,
  default ``commune, commune_*, adresse*``): a client whose variable is called
  ``ville`` gets the check without a patch. Read at call time, alone.
- D6: the instruction to the agent lives in the note; no prompt is edited.
- D7: the keyboard bench is annotated too (now ``lecture_appelant.lire_message_tape``),
  so a keyboard campaign behaves like a call.
- T7: provisional contexts (``speculation=True``) are annotated as well.
  ⚠️ Only PARTLY covered, dormant today (Flux's eager end of turn is not
  enabled). Pipecat runs the early answer on a COPY of the context
  (``_run_speculative_inference``): the note reaches that early answer, but
  when the turn confirms it, the real message is written without a new
  context frame and never passes through this step. Later turns, and the
  variable extraction, would not see the note, and the only record is marked
  ``provisoire``. To be handled the day the early answer is turned on
  (review of 2026-09-16).
- T8: every check is recorded in the call's gathered context, under
  ``communes_verifiees``: the note is not in the transcript, and without this
  record a bench cannot be scored.

⚠️ The current step is read when the context reaches this step. Right after a
move to a step that collects a town, the caller's last message, said at the
previous step, is analysed then (« à Beauvais pour un devis » said at the
greeting gets its note at the address step). Wanted: that step is the one that
needs the town (counter-review of 2026-09-16).

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
from api.schemas.workflow_configurations import (
    DEFAULT_VARIABLES_COMMUNE,
    WorkflowConfigurationDefaults,
    decouper_variables_commune,
)
from api.services.communes.analyse import SURE, Detection, analyser, propositions_fondees
from api.services.communes.base import BaseCommunes, charger_base
from api.services.communes.mention import deja_mentionne, mentionner

CLE_INTERRUPTEUR = "verification_communes"
CLE_TRACE = "communes_verifiees"
CLE_VARIABLES = "variables_commune"

# The names of the default setting, ready to compare.
VARIABLES_PAR_DEFAUT = decouper_variables_commune(DEFAULT_VARIABLES_COMMUNE)


def _correspond(nom: str, motif: str) -> bool:
    return nom.startswith(motif[:-1]) if motif.endswith("*") else nom == motif


def etape_concernee(noeud, variables: tuple[str, ...] = VARIABLES_PAR_DEFAUT) -> bool:
    """Does this step collect a town? By the name of its extraction variables.

    ``variables`` is the agent's setting, already split (``variables_commune``):
    a name, or a name ending with ``*`` for "starts with". Case and spaces
    around the variable's name do not count.
    """
    for variable in getattr(noeud, "extraction_variables", None) or []:
        nom = (getattr(variable, "name", None) or "").strip().lower()
        if nom and any(_correspond(nom, motif) for motif in variables):
            return True
    return False


def variables_commune(run_configs: dict | None) -> tuple[str, ...]:
    """The agent's variable names, read alone through the schema (null or blank = default).

    ⛔ Only this key, like the switch below. An unreadable value (invalid name
    stored by hand, wrong type) falls back to the default with a warning: the
    call goes on with the rule of before, it does not lose the check.
    """
    try:
        valeur = WorkflowConfigurationDefaults.model_validate(
            {CLE_VARIABLES: (run_configs or {}).get(CLE_VARIABLES)}
        ).variables_commune
        return decouper_variables_commune(valeur)
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.warning(
            f"[.mark] Town check variable names unreadable, default used "
            f"({DEFAULT_VARIABLES_COMMUNE}): {erreur!r}"
        )
        return VARIABLES_PAR_DEFAUT


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
        # Present only when the words heard were a postal code (plan nombres-dictes):
        # its proposals must not confirm that same code on a later turn.
        **({"code_postal_entendu": True} if getattr(detection, "code_postal_entendu", False) else {}),
    }


def _analyser_et_mentionner(texte: str, adresse: AdresseEtablissement | None):
    """Blocking: runs in a worker thread. Returns (annotated text, detections, base)."""
    base = charger_base()
    magasin = base.coordonnees(adresse.code_insee) if adresse else None
    detections = propositions_fondees(texte, analyser(texte, base, magasin), base)
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


class Consignation:
    """Records into the call's gathered context (T8), and reads it back.

    ``consigner(entree)`` appends a town check under ``communes_verifiees``;
    ``consigner(entree, cle)`` under another key (``nombres_lus``). ``lire``
    gives the reading step the towns of the call so far (N2, branch ②).
    """

    def __init__(self, contexte_recueilli: Callable[[], dict]):
        self._contexte_recueilli = contexte_recueilli

    def __call__(self, entree: dict, cle: str = CLE_TRACE) -> None:
        self._contexte_recueilli().setdefault(cle, []).append(entree)

    def lire(self, cle: str = CLE_TRACE) -> list:
        return list(self._contexte_recueilli().get(cle) or [])


def consigner_dans(contexte_recueilli: Callable[[], dict]) -> Consignation:
    """A recorder that appends to the call's gathered context (T8)."""
    return Consignation(contexte_recueilli)
