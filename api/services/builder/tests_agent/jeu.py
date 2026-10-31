"""[.mark] Builder, lot 6 : jouer un test (N × 3, B12) sur le chemin texte existant.

Deux sortes de tests, un seul verdict (``verdict.py``) :

* **réplique** (tiré d'un appel) : l'historique et l'étape sont restaurés, la réplique de la personne est rejouée UN tour
  (``tests_rejouables.rejeu``, le même moteur et les mêmes portes que le clavier) ;
* **conversation libre** (écrit à la main ou par le builder depuis la fiche) : un APPELANT SIMULÉ joue un personnage de la
  bibliothèque (B32) face à l'agent, tour par tour, jusqu'à la fin de l'appel ou ``tours_max``. Porté de la méthode du labo
  (``jouer-13-libre``), sans rien de propre à un client : le personnage et le but sont des DONNÉES du test.

Dans les deux cas les outils sortants de la copie sont simulés et figés (``CLE_REJEU``, B42) : rien ne part vers le système du
client. Le cerveau de l'appelant est injecté (``Appelant``) : les tests passent un cerveau factice, rien n'est dépensé.

L'ouverture d'une session et un tour de l'agent sont isolés dans ``Moteur`` (deux fonctions) : c'est la seule couture avec la
base et le modèle de l'agent, remplaçable dans les tests. ⛔ Zéro vocabulaire métier.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from loguru import logger

from api.services.builder.cerveau.appel import Cerveau, ErreurCerveau
from api.services.builder.tests_agent import verdict
from api.services.builder.tests_agent.verdict import ObservationConversation

TOURS_MAX_PAR_DEFAUT = 12
TOURS_MAX_ABSOLU = 40
ADIEUX = ("au revoir", "bonne journee", "bonne soiree", "a bientot", "bye", "goodbye")


# --- l'appelant simulé ---------------------------------------------------------------------------------------------------


class Appelant(Protocol):
    async def repondre(self, lignes: list[tuple[str, str]]) -> str: ...


def consigne_de_l_appelant(personnage: dict[str, Any], scenario: dict[str, Any]) -> str:
    """Le prompt de l'appelant : une base générique (parler comme au téléphone, ne jouer QUE l'appelant), puis le personnage
    (description, but, fin, comportements) et ce que le scénario donne à savoir. Rien de propre à un métier."""
    from api.schemas.appel_simule import CONSIGNE_APPELANT

    morceaux = [
        CONSIGNE_APPELANT,
        "Tu ne joues QUE l'appelant : jamais l'agent, jamais de didascalie, jamais de guillemets, jamais de commentaire sur le jeu. "
        "Tu ne donnes que ce qu'on te demande, sans anticiper, sauf si ta fiche dit de donner deux informations d'un coup. "
        "Si l'agent se répète ou te redemande ce que tu as déjà dit, tu réagis comme une vraie personne.",
    ]
    if personnage.get("description"):
        morceaux.append(f"Qui tu es : {personnage['description']}")
    comportements = [str(c) for c in personnage.get("comportements") or []]
    if comportements:
        morceaux.append("Comportement : " + " ; ".join(comportements))
    but = scenario.get("but") or personnage.get("but")
    if but:
        morceaux.append(f"Ce que tu veux : {but}")
    if scenario.get("role"):
        morceaux.append(f"Ce que tu sais : {scenario['role']}")
    fin = personnage.get("fin")
    morceaux.append(f"Comment tu termines : {fin}" if fin else "Quand tu as obtenu ce que tu voulais et qu'on te demande s'il y a autre chose, tu dis non et au revoir.")
    return "\n\n".join(morceaux)


async def completer(cerveau: Cerveau, systeme: str, messages: list[dict[str, Any]]) -> str:
    """Un message de texte du cerveau (sans outils)."""
    texte = ""
    async for evenement in cerveau.tour(systeme=systeme, messages=messages, outils=[]):
        if evenement.get("type") == "texte":
            texte += evenement["texte"]
    return texte.strip().strip('"«» ')


@dataclass
class AppelantParCerveau:
    cerveau: Cerveau
    consigne: str

    async def repondre(self, lignes: list[tuple[str, str]]) -> str:
        # L'appelant voit l'agent comme « user » et ses propres répliques comme « assistant ».
        messages = [{"role": "assistant" if r == "moi" else "user", "content": t or "(silence)"} for r, t in lignes]
        if not messages or messages[0]["role"] != "user":
            messages.insert(0, {"role": "user", "content": "(l'agent décroche)"})
        try:
            texte = await completer(self.cerveau, self.consigne, messages)
        except ErreurCerveau:
            return "Pardon, vous pouvez répéter ?"
        return texte or "Pardon, vous pouvez répéter ?"


async def personnage_de(scenario: dict[str, Any]) -> dict[str, Any]:
    """Le personnage du scénario : en ligne, ou celui de la bibliothèque (famille « personnages-appelant », B32)."""
    if isinstance(scenario.get("personnage_en_ligne"), dict):
        return scenario["personnage_en_ligne"]
    slug = scenario.get("personnage")
    if not slug:
        return {}
    from api.services.builder.bibliotheque import service

    element = await service.element_ou_none("personnages-appelant", str(slug))
    return dict(element.courante.contenu) if element else {}


# --- la couture avec le moteur ------------------------------------------------------------------------------------------------


@dataclass
class Session:
    run_id: int | None
    noeuds_de_fin: set[str] = field(default_factory=set)
    etat: Any = None


@dataclass
class TourAgent:
    texte: str
    termine: bool = False


@dataclass
class Moteur:
    """Ouvrir une session sur l'agent (rend aussi l'ouverture dite par l'agent) ; jouer un tour ; lire et clore."""

    ouvrir: Callable[[Any, dict[str, Any]], Awaitable[tuple[Session, TourAgent]]]
    tour: Callable[[Session, str], Awaitable[TourAgent]]
    lire: Callable[[Session], Awaitable[ObservationConversation]]
    clore: Callable[[Session], Awaitable[None]]


