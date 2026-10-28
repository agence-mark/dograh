"""[.mark] passages-fiables, lot B : l'arbitre du passage d'étape.

Le petit modèle qui parle ne devrait pas être le seul à décider d'un passage (il en saute ou en double une sur trois).
L'arbitre est **un appel séparé**, lancé en même temps que la passe du greffier (dès que la personne a fini de
parler), jamais en le faisant attendre : « sur ce que la personne vient de dire, faut-il prendre une des sorties de
l'étape, et laquelle ? ». Une seule question fermée (``ChoiceQuestion`` de Pipecat) : les portes de l'étape avec leur
description écrite à l'écran, plus l'option « rester dans l'étape ». On ne passe que s'il est sûr (seuil, 0,8 par défaut).

Ce qui est réutilisé de Pipecat 1.12 (R9) : le rendu, le schéma et la lecture du ``LLMClassifier`` (``_render``,
``_schema``, ``_parse``, ``_result``). Ce qui change : son appel passe par le client du service du greffier
(``greffier.interroger``), qui rend les jetons (le coût de l'arbitre est compté à part) et laisse voir un 429 ; le
``run_inference`` de Pipecat ne rend ni l'un ni l'autre. Les contrôles du format garanti du greffier
(``interroger_au_format``) sont ceux d'une fiche : ils ne valent pas ici, le repli est donc fait ici (schéma refusé,
même requête en mode JSON).

Le résultat est lié à la **visite d'étape** où il est né (``engine.jeton_de_visite()``) : le décideur de fin de tour
(``decideur_de_fin_de_tour.py``) jette toute décision arrivée sous un autre jeton.

Erreur, délai (3 s), JSON illisible, 429 : **rien ne se passe**, c'est tracé. L'appel ne paie jamais pour l'arbitre.
Consigne générique : aucun mot de métier (les étapes, portes et descriptions sont des données).
⛔ Ne lève jamais.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from loguru import logger

from api.services.fiche.traces import CLE_TOUR
from api.services.groupe.passations import est_la_note_de_passation, est_un_resultat_de_travail
from pipecat.classifiers.base_classifier import ChoiceQuestion, ClassifierError
from pipecat.classifiers.llm.classifier import DEFAULT_INSTRUCTIONS, LLMClassifier

CLE_ARBITRE = "arbitre"
CLE_DESACCORDS = "desaccords_arbitre"
USAGE_ARBITRE = "arbitre"
RESTER = "rester_dans_l_etape"
NOM_DE_LA_QUESTION = "passage"
SEUIL_PAR_DEFAUT = 0.8
DELAI_PAR_DEFAUT = 3.0
NOMBRE_D_ECHANGES = 10
LONGUEUR_MAX_DU_TEXTE = 1500
LONGUEUR_MAX_D_UN_MESSAGE = 600

# La consigne au modèle (jamais dite à l'appelant) : générique, aucun mot de métier.
CONSIGNE = (
    "Tu es l'arbitre du passage d'une étape à l'autre d'une conversation entre un agent et une personne. "
    "Tu lis l'étape en cours, les derniers échanges et les sorties possibles. Tu dis si la conversation appelle "
    "maintenant une de ces sorties, et laquelle. Choisis une sortie seulement si ce que la personne vient de dire "
    "ou de faire la demande clairement. Dans le doute, ou si l'étape n'a pas fini son travail, choisis de rester "
    "dans l'étape. Ne réponds jamais à la place de l'agent."
)

# Les états d'une décision.
ETAT_OK, ETAT_DELAI, ETAT_ERREUR, ETAT_ILLISIBLE, ETAT_429, ETAT_SANS_CERVEAU = (
    "ok",
    "delai",
    "erreur",
    "illisible",
    "429",
    "sans_cerveau",
)


class ArbitreEnEchec(ClassifierError):
    """Une défaillance de l'arbitre, avec son état tracé."""

    def __init__(self, etat: str, message: str = ""):
        super().__init__(message or etat)
        self.etat = etat


@dataclass
class Decision:
    """La réponse de l'arbitre, liée à la visite d'étape où elle est née."""

    jeton: tuple
    etat: str = ETAT_OK
    choix: str | None = None
    confiance: float = 0.0
    jetons: dict = field(default_factory=dict)
    duree: float = 0.0

    @property
    def veut_passer(self) -> bool:
        return self.etat == ETAT_OK and bool(self.choix) and self.choix != RESTER


