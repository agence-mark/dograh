"""[.mark] Lot H : rejouer un test (ou une suite) sur une COPIE d'agent, par la session clavier.

Chaque essai crée un run clavier sur l'agent visé, y pose un tour déjà « joué » dont le point de reprise
porte l'historique, l'étape et la fiche du test (``checkpoint_after_turn``, que ``text_chat_runner`` relit
comme après un vrai tour), puis envoie la réplique de la personne et lit ce que le tour a produit. Même
moteur, mêmes portes, même greffier que le banc clavier : c'est le but.

Ce que ça ne fait pas : la fin de conversation (extraction, webhooks, tâches d'après appel) ne tourne pas ;
le run d'essai est marqué terminé sans elle. Les outils de la copie d'agent, eux, sont les siens.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from api.db import db_client
from api.enums import WorkflowRunMode, WorkflowRunState
from api.services.tests_rejouables.modele import (
    ESSAIS_PAR_DEFAUT,
    ErreurTestRejouable,
    Observation,
    TestRejouable,
    evaluer,
    lire_test,
    refuser_si_protege,
)
from api.services.workflow.run_creation import (
    definition_to_run,
    prepare_workflow_run_inputs,
)
from api.services.workflow.text_chat_runner import (
    TEXT_CHAT_CHECKPOINT_VERSION,
    _serialize_text_chat_checkpoint_messages,
)
from api.services.workflow.text_chat_session_service import (
    append_text_chat_user_message,
    default_text_chat_session_data,
    execute_pending_text_chat_turn,
)


@dataclass
class Essai:
    numero: int
    reussi: bool
    detail: str = ""
    observe: dict[str, Any] = field(default_factory=dict)
    erreur: str | None = None
    run_id: int | None = None


@dataclass
class ResultatTest:
    # Pas collectée par pytest.
    __test__ = False

    nom: str
    agent_id: int
    essais: list[Essai] = field(default_factory=list)
    erreur: str | None = None  # le test n'a pas pu être joué (fichier illisible, refus)

    @property
    def reussis(self) -> int:
        return sum(1 for e in self.essais if e.reussi)

    @property
    def taux(self) -> str:
        return f"{self.reussis}/{len(self.essais)}"

    @property
    def vert(self) -> bool:
        return self.erreur is None and bool(self.essais) and self.reussis == len(self.essais)


def _noeuds(definition: Any) -> dict[str, str]:
    """identifiant d'étape → nom, dans la définition jouée."""
    sortie: dict[str, str] = {}
    for n in ((getattr(definition, "workflow_json", None) or {}).get("nodes") or []):
        if isinstance(n, dict) and n.get("id") is not None:
            sortie[str(n["id"])] = str((n.get("data") or {}).get("name") or "")
    return sortie


def _resoudre_l_etape(test: TestRejouable, noeuds: dict[str, str]) -> str | None:
    """L'identifiant de l'étape de reprise dans l'agent visé (None : sa première étape)."""
    if not test.etape:
        return None
    voulu_id, voulu_nom = test.etape.get("id"), test.etape.get("nom")
    if voulu_id is not None and str(voulu_id) in noeuds:
        return str(voulu_id)
    pareils = [i for i, n in noeuds.items() if voulu_nom and n == voulu_nom]
    if len(pareils) == 1:
        return pareils[0]
    raise ErreurTestRejouable(
        f"l'étape {voulu_nom or voulu_id!r} du test est "
        f"{'ambiguë' if pareils else 'introuvable'} dans l'agent visé (ce n'est pas une copie de l'agent du run ?)"
    )


def _point_de_reprise(test: TestRejouable, etape_id: str | None) -> dict[str, Any]:
    messages = [{"role": m["role"], "content": m["texte"]} for m in test.historique]
    return {
        "version": TEXT_CHAT_CHECKPOINT_VERSION,
        "anchor_turn_id": "turn_restaure",
        "current_node_id": etape_id,
        "messages": _serialize_text_chat_checkpoint_messages(messages),
        "gathered_context": dict(test.fiche),
        "tool_state": {},
    }


def _observer(tour: dict[str, Any], noeuds: dict[str, str]) -> Observation:
    obs = Observation(texte=((tour.get("assistant_message") or {}).get("text") or "").strip())
    noms_par_id: dict[str, str] = {}
    for ev in tour.get("events") or []:
        p = ev.get("payload") or {}
        if ev.get("type") == "tool_call_started":
            obs.outils.append({"nom": p.get("function_name"), "arguments": p.get("arguments") or {}})
        elif ev.get("type") == "node_transition":
            nom = p.get("node_name") or noeuds.get(str(p.get("node_id")), "")
            obs.etapes_traversees.append(nom)
            if p.get("node_id") is not None:
                noms_par_id[str(p["node_id"])] = nom
    obs.etape_id = (tour.get("checkpoint_after_turn") or {}).get("current_node_id")
    if obs.etape_id is not None:
        obs.etape_nom = noms_par_id.get(str(obs.etape_id)) or noeuds.get(str(obs.etape_id)) or None
    return obs


