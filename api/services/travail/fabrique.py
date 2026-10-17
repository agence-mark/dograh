"""[.mark] Lot 4 d'orchestrateur-trois-cerveaux (D10) : le service de modèle du cerveau de fond.

Même fabrique que le cerveau de conversation et que le greffier (``create_llm_service``) : tout
fournisseur, l'API Responses comprise (lot 1). Le modèle du fond est CHOISI LIBREMENT à l'écran,
fournisseur compris ; le code ne le contraint jamais. Seul effet : un bloc vide veut dire « le
cerveau de conversation de l'agent » (clé comprise).

Construit AVANT le worker, comme le greffier avant le moteur : s'il ne se construit pas, l'agent
est joué SANS cerveau de fond (jamais un appel cassé), et le journal le dit.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.services.pipecat.greffier import (
    configuration_d_un_cerveau_annexe,
    resoudre_le_bloc_annexe,
)
from api.services.travail.reglages import CLE_LLM, USAGE_TRAVAIL, ReglagesTravail

# L'estampille du modèle du fond dans la configuration de l'agent (fournisseur et modèle, jamais la clé).
CLE_ESTAMPILLE = "travail_modele"


def configuration_du_travail(user_config: Any, bloc: dict | None) -> Any:
    """La configuration de modèle du cerveau de fond : celle de la conversation, à laquelle son
    bloc s'applique comme une surcharge de modèle. Bloc vide : exactement la conversation."""
    return configuration_d_un_cerveau_annexe(
        user_config, bloc, objet="background brain", nom_du_reglage="Background model"
    )


async def resoudre_le_bloc_du_travail(
    run_configs: dict | None, organization_id: int | None
) -> dict | None:
    """Le bloc ``travail_llm`` dont la clé est une référence de la bibliothèque, rendu avec la
    vraie clé (une copie : ``run_configs`` n'est jamais modifié). Ne lève jamais."""
    return await resoudre_le_bloc_annexe(
        run_configs, organization_id, CLE_LLM, "background brain"
    )


def service_du_travail(
    reglages: ReglagesTravail,
    run_configs: dict | None,
    user_config: Any,
    *,
    correlation_id: str | None = None,
) -> tuple[Any, dict | None]:
    """Le service de modèle du cerveau de fond et son estampille, ou ``(None, None)`` si le
    travail est éteint. Lève si le service ne se construit pas (l'appelant joue alors l'agent
    sans cerveau de fond)."""
    if not reglages.actif:
        return None, None
    from api.services.pipecat.service_factory import create_llm_service

    configuration = configuration_du_travail(user_config, (run_configs or {}).get(CLE_LLM))
    service = create_llm_service(
        configuration, correlation_id=correlation_id, usage_context=USAGE_TRAVAIL
    )
    return service, {
        "provider": configuration.llm.provider,
        "model": configuration.llm.model,
    }


async def preparer_le_service_du_travail(
    run_configs: dict | None,
    user_config: Any,
    organization_id: int | None,
    runtime_configuration: dict | None,
    *,
    correlation_id: str | None = None,
) -> tuple[ReglagesTravail | None, Any]:
    """Les réglages et le service du cerveau de fond d'un agent, ou ``(None, None)`` : éteint,
    ou service impossible à construire (journalisé, l'agent est joué sans). Pose l'estampille
    ``travail_modele`` dans ``runtime_configuration``. ⛔ Ne lève jamais."""
    reglages = ReglagesTravail.depuis(run_configs)
    if not reglages.actif:
        return None, None
    try:
        service, estampille = service_du_travail(
            reglages,
            await resoudre_le_bloc_du_travail(run_configs, organization_id),
            user_config,
            correlation_id=correlation_id,
        )
    except Exception as erreur:  # noqa: BLE001 -- l'agent part sans cerveau de fond
        logger.error(
            "[travail] modèle du cerveau de fond impossible à construire, agent joué "
            f"sans travail en arrière-plan : {type(erreur).__name__}"
        )
        return None, None
    if estampille is not None and runtime_configuration is not None:
        runtime_configuration[CLE_ESTAMPILLE] = estampille
    return reglages, service
