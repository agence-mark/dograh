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
  ``reference`` (N4), now the agent's setting ``variables_reference``. Digits at
  every step.
- Plan fiche-au-fil-de-leau, lot 2 (D9): with the record switched on, the two
  triggers read the fields of the AGENT's record instead of the current step's
  variables, so a town given at any step is checked. Off: exactly as before.
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
from types import SimpleNamespace
from typing import Callable

from api.schemas.organization_preferences import AdresseEtablissement
from api.schemas.workflow_configurations import (
    DEFAULT_VARIABLES_REFERENCE,
    WorkflowConfigurationDefaults,
    decouper_variables_commune,
)
from api.services.communes.analyse import SURE as SURE_COMMUNE
from api.services.communes.base import charger_base, obtenir_base
from api.services.communes.mention import deja_mentionne as commune_deja_mentionnee
from api.services.communes.mention import mentionner
from api.services.communes.sons import precharger as precharger_sons
from api.services.epellation.lecture import lire as lire_epellations
from api.services.epellation.mention import deja_mentionne as epellation_deja_mentionnee
from api.services.epellation.mention import mentionner_epellations
from api.services.lexique.correction import MARQUE as MARQUE_LEXIQUE
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
    CLE_TRACE_EPELLATIONS,
    CLE_TRACE_VOIES,
    VARIABLES_PAR_DEFAUT,
    annoter_texte,
    epellation_allumee,
    etape_concernee,
    interrupteur_allume,
    sons_allumes,
    trace_de,
    variables_commune,
    voies_allumees,
)
from api.services.voies import base as base_voies
from api.services.voies.analyse import SURE as VOIE_SURE
from api.services.voies.analyse import Detection as DetectionVoie
from api.services.voies.analyse import analyser as analyser_voie
from api.services.voies.mention import deja_mentionne as voie_deja_mentionnee
from api.services.voies.mention import mentionner_voie
from loguru import logger

from pipecat.frames.frames import Frame, LLMContextFrame, StartFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

CLE_TRACE_NOMBRES = "nombres_lus"


VARIABLES_REFERENCE_PAR_DEFAUT = decouper_variables_commune(
    DEFAULT_VARIABLES_REFERENCE, DEFAULT_VARIABLES_REFERENCE
)


def etape_reference(noeud, variables: tuple[str, ...] = VARIABLES_REFERENCE_PAR_DEFAUT) -> bool:
    """Does this step collect a reference? (N4) By variable name, like the towns.

    The default (``reference*``) is the rule written here until the lot 2 of
    fiche-au-fil-de-leau: a name that starts with ``reference``.
    """
    return etape_concernee(noeud, variables)


def variables_reference(run_configs: dict | None) -> tuple[str, ...]:
    """The agent's reference variable names, read alone (null or blank = default).

    An unreadable value falls back to the default with a warning, like the towns.
    """
    try:
        valeur = WorkflowConfigurationDefaults.model_validate(
            {"variables_reference": (run_configs or {}).get("variables_reference")}
        ).variables_reference
        return decouper_variables_commune(valeur, DEFAULT_VARIABLES_REFERENCE)
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.warning(
            f"[.mark] Reference variable names unreadable, default used "
            f"({DEFAULT_VARIABLES_REFERENCE}): {erreur!r}"
        )
        return VARIABLES_REFERENCE_PAR_DEFAUT


def champs_de_la_fiche(run_configs: dict | None) -> tuple[str, ...] | None:
    """The fields of the agent's record when the switch is on, else ``None``."""
    from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche

    reglages = ReglagesFiche.depuis(run_configs)
    return None if reglages is None else tuple(c.nom for c in reglages.champs)


def etape_vue_par_la_fiche(noeud, champs: tuple[str, ...] | None):
    """D9: with the record on, the triggers see the record's fields as the
    step's variables, whatever the step. The step keeps its NAME, for the
    traces. ``None`` = the real step, unchanged."""
    if champs is None:
        return noeud
    return SimpleNamespace(
        name=getattr(noeud, "name", None),
        extraction_variables=[SimpleNamespace(name=nom) for nom in champs],
    )


def _nom_etape(noeud) -> str | None:
    return getattr(noeud, "name", None)


def _trace_voie(detection: DetectionVoie, etape: str | None) -> dict:
    """What the bench reads back for one street (plan, lot 5).

    ⚠️ ``numero_present`` is recorded and NEVER said to the model (Q5): an
    incomplete base must not make a caller repeat their own number.
    """
    return {
        "etape": etape,
        "entendu": detection.entendu,
        "statut": detection.statut,
        "voie_retenue": detection.retenue or None,
        "propositions": [
            {"nom": p.nom, "score": round(p.score, 1), "numero_present": p.numero_present}
            for p in detection.propositions
        ],
        "par_son": detection.par_son,
    }


