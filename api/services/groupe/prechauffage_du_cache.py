"""[.mark] agent-facon-tala, C3 bis : préchauffer le cache du prompt des collègues, au début de l'appel.

Mesure du 30/10 : à la passation, le cache du prompt du collègue ne couvrait que 0 à 1 300 jetons sur 4 400,
et la passation qui suit tardait (4 s et plus). Case par agent ``prechauffer_les_collegues``, **éteinte par
défaut** : au début de l'appel, une requête minimale par collègue du groupe (un jeton demandé) qui porte son
prompt d'entrée avec la clé de cache de l'agent (``mark-wf-<id>``, posée par la fabrique de services), pour
que sa vraie première requête retrouve ce début de prompt déjà lu.

- Agnostique du fournisseur : la requête passe par ``run_inference`` du service de modèle de l'agent, comme
  toute requête hors circuit ; un fournisseur sans cache la reçoit comme une requête ordinaire et n'en tire
  rien, sans rien casser. Rien de propre à un fournisseur ici.
- Une requête par collègue et par appel ; jamais bloquante (tâche de fond, délai borné) ; une erreur ne
  coûte jamais l'appel. Aucune parole, aucune écriture dans la conversation.
- Au téléphone elle s'appuie sur le préchargement des collègues (``Precharge``) ; au clavier elle lit les mêmes
  données en base au premier tour (même fonction de départ pour les deux : ``chauffer_un_collegue``).
- Aucun mot de métier : des clés de réglages.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Iterable, Mapping

from loguru import logger

CLE_PRECHAUFFER_COLLEGUES = "prechauffer_les_collegues"
CLE_FICHE_DE_L_APPEL = "prechauffage_du_cache"
DELAI_S = 20.0


def prechauffer_les_collegues_actif(reglages: Mapping[str, Any] | None) -> bool:
    """Faux par défaut ; vrai seulement si la case est allumée (un vrai booléen). ⛔ Ne lève jamais."""
    try:
        return (reglages or {}).get(CLE_PRECHAUFFER_COLLEGUES) is True
    except Exception:  # noqa: BLE001
        return False


async def chauffer_un_collegue(
    engine: Any,
    workflow_id: int,
    graphe: Any,
    user_config: Any,
    *,
    creer_llm: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Une requête d'un jeton avec le prompt d'entrée du collègue ``workflow_id``. Rend la mesure
    ``{"agent_id", "duree_s", "ok"}`` (``erreur`` si elle a échoué). ⛔ Ne lève jamais."""
    mesure: dict[str, Any] = {"agent_id": workflow_id, "ok": False}
    debut = time.monotonic()
    try:
        from pipecat.processors.aggregators.llm_context import LLMContext

        from api.services.pipecat.service_factory import cle_de_cache, create_llm_service
        from api.services.workflow.pipecat_engine_context_composer import (
            compose_system_prompt_for_node,
        )

        noeud = graphe.nodes[graphe.start_node_id]
        systeme = compose_system_prompt_for_node(
            node=noeud,
            workflow=graphe,
            format_prompt=engine._format_prompt,
            has_recordings=engine._has_recordings,
        ).text
        # Le service de modèle de l'agent, avec SA clé de cache : celle que posera sa vraie requête.
        service = (creer_llm or create_llm_service)(
            user_config, prompt_cache_key=cle_de_cache(workflow_id)
        )
        contexte = LLMContext(messages=[{"role": "user", "content": "."}])
        await asyncio.wait_for(
            service.run_inference(contexte, max_tokens=1, system_instruction=systeme),
            timeout=DELAI_S,
        )
        mesure["ok"] = True
    except Exception as erreur:  # noqa: BLE001 -- un préchauffage ne coûte jamais l'appel
        mesure["erreur"] = type(erreur).__name__
        logger.warning(f"[prechauffage] cache du collègue {workflow_id} non chauffé : {erreur!r}")
    mesure["duree_s"] = round(time.monotonic() - debut, 3)
    logger.info(f"[prechauffage] cache du collègue {workflow_id} : {mesure}")
    try:
        engine._gathered_context.setdefault(CLE_FICHE_DE_L_APPEL, []).append(mesure)
    except Exception:  # noqa: BLE001
        pass
    return mesure


async def chauffer_les_collegues(
    engine: Any,
    collegues: Iterable[tuple[int, Any, Any]],
    *,
    creer_llm: Callable[..., Any] | None = None,
) -> list[dict[str, Any]]:
    """Chaque collègue ``(identifiant, graphe, configuration)`` en parallèle, une fois par appel
    (``engine._cache_chauffe``). ⛔ Ne lève jamais."""
    try:
        deja = engine.__dict__.setdefault("_cache_chauffe", set())
        a_faire = [c for c in collegues if c[0] not in deja]
        deja.update(c[0] for c in a_faire)
        if not a_faire:
            return []
        return list(
            await asyncio.gather(
                *(
                    chauffer_un_collegue(engine, i, g, c, creer_llm=creer_llm)
                    for i, g, c in a_faire
                )
            )
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[prechauffage] cache des collègues abandonné : {erreur!r}")
        return []


async def collegues_depuis_la_base(
    engine: Any, fabrique: Any, graphe_du_principal: Any, *, ids_a_exclure: Iterable[int] = ()
) -> list[tuple[int, Any, Any]]:
    """Les collègues du groupe lus en base (clavier : pas de préchargement) : les cibles des outils de
    passation du graphe du principal, leur graphe et la configuration de leur modèle. ⛔ Ne lève jamais."""
    try:
        from api.db import db_client
        from api.services.configuration.ai_model_configuration import (
            get_effective_ai_model_configuration_for_workflow,
        )
        from api.services.groupe.prechauffage import cibles_de_passation, uuids_des_outils
        from api.services.workflow.dto import ReactFlowDTO
        from api.services.workflow.workflow_graph import WorkflowGraph

        organisation = fabrique._organization_id
        outils = await db_client.get_tools_by_uuids(
            uuids_des_outils(graphe_du_principal), organisation
        )
        exclus = set(ids_a_exclure)
        trouves: list[tuple[int, Any, Any]] = []
        for cible in cibles_de_passation(outils):
            if cible in exclus:
                continue
            try:
                _workflow, definition = await fabrique.resolve_destination(cible)
                config = await get_effective_ai_model_configuration_for_workflow(
                    organization_id=organisation,
                    workflow_configurations=definition.workflow_configurations or {},
                )
                if config.llm is None:
                    continue
                graphe = WorkflowGraph(
                    ReactFlowDTO.model_validate(definition.workflow_json),
                    skip_instance_constraints_for={"trigger"},
                )
                trouves.append((cible, graphe, config))
            except Exception as erreur:  # noqa: BLE001 -- un collègue illisible : on passe au suivant
                logger.warning(f"[prechauffage] collègue {cible} non lu pour le cache : {erreur!r}")
        return trouves
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[prechauffage] collègues du cache non lus : {erreur!r}")
        return []