class ClassifieurDeLArbitre(LLMClassifier):
    """``LLMClassifier`` dont l'appel passe par le client du service du greffier (jetons comptés, 429 visible)."""

    def __init__(self, *, service: Any, delai: float = DELAI_PAR_DEFAUT):
        super().__init__(llm=service, instructions=f"{CONSIGNE}\n\n{DEFAULT_INSTRUCTIONS}", timeout=delai)
        self.jetons: dict = {}

    @property
    def model(self) -> str | None:
        modele = getattr(getattr(self._llm, "_settings", None), "model", None)
        return modele if isinstance(modele, str) else None

    async def _requete(self, message: str, schema: dict) -> tuple[str | None, dict]:
        from api.services.pipecat.greffier import _refus_du_format, interroger

        try:
            return await interroger(self._llm, self._instructions, message, schema=schema)
        except Exception as erreur:  # noqa: BLE001 -- seul un refus du format se rattrape
            if not _refus_du_format(erreur):
                raise
            logger.warning(f"[arbitre] format garanti refusé ({type(erreur).__name__}) : mode JSON")
            return await interroger(self._llm, self._instructions, message)

    async def _ask(self, state, questions):  # type: ignore[override]
        from api.services.pipecat.greffier import est_un_429

        message = self._render(state, questions)
        try:
            reponse, jetons = await asyncio.wait_for(self._requete(message, self._schema(questions)), self._timeout)
        except (TimeoutError, asyncio.TimeoutError) as erreur:
            raise ArbitreEnEchec(ETAT_DELAI) from erreur
        except Exception as erreur:  # noqa: BLE001
            raise ArbitreEnEchec(ETAT_429 if est_un_429(erreur) else ETAT_ERREUR, type(erreur).__name__) from erreur
        self.jetons = jetons or {}
        try:
            reponses = self._parse(reponse or "")
            if len(questions) == 1 and not any(nom in reponses for nom in questions):
                reponses = {next(iter(questions)): reponses}
            resultats = {}
            for nom, question in questions.items():
                brut = reponses.get(nom)
                if not isinstance(brut, dict):
                    raise ClassifierError(f"no answer for {nom!r}")
                resultats[nom] = self._result(question, brut)
        except ClassifierError as erreur:
            raise ArbitreEnEchec(ETAT_ILLISIBLE, "illisible") from erreur
        return resultats, None


# ---------------------------------------------------------------------------------------------------------
# Ce que l'arbitre lit
# ---------------------------------------------------------------------------------------------------------


def _texte_d_un_message(message: dict) -> str:
    contenu = message.get("content")
    if isinstance(contenu, str):
        return contenu.strip()
    if isinstance(contenu, list):
        return " ".join(
            str(p.get("text") or "") for p in contenu if isinstance(p, dict) and p.get("type") in (None, "text")
        ).strip()
    return ""


def derniers_echanges(messages: Iterable[Any], nombre: int = NOMBRE_D_ECHANGES) -> list[tuple[str, str]]:
    """Les ``nombre`` derniers échanges lus dans la conversation : (rôle, texte), appelant et agent seulement. Ni
    consigne, ni résultat d'outil, ni note du code."""
    lignes: list[tuple[str, str]] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in ("user", "assistant"):
            continue
        if message["role"] == "user" and (est_un_resultat_de_travail(message) or est_la_note_de_passation(message)):
            continue
        texte = _texte_d_un_message(message)
        if texte:
            lignes.append((message["role"], texte[:LONGUEUR_MAX_D_UN_MESSAGE]))
    return lignes[-nombre:]


def question_de_l_etape(noeud: Any) -> tuple[ChoiceQuestion, dict[str, str]]:
    """La question fermée : les portes de l'étape (avec la description écrite à l'écran, ``condition`` de la porte)
    plus « rester ». Rend aussi la table option -> nom de la porte."""
    options: dict[str, Any] = {}
    portes: dict[str, str] = {}
    for arete in getattr(noeud, "out_edges", None) or ():
        nom = arete.get_function_name()
        options[nom] = f"{arete.label} : {arete.condition}".strip()
        portes[nom] = nom
    cle = RESTER
    while cle in options:
        cle += "_"
    options[cle] = "Aucune de ces sorties n'est appelée pour l'instant : l'étape continue."
    question = ChoiceQuestion(
        instructions="Quelle sortie de l'étape la conversation appelle-t-elle maintenant, s'il y en a une ?",
        options=options,
    )
    return question, portes


def etat_a_juger(noeud: Any, echanges: list[tuple[str, str]]) -> str:
    """Le texte de l'étape et les derniers échanges, tels que l'arbitre les lit."""
    prompt = str(getattr(noeud, "prompt", None) or "").strip()[:LONGUEUR_MAX_DU_TEXTE]
    lignes = [f"{'Personne' if role == 'user' else 'Agent'} : {texte}" for role, texte in echanges]
    return f"Étape en cours : {getattr(noeud, 'name', '')}\n{prompt}\n\nDerniers échanges :\n" + "\n".join(lignes)


# ---------------------------------------------------------------------------------------------------------
# L'arbitre d'un appel
# ---------------------------------------------------------------------------------------------------------