def _trace_epellation(epellation, etape: str | None) -> dict:
    """What the bench reads back for one spelling.

    🔑 ``entendu`` is what the other session's name filter needs to compare the
    HEARD form as well as the extracted one (point I1 of the plan, section 5).
    """
    return {"etape": etape, "entendu": epellation.entendu, "epele": epellation.epele}


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


def _hors_epellation(detections: list, epellations: list) -> list:
    """Les villes trouvées AILLEURS que dans des lettres épelées.

    🔴 Sur le tour d'épellation que Q4 fabrique exprès, la vérification des
    communes lisait les lettres comme un nom de ville : « oui, rue Lavoira,
    L A V O I R A » faisait demander « êtes-vous à **Voires, dans le Doubs** ? »
    à un appelant de Creil dont la commune était déjà tranchée. Mesuré :
    **18 notes de commune sur les 136 cas** du corpus d'épellation — « g e o »
    devenait Gaillon, « bois » devenait Bois (Charente-Maritime).

    ⛔ Le défaut est antérieur à ce chantier, mais ce chantier **fabrique** ce
    tour : le motif se ferme des DEUX côtés ou il ne se ferme pas
    (contre-relecture n° 6).

    ⚠️ Une ville épelée EXPRÈS reste lue : « c'est à Beauvais, B E A U V A I S »
    garde sa détection, parce que « beauvais » n'apparaît pas dans « b e a u v
    a i s ». Seul ce qui est lu DANS les lettres est écarté.
    """
    if not epellations or not detections:
        return detections
    passages = [e.entendu.lower() for e in epellations]
    return [
        detection
        for detection in detections
        if not any((detection.entendu or "").lower() in passage for passage in passages)
    ]


def _commune_sure(lecture: LectureMessage, trace_communes: list | None) -> str | None:
    """The INSEE code of the town to search the street in, or None.

    🔑 **This turn first, then the earlier ones.** The street reader needs a
    commune, and your agents ask for the postal code and the town BEFORE the
    street (Q6): most of the time the town was settled at an earlier turn and
    is not repeated with the street. Reading only the current turn would leave
    the street unchecked on exactly the turns that carry one.

    ⛔ Only a town settled SURE counts: searching the streets of a town that is
    still "to confirm" would look for a street in the wrong commune.
    """
    for detection in lecture.detections:
        if detection.statut == SURE_COMMUNE and detection.lectures:
            return detection.lectures[0].commune.insee
    # The most recent settled town of the call, latest first.
    for entree in reversed(trace_communes or []):
        if not isinstance(entree, dict) or entree.get("statut") != "sure":
            continue
        retenue = entree.get("commune_retenue") or {}
        if insee := retenue.get("code_insee"):
            return insee
    return None


def _lire_voie(
    texte: str,
    insee: str,
    nom_commune: str | None,
    avec_sons: bool,
    autres_communes: tuple[str, ...] = (),
    est_une_commune=None,
) -> DetectionVoie | None:
    """The street verdict, or None when it could not be read. Never raises."""
    try:
        return analyser_voie(
            texte,
            base_voies.voies_de(insee),
            nom_commune,
            avec_sons=avec_sons,
            autres_communes=autres_communes,
            est_une_commune=est_une_commune,
        )
    except FileNotFoundError:
        # A department whose file is not in the image: the call goes on exactly
        # as before this module existed.
        logger.warning(f"[.mark] No street base for {insee}, street not checked")
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.warning(f"[.mark] Street check failed, message kept as is: {erreur!r}")
    return None


