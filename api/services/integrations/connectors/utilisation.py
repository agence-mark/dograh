"""[.mark] Lot F6 de cloture-code-avant-migration : « utilisé par » d'un logiciel connecté.

Calculé à l'affichage, jamais stocké : les outils de l'organisation (type ``integration``) disent
quel connecteur ils appellent ; le catalogue dit quel logiciel (``integration``) est derrière ce
connecteur. Un logiciel utilisé par aucun outil rend une liste vide. Aucun mot de métier : des noms
d'outils venus de la configuration.
"""

from __future__ import annotations

from api.db import db_client
from api.enums import ToolCategory
from api.services.integrations.connectors.catalogue import connecteur


async def outils_par_logiciel(organization_id: int) -> dict[str, list[dict]]:
    """``{logiciel (clé d'intégration Nango): [{tool_uuid, nom}]}`` pour les outils actifs de CETTE
    organisation (les outils archivés ne comptent pas)."""
    sortie: dict[str, list[dict]] = {}
    outils = await db_client.get_tools_for_organization(
        organization_id, category=ToolCategory.INTEGRATION.value
    )
    for outil in outils:
        config = ((outil.definition or {}).get("config")) or {}
        c = connecteur(str(config.get("connecteur") or ""))
        if c is None or c.interne:
            continue
        sortie.setdefault(c.integration, []).append(
            {"tool_uuid": outil.tool_uuid, "nom": outil.name}
        )
    return sortie
