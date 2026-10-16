"""[.mark] Chantier agents-specialises (lot 2) : la fabrique d'agents du clavier.

Au téléphone, chaque agent tourne dans un sous-circuit à lui (voix comprise) sous le circuit
de l'appel. Au clavier, il n'y a ni voix ni circuit d'appel : chaque tour reconstruit un
moteur sur le graphe de l'agent actif. Cette fabrique **réutilise**
``AgentRuntimeFactory.resolve_destination`` (même organisation, même version que l'appel :
brouillon si l'essai joue un brouillon) et construit l'agent **sans voix ni sous-circuit** :
seul son modèle compte. La bascule elle-même (outil ``transfer_agent``, note ou historique,
``commit_agent``) est celle du téléphone, à l'identique.

Après la bascule, l'ouverture de l'agent appelé n'est pas jouée dans le circuit du tour (son
modèle n'y est pas) : le moteur la met de côté (``ouverture_differee``) et le clavier la joue
dans un passage suivant, sur le graphe du nouvel agent.
"""

from __future__ import annotations

from typing import Any, Callable

from loguru import logger

from api.services.pipecat.agent_runtime_factory import AgentRuntimeFactory
from api.services.pipecat.service_factory import cle_de_cache, create_llm_service
from api.services.workflow.agent_runtime import AgentRuntime, new_visit_id
from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.workflow_graph import WorkflowGraph


class TextAgentFactory(AgentRuntimeFactory):
    """Construit un agent de l'appel au clavier : son graphe et son modèle, rien d'autre."""

    def __init__(
        self,
        *,
        organization_id: int,
        workflow_run_id: int,
        use_draft: bool,
        mps_correlation_id: str | None = None,
        creer_llm: Callable[..., Any] = create_llm_service,
    ):
        self._creer_llm = creer_llm
        super().__init__(
            organization_id=organization_id,
            workflow_run_id=workflow_run_id,
            call_worker=None,  # type: ignore[arg-type] -- aucun circuit d'appel au clavier
            audio_config=None,
            callbacks_factory=lambda _visit: None,  # type: ignore[arg-type,return-value]
            use_draft=use_draft,
            mps_correlation_id=mps_correlation_id,
        )

    async def build(
        self, *, workflow_id: int, visit_id: str | None = None
    ) -> AgentRuntime:
        visit_id = visit_id or new_visit_id()
        workflow, definition = await self.resolve_destination(workflow_id)
        run_configs = definition.workflow_configurations or {}

        from api.services.configuration.ai_model_configuration import (
            get_effective_ai_model_configuration_for_workflow,
        )

        user_config = await get_effective_ai_model_configuration_for_workflow(
            organization_id=self._organization_id,
            workflow_configurations=run_configs,
        )
        if user_config.llm is None:
            from api.services.pipecat.agent_runtime_factory import AgentBuildError

            raise AgentBuildError(
                "destination_without_llm",
                f"Workflow {workflow_id} has no LLM configured",
            )
        graphe = WorkflowGraph(
            ReactFlowDTO.model_validate(definition.workflow_json),
            skip_instance_constraints_for={"trigger"},
        )
        llm = self._creer_llm(
            user_config,
            correlation_id=self._mps_correlation_id,
            prompt_cache_key=cle_de_cache(workflow_id),
        )
        logger.info(
            f"[passation] clavier : agent {workflow_id} ({workflow.name}) "
            f"définition {definition.id} prêt"
        )
        return AgentRuntime(
            visit_id=visit_id,
            workflow_id=workflow_id,
            definition_id=definition.id,
            workflow_name=workflow.name,
            workflow=graphe,
            llm=llm,
            inference_llm=llm,
            variable_extraction_llm=llm,
            user_config=user_config,
            runtime_configuration={
                "llm_provider": user_config.llm.provider,
                "llm_model": user_config.llm.model,
            },
            is_child=False,
            entered_at=None,
            reglages=dict(run_configs),
        )

    async def attach(self, runtime: AgentRuntime) -> None:  # noqa: D401
        """Rien à attacher : au clavier, l'agent n'a pas de sous-circuit."""
        return None