def _lire(texte: str, adresse: AdresseEtablissement | None, trace_communes: list, conversion: bool,
          communes: bool, references: bool, etape_adresse: bool = True, trace_nombres: list | None = None,
          avec_sons: bool = True, voies: bool = False, epellation: bool = False):
    """Blocking: runs in a worker thread. Returns (text for the model, records...).

    🔑 The order is the plan's (lot 5), and each step of it was bought:
    1. **spelling FIRST**, before the numbers — otherwise "deux T" becomes "2 T"
       and the spelling is lost;
    2. numbers, towns, then the street, which needs the town the analysis settled.
    The notes are glued in this order: towns, street, spelling, numbers.
    """
    epellations = lire_epellations(texte) if epellation else []
    try:
        base = charger_base()
        magasin = base.coordonnees(adresse.code_insee) if adresse else None
        lecture = analyser_message(
            texte, base, magasin, trace_communes, etape_adresse=etape_adresse, trace_nombres=trace_nombres,
            avec_sons=avec_sons,
        )
    except Exception as erreur:  # noqa: BLE001
        # Without the list of communes (or its analysis), the numbers are still
        # written as digits: the fix of 2026-09-15 does not depend on the towns.
        logger.warning(f"[.mark] Town analysis failed, numbers read without it: {erreur!r}")
        base = None
        lecture = LectureMessage(nombres=lecteur.lire_nombres(texte), detections=[], choix={})

    lu = reecrire(texte, lecture.nombres, lecture.choix_cp) if conversion else texte

    # 🔑 La rue est cherchée sur le texte APRÈS la conversion des nombres, et
    # l'épellation AVANT : chacun a besoin de l'autre forme. « c'est au six rue
    # Danton » ne laissait vérifier aucun numéro tant que « six » restait en
    # lettres, et la base écrit « Rue des 3 Ponts » quand l'appelant dit
    # « des trois ponts ».
    voie = None
    if voies and base is not None and (insee := _commune_sure(lecture, trace_communes)):
        commune = base.commune(insee)
        # Les autres villes entendues à ce tour : une ville dont le nom commence
        # par un type de voie (« Pont-Sainte-Maxence ») ancrait la phrase sur une
        # rue que personne n'avait nommée.
        # ⛔ Les villes TRANCHÉES seulement, jamais les candidates : la
        # vérification des communes propose Tende, Hatten et Andé sur le mot
        # « attendez ». Une candidate approchée servant de point de coupe
        # tronquerait un nom de rue réel, sans trace (contre-relecture du 22/09).
        autres = tuple(
            detection.entendu
            for detection in lecture.detections
            if detection.entendu and detection.statut == SURE_COMMUNE
        )
        voie = _lire_voie(
            lu, insee, commune.nom if commune else None, avec_sons, autres,
            # La liste nationale des communes, que cette étape a déjà chargée :
            # elle sert à reconnaître « à <ville> » même quand la ville n'est pas
            # celle de l'appelant.
            lambda mot: bool(base.par_nom.get(mot)),
        )
        if epellations and voie is not None and voie.statut != VOIE_SURE:
            # 🔴 LA boucle que Q4 interdit, fermée par le CODE et non par une
            # phrase. Q4 fabrique exprès le tour « rue introuvable → fais
            # épeler » ; au tour suivant l'appelant épelle, le lecteur de rue
            # analyse les lettres, n'y retrouve rien, et **redemande une
            # épellation**. Mesuré : « oui, rue Lavoira, L A V O I R A » ressortait
            # avec « « lavoira v o i r » ne correspond à aucune rue… fais épeler ».
            # ⛔ Une épellation lue sur ce tour EST la réponse : la note de rue se
            # tait, celle de l'épellation dit au modèle quoi noter.
            voie = None

    if communes and base is not None:
        lu = mentionner(lu, _hors_epellation(lecture.detections, epellations), base)
    if voie is not None:
        lu = mentionner_voie(lu, voie)
    if epellations:
        lu = mentionner_epellations(lu, epellations)
    if conversion:
        lu = mentionner_nombres(lu, lecture.nombres, avec_references=references)
    return lu, lecture, base, voie, epellations


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
    avec_sons: bool = True,
    voies: bool = False,
    epellation: bool = False,
    variables_ref: tuple[str, ...] = VARIABLES_REFERENCE_PAR_DEFAUT,
    champs_fiche: tuple[str, ...] | None = None,
) -> str:
    """``texte`` as the model must read it, or ``texte`` unchanged. Never raises.

    ``variables``: the agent's names of the variables that collect a town.

    🆕 T17 (plan lexique-metier): the note the trade vocabulary may have added
    is set aside and glued back untouched. Read along with the rest, the brand
    names it cites ("Deville", "Barbas") would be proposed as communes and the
    agent would say them out loud (fiche D of 2026-09-17).
    """
    appelant, mention_lexique = _separer_mention_lexique(texte)
    lu = await _lire_texte_de_lappelant(
        appelant,
        conversion=conversion,
        verification=verification,
        langue_francaise=langue_francaise,
        adresse=adresse,
        # D9: the ONE place where the record replaces the step for the triggers.
        noeud=etape_vue_par_la_fiche(noeud, champs_fiche),
        consigner=consigner,
        provisoire=provisoire,
        variables=variables,
        avec_sons=avec_sons,
        voies=voies,
        epellation=epellation,
        variables_ref=variables_ref,
    )
    return f"{lu} {mention_lexique}" if mention_lexique else lu