def termine_par_adieux(texte: str) -> bool:
    n = verdict.normaliser(texte)
    return any(a in n for a in ADIEUX)


async def jouer_une_conversation(
    workflow: Any, test: dict[str, Any], appelant: Appelant, moteur: Moteur, *, tours_max: int | None = None
) -> ObservationConversation:
    """Une conversation complète ; l'observation est relue DANS LE JOURNAL du run (parité avec l'appel simulé)."""
    scenario = test.get("scenario") or {}
    maxi = max(1, min(int(tours_max or scenario.get("tours_max") or TOURS_MAX_PAR_DEFAUT), TOURS_MAX_ABSOLU))
    session, ouverture = await moteur.ouvrir(workflow, test)
    lignes: list[tuple[str, str]] = []
    if ouverture.texte:
        lignes.append(("agent", ouverture.texte))
    termine = ouverture.termine
    a_dire = str(scenario.get("ouverture") or "").strip()
    try:
        for _ in range(maxi):
            if termine:
                break
            if not a_dire:
                a_dire = await appelant.repondre(lignes)
            lignes.append(("moi", a_dire))
            reponse = await moteur.tour(session, a_dire)
            if reponse.texte:
                lignes.append(("agent", reponse.texte))
            termine = reponse.termine
            if not termine and termine_par_adieux(a_dire) and termine_par_adieux(reponse.texte):
                break
            a_dire = ""
        return await moteur.lire(session)
    finally:
        try:
            await moteur.clore(session)
        except Exception:  # noqa: BLE001 -- un run non clos ne fait pas échouer le test
            logger.debug("[tests-agent] run d'essai non clos")


# --- le vrai moteur : le chemin texte existant --------------------------------------------------------------------------------