class ArbitreDuPassage:
    """Lance l'appel de l'arbitre au moment où la personne a fini de parler, garde la tâche liée au jeton de la visite
    d'étape, rend la décision à la demande du décideur de fin de tour."""

    def __init__(self, engine: Any):
        self._engine = engine
        self._tache: asyncio.Task | None = None
        self._jeton: tuple | None = None
        self._portes: dict[str, str] = {}
        self._decision: Decision | None = None

    def _service(self) -> Any:
        moteur = self._engine
        service = getattr(moteur, "arbitre_service", None)
        if service is None:
            service = getattr(getattr(moteur, "greffier", None), "_service", None)
        if service is None:
            service = getattr(getattr(moteur, "active_agent", None), "llm", None)
        return service

    def lancer(self, jeton: tuple, noeud: Any, messages: Iterable[Any], *, delai: float = DELAI_PAR_DEFAUT) -> bool:
        """Part en parallèle ; ne bloque jamais. Rend ``True`` si une demande est partie. ⛔ Ne lève jamais."""
        try:
            self._jeton, self._decision = None, None
            if noeud is None or not (getattr(noeud, "out_edges", None) or ()):
                return False
            question, portes = question_de_l_etape(noeud)
            echanges = derniers_echanges(messages)
            if not echanges:
                return False
            service = self._service()
            self._jeton, self._portes, self._decision = jeton, portes, None
            if service is None:
                self._decision = Decision(jeton=jeton, etat=ETAT_SANS_CERVEAU)
                self._tache = None
                return False
            etat = etat_a_juger(noeud, echanges)
            self._tache = asyncio.get_running_loop().create_task(self._demander(jeton, service, etat, question, delai))
            self._engine.notes_en_cours.add(self._tache)
            self._tache.add_done_callback(self._engine.notes_en_cours.discard)
            return True
        except Exception as erreur:  # noqa: BLE001 -- l'arbitre ne coûte jamais l'appel
            logger.warning(f"[arbitre] non lancé : {erreur!r}")
            return False

    async def _demander(self, jeton: tuple, service: Any, etat: str, question: ChoiceQuestion, delai: float) -> None:
        debut = time.monotonic()
        classifieur = ClassifieurDeLArbitre(service=service, delai=delai)
        decision = Decision(jeton=jeton)
        try:
            resultats = await classifieur.choice(etat, {NOM_DE_LA_QUESTION: question})
            resultat = resultats[NOM_DE_LA_QUESTION]
            decision.choix = self._portes.get(resultat.choice) if resultat.choice in self._portes else RESTER
            decision.confiance = float(resultat.confidence)
        except ArbitreEnEchec as erreur:
            decision.etat = erreur.etat
        except asyncio.CancelledError:
            raise
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[arbitre] en échec : {type(erreur).__name__}")
            decision.etat = ETAT_ERREUR
        decision.jetons = dict(classifieur.jetons)
        decision.duree = round(time.monotonic() - debut, 3)
        self._verser(service, decision.jetons)
        self._decision = decision
        if decision.etat == ETAT_429:
            logger.warning("[arbitre] 429 : l'arbitre se tait pour ce tour")

    def _verser(self, service: Any, jetons: dict) -> None:
        """Le coût de l'arbitre, à part (``arbitre``) dans le coût de l'appel. ⛔ Ne lève jamais."""
        try:
            if not jetons:
                return
            from api.services.pipecat.greffier import versement_du_cout

            versement_du_cout(self._engine, USAGE_ARBITRE, service)(
                jetons.get("jetons_entree"), jetons.get("jetons_sortie")
            )
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[arbitre] coût non versé : {erreur!r}")

    async def resultat(self, jeton: tuple) -> Decision | None:
        """La décision née sous ``jeton`` (attendue si elle est en route, au plus son délai), ou ``None`` : aucune
        demande n'est partie pour cette visite. ⛔ Ne lève jamais."""
        try:
            if self._jeton != jeton:
                return None
            if self._tache is not None and not self._tache.done():
                await asyncio.shield(self._tache)
            return self._decision
        except asyncio.CancelledError:
            raise
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[arbitre] décision illisible : {erreur!r}")
            return None

    def oublier(self) -> None:
        self._jeton, self._decision = None, None


def tracer(moteur: Any, **entree: Any) -> None:
    """Une ligne de plus dans ``arbitre`` (fiche de l'appel). ⛔ Ne lève jamais."""
    try:
        fiche = getattr(moteur, "_gathered_context", None)
        if isinstance(fiche, dict):
            fiche.setdefault(CLE_ARBITRE, []).append({"tour": fiche.get(CLE_TOUR), **entree})
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[arbitre] trace non écrite : {erreur!r}")


def tracer_un_desaccord(moteur: Any, **entree: Any) -> None:
    """L'agent et l'arbitre ne sont pas d'accord : tracé pour la file de tri (lot G). ⛔ Ne lève jamais."""
    try:
        fiche = getattr(moteur, "_gathered_context", None)
        if isinstance(fiche, dict):
            fiche.setdefault(CLE_DESACCORDS, []).append({"tour": fiche.get(CLE_TOUR), **entree})
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[arbitre] désaccord non écrit : {erreur!r}")