def _separer_mention_lexique(texte: str) -> tuple[str, str]:
    """(what the caller said, the trade vocabulary's note) -- the note is never read."""
    place = texte.find(MARQUE_LEXIQUE) if texte else -1
    return (texte, "") if place == -1 else (texte[:place].rstrip(), texte[place:])


async def _lire_texte_de_lappelant(
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
    avec_sons: bool = True,
    voies: bool = False,
    epellation: bool = False,
    variables_ref: tuple[str, ...] = VARIABLES_REFERENCE_PAR_DEFAUT,
) -> str:
    try:
        if (
            not texte
            or commune_deja_mentionnee(texte)
            or nombres_deja_mentionnes(texte)
            or voie_deja_mentionnee(texte)
            or epellation_deja_mentionnee(texte)
        ):
            return texte
        etape_adresse = etape_concernee(noeud, variables)
        communes = verification and etape_adresse
        # Q7: the street check runs at the same steps as the town check, by the
        # same setting, and needs it — there is no street list without a commune.
        voies = voies and communes
        etape = _nom_etape(noeud)
        if not langue_francaise:
            # The reader is French only: the town check of 2026-09-16, unchanged.
            if not communes:
                return texte
            return await annoter_texte(
                texte, adresse, etape, (lambda e: consigner(e, CLE_TRACE)) if consigner else None, provisoire,
                avec_sons,
            )
        # ⚠️ ``epellation`` alone is enough to run: a caller spells a name at any
        # step (Q8), including when neither conversion nor the town check apply.
        if not conversion and not communes and not epellation:
            return texte
        lire_trace = getattr(consigner, "lire", None)
        trace_communes = lire_trace(CLE_TRACE) if callable(lire_trace) else []
        # V4 (plan voix-et-communes): a postal code said at an earlier turn.
        trace_nombres = lire_trace(CLE_TRACE_NOMBRES) if callable(lire_trace) else []
        lu, lecture, base, voie, epellations = await asyncio.to_thread(
            _lire, texte, adresse, trace_communes, conversion, communes, etape_reference(noeud, variables_ref),
            etape_adresse, trace_nombres, avec_sons, voies, epellation,
        )
        if consigner is not None:
            entrees: list[tuple[str, dict]] = []
            if communes:
                entrees += [(CLE_TRACE, trace_de(d, base, etape)) for d in lecture.detections]
            if voie is not None:
                entrees.append((CLE_TRACE_VOIES, _trace_voie(voie, etape)))
            entrees += [(CLE_TRACE_EPELLATIONS, _trace_epellation(e, etape)) for e in epellations]
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
        avec_sons: bool = True,
        voies: bool = False,
        epellation: bool = False,
        variables_ref: tuple[str, ...] = VARIABLES_REFERENCE_PAR_DEFAUT,
        champs_fiche: tuple[str, ...] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._variables_ref = variables_ref
        self._champs_fiche = champs_fiche
        self._variables = variables
        self._avec_sons = avec_sons
        self._voies = voies
        self._epellation = epellation
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
            if self._voies:
                # 🔴 Says ONCE whether the street base is actually in the image.
                # Without it, a production with no files looks exactly like a
                # production where no caller ever names a known street.
                await asyncio.to_thread(base_voies.journaliser_etat)
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
            avec_sons=self._avec_sons,
            voies=self._voies,
            epellation=self._epellation,
            variables_ref=self._variables_ref,
            champs_fiche=self._champs_fiche,
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
    epellation = epellation_allumee(run_configs)
    # ⚠️ The spelling reader alone justifies the step: a caller spells a name
    # at any step (Q8), with or without the two older switches.
    if not conversion and not verification and not epellation:
        return None
    return LectureAppelantProcessor(
        conversion=conversion,
        verification=verification,
        langue_francaise=langue_agent_francaise(stt_config),
        adresse=adresse,
        etape_courante=etape_courante,
        consigner=consigner,
        variables=variables_commune(run_configs),
        avec_sons=sons_allumes(run_configs),
        voies=voies_allumees(run_configs),
        epellation=epellation,
        variables_ref=variables_reference(run_configs),
        champs_fiche=champs_de_la_fiche(run_configs),
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
            avec_sons=sons_allumes(run_configs),
            voies=voies_allumees(run_configs),
            epellation=epellation_allumee(run_configs),
            variables_ref=variables_reference(run_configs),
            champs_fiche=champs_de_la_fiche(run_configs),
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Caller reading failed on the keyboard, message kept: {erreur!r}")
        return texte