def moteur_texte() -> Moteur:
    """Le chemin clavier du fork (``text_chat_session_service``), outils sortants simulés (``CLE_REJEU``)."""
    from api.db import db_client
    from api.enums import WorkflowRunMode, WorkflowRunState
    from api.services.tests_rejouables.simulation import CLE_REJEU
    from api.services.workflow.run_creation import definition_to_run, prepare_workflow_run_inputs
    from api.services.workflow.text_chat_logs import build_text_chat_realtime_feedback_events
    from api.services.workflow.text_chat_session_service import (
        append_text_chat_user_message,
        default_text_chat_checkpoint,
        default_text_chat_session_data,
        execute_pending_text_chat_turn,
        initialize_text_chat_session,
    )

    def dit(session_data: dict[str, Any]) -> tuple[str, bool]:
        tours = session_data.get("turns") or []
        message = (tours[-1].get("assistant_message") or {}).get("text") if tours else None
        return (message or "").strip(), session_data.get("status") == "completed"

    async def ouvrir(workflow: Any, test: dict[str, Any]) -> tuple[Session, TourAgent]:
        entrees = await prepare_workflow_run_inputs(
            db_client, workflow, initial_context=dict((test.get("scenario") or {}).get("contexte") or {}), use_draft=True, include_template_context=True
        )
        run = await db_client.create_workflow_run(
            name=f"TEST-{test.get('slug', 'test')}"[:120],
            workflow_id=workflow.id,
            mode=WorkflowRunMode.TEXTCHAT.value,
            user_id=workflow.user_id,
            initial_context=entrees.initial_context,
            gathered_context={CLE_REJEU: True},
            organization_id=workflow.organization_id,
            definition_id=entrees.definition_id,
            use_draft=entrees.use_draft,
        )
        await db_client.update_workflow_run(run.id, annotations={"tester": {"source": "test_agent", "modality": "text", "test": test.get("slug")}})
        definition = await definition_to_run(db_client, workflow, use_draft=True)
        fins = {
            str(n["id"])
            for n in ((getattr(definition, "workflow_json", None) or {}).get("nodes") or [])
            if isinstance(n, dict) and n.get("type") == "endCall"
        }
        texte_session = await db_client.ensure_workflow_run_text_session(
            run.id, session_data=default_text_chat_session_data(), checkpoint=default_text_chat_checkpoint()
        )
        texte_session = await initialize_text_chat_session(run_id=run.id, text_session=texte_session)
        texte_session = await execute_pending_text_chat_turn(workflow_id=workflow.id, run_id=run.id, text_session=texte_session)
        session = Session(run.id, fins, etat={"texte": texte_session, "workflow": workflow})
        texte, termine = dit(texte_session.session_data)
        return session, TourAgent(texte, termine)

    async def tour(session: Session, texte: str) -> TourAgent:
        s = session.etat["texte"]
        s = await append_text_chat_user_message(run_id=session.run_id, text_session=s, user_text=texte, expected_revision=s.revision)
        s = await execute_pending_text_chat_turn(workflow_id=session.etat["workflow"].id, run_id=session.run_id, text_session=s)
        session.etat["texte"] = s
        message, termine = dit(s.session_data)
        return TourAgent(message, termine)

    async def lire(session: Session) -> ObservationConversation:
        s = session.etat["texte"]
        journal = build_text_chat_realtime_feedback_events(s.session_data)
        gathered = await _contexte_du_run(session.run_id, s.workflow_run.workflow.organization_id)
        return verdict.observation_depuis_un_run(journal, gathered, session.noeuds_de_fin)

    async def clore(session: Session) -> None:
        await db_client.update_workflow_run(session.run_id, is_completed=True, state=WorkflowRunState.COMPLETED.value)

    return Moteur(ouvrir, tour, lire, clore)


async def _contexte_du_run(run_id: int | None, organisation_id: int) -> dict[str, Any]:
    from api.db import db_client

    try:
        run, _ = await db_client.get_workflow_run_with_context(run_id)
        return dict(getattr(run, "gathered_context", None) or {})
    except Exception:  # noqa: BLE001
        return {}