async def _un_essai(
    test: TestRejouable, workflow: Any, definition: Any, etape_id: str | None, numero: int
) -> Essai:
    noeuds = _noeuds(definition)
    run_id: int | None = None
    try:
        entrees = await prepare_workflow_run_inputs(
            db_client,
            workflow,
            initial_context={},
            use_draft=True,
            include_template_context=True,
        )
        run = await db_client.create_workflow_run(
            name=f"REJEU-{test.nom}-{numero}"[:120],
            workflow_id=workflow.id,
            mode=WorkflowRunMode.TEXTCHAT.value,
            user_id=workflow.user_id,
            initial_context=entrees.initial_context,
            gathered_context=dict(test.fiche),
            organization_id=workflow.organization_id,
            definition_id=entrees.definition_id,
            use_draft=entrees.use_draft,
        )
        run_id = run.id
        await db_client.update_workflow_run(
            run_id,
            annotations={"tester": {"source": "test_rejouable", "modality": "text", "test": test.nom}},
        )
        point = _point_de_reprise(test, etape_id)
        tour_restaure = {
            "id": "turn_restaure",
            "status": "completed",
            "created_at": datetime.now(UTC).isoformat(),
            "user_message": None,
            "assistant_message": None,
            "events": [],
            "usage": {},
            "checkpoint_after_turn": point,
        }
        donnees = default_text_chat_session_data()
        donnees["turns"] = [tour_restaure]
        donnees["status"] = "idle"
        await db_client.ensure_workflow_run_text_session(
            run_id, session_data=donnees, checkpoint=point
        )
        session = await db_client.get_workflow_run_text_session(
            run_id, organization_id=workflow.organization_id
        )
        session = await append_text_chat_user_message(
            run_id=run_id,
            text_session=session,
            user_text=test.replique,
            expected_revision=session.revision,
        )
        session = await execute_pending_text_chat_turn(
            workflow_id=workflow.id, run_id=run_id, text_session=session
        )
        tour = (session.session_data or {}).get("turns", [])[-1]
        obs = _observer(tour, noeuds)
        reussi, detail = evaluer(test.critere, obs)
        return Essai(numero, reussi, detail, obs.en_json(), run_id=run_id)
    except Exception as e:  # noqa: BLE001 -- un essai en erreur compte comme raté, avec sa cause
        logger.warning(f"[tests-rejouables] essai {numero} de {test.nom} en erreur : {e!r}")
        return Essai(numero, False, "essai en erreur", erreur=f"{type(e).__name__}: {e}", run_id=run_id)
    finally:
        if run_id is not None:
            try:
                await db_client.update_workflow_run(
                    run_id, is_completed=True, state=WorkflowRunState.COMPLETED.value
                )
            except Exception:  # noqa: BLE001
                logger.debug(f"[tests-rejouables] run {run_id} non clos")


async def rejouer(
    test: TestRejouable, agent_id: int, essais: int = ESSAIS_PAR_DEFAUT
) -> ResultatTest:
    """Rejoue ``test`` ``essais`` fois sur l'agent ``agent_id`` (une copie). Lève ``ErreurTestRejouable``
    pour un refus (agent protégé, autre organisation, étape introuvable)."""
    refuser_si_protege(agent_id)
    if essais < 1:
        raise ErreurTestRejouable("au moins un essai")
    workflow = await db_client.get_workflow_by_id(agent_id)
    if workflow is None:
        raise ErreurTestRejouable(f"agent {agent_id} introuvable")
    if test.organisation_id is not None and workflow.organization_id != test.organisation_id:
        raise ErreurTestRejouable(
            f"agent {agent_id} refusé : le test {test.nom!r} est celui de l'organisation "
            f"{test.organisation_id}, l'agent est d'une autre"
        )
    definition = await definition_to_run(db_client, workflow, use_draft=True)
    if definition is None:
        raise ErreurTestRejouable(f"agent {agent_id} sans définition à jouer")
    etape_id = _resoudre_l_etape(test, _noeuds(definition))
    resultat = ResultatTest(nom=test.nom, agent_id=agent_id)
    for n in range(1, essais + 1):
        resultat.essais.append(await _un_essai(test, workflow, definition, etape_id, n))
    return resultat


async def jouer_suite(
    dossier: Path | str, agent_id: int, essais: int = ESSAIS_PAR_DEFAUT
) -> list[ResultatTest]:
    """Tous les ``*.json`` du dossier, dans l'ordre des noms. Un fichier illisible ou un test refusé est
    rendu avec son erreur, les autres sont joués. Un agent protégé refuse toute la suite d'emblée."""
    refuser_si_protege(agent_id)
    dossier = Path(dossier)
    if not dossier.is_dir():
        raise ErreurTestRejouable(f"{dossier} n'est pas un dossier")
    fichiers = sorted(dossier.glob("*.json"))
    if not fichiers:
        raise ErreurTestRejouable(f"aucun test (*.json) dans {dossier}")
    sortie: list[ResultatTest] = []
    for f in fichiers:
        try:
            sortie.append(await rejouer(lire_test(f), agent_id, essais))
        except ErreurTestRejouable as e:
            sortie.append(ResultatTest(nom=f.stem, agent_id=agent_id, erreur=str(e)))
    return sortie


def rendre(resultats: list[ResultatTest]) -> str:
    lignes: list[str] = []
    for r in resultats:
        if r.erreur:
            lignes.append(f"[ERREUR] {r.nom} : {r.erreur}")
            continue
        lignes.append(f"[{'OK' if r.vert else 'ROUGE'}] {r.nom} : {r.taux} (agent {r.agent_id})")
        for e in r.essais:
            marque = "ok " if e.reussi else "raté"
            lignes.append(f"    essai {e.numero} {marque} : {e.erreur or e.detail}" + (f" (run {e.run_id})" if e.run_id else ""))
    if len(resultats) > 1:
        verts = sum(1 for r in resultats if r.vert)
        lignes.append(f"Suite : {verts}/{len(resultats)} test(s) à 100 %.")
    return "\n".join(lignes)
