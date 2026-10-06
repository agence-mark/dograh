"""[.mark] La bibliothèque de clés (chantier direct-et-passe-muette, lot 0, P15, P16) : ce qui la
distingue des autres identifiants de Dograh, et où une clé sert encore.

Une clé de la bibliothèque est un identifiant ``bearer_token`` du coffre de Dograh dont les
données portent son fournisseur et la marque ``mark_bibliotheque``. La route est
``api/routes/cles.py``.
"""

from typing import Literal, Optional

from pydantic import BaseModel

from api.db import db_client
from api.services.appel_simule import reglages as reglages_simules
from api.services.cles_reference import MARQUE, reference_de
from api.services.configuration.ai_model_configuration import (
    get_organization_ai_model_configuration_v2,
)
from api.services.configuration.registry import ServiceProviders

# P19 : tous les fournisseurs de Dograh, ceux que propose « Models ».
Fournisseur = ServiceProviders
FOURNISSEURS: tuple[str, ...] = tuple(p.value for p in ServiceProviders)


class Usage(BaseModel):
    """Un endroit où la clé sert encore ; l'écran le traduit (``nom`` : outil ou agent)."""

    ou: Literal[
        "reglages_modele",
        "reglages_voix",
        "outil",
        "agent",
        "modeles_organisation",
        "modeles_agent",
    ]
    nom: Optional[str] = None


def donnees_d_une_cle(fournisseur, cle: str) -> dict:
    valeur = getattr(fournisseur, "value", fournisseur)
    return {"token": cle, "fournisseur": valeur, MARQUE: True}


def fournisseur_de(identifiant) -> Optional[str]:
    """Le fournisseur d'un identifiant de la bibliothèque, ``None`` pour tout autre identifiant."""
    donnees = identifiant.credential_data or {}
    if not donnees.get(MARQUE):
        return None
    fournisseur = donnees.get("fournisseur")
    return fournisseur if fournisseur in FOURNISSEURS else None


def nom_apres_suppression(nom: str, uuid: str) -> str:
    """Le coffre de Dograh supprime en douceur et garde l'unicité (organisation, nom) sur les
    lignes supprimées : la ligne change de nom avant d'être supprimée, pour que le nom se
    réutilise (une clé révoquée remplacée sous le même nom)."""
    return f"{nom} · deleted {uuid[:8]}"


async def usages_de(uuid: str, organization_id: int) -> list[Usage]:
    """Où la clé sert encore dans l'organisation : les réglages de l'appelant simulé, les outils,
    la configuration de modèle de l'organisation (« Models »), et pour chaque agent sa version
    courante (récupération avant l'appel, webhook) et ses réglages de modèle (P23)."""
    reference = reference_de(uuid)
    usages: list[Usage] = []
    reglages = await reglages_simules.lire_reglages(organization_id)
    if uuid in {reglages.appelant.identifiant, reglages.juge.identifiant}:
        usages.append(Usage(ou="reglages_modele"))
    if reglages.voix.identifiant == uuid:
        usages.append(Usage(ou="reglages_voix"))
    for outil in await db_client.get_tools_for_organization(organization_id):
        if uuid in str(outil.definition or {}):
            usages.append(Usage(ou="outil", nom=outil.name))
    modeles = await get_organization_ai_model_configuration_v2(organization_id)
    if modeles is not None and reference in modeles.model_dump_json():
        usages.append(Usage(ou="modeles_organisation"))
    for agent in await db_client.get_all_workflows(organization_id=organization_id):
        version = agent.current_definition
        definition = getattr(version, "workflow_json", None)
        if uuid in str(definition or {}):
            usages.append(Usage(ou="agent", nom=agent.name))
        configurations = (
            str(getattr(agent, "workflow_configurations", None) or {}),
            str(getattr(version, "workflow_configurations", None) or {}),
        )
        if any(reference in c for c in configurations):
            usages.append(Usage(ou="modeles_agent", nom=agent.name))
    return usages
