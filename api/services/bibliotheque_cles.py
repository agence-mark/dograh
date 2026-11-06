"""[.mark] La bibliothèque de clés (chantier direct-et-passe-muette, lot 0, P15, P16) : ce qui la
distingue des autres identifiants de Dograh, et où une clé sert encore.

Une clé de la bibliothèque est un identifiant ``bearer_token`` du coffre de Dograh dont les
données portent son fournisseur et la marque ``mark_bibliotheque``. La route est
``api/routes/cles.py``.
"""

from typing import Literal, Optional

from pydantic import BaseModel

from api.db import db_client
from api.enums import OrganizationConfigurationKey
from api.services.appel_simule import reglages as reglages_simules
from api.services.cles_reference import MARQUE, reference_de
from api.services.configuration.ai_model_configuration import (
    get_organization_ai_model_configuration_v2,
)
from api.services.configuration.registry import ServiceProviders

# P19 : tous les fournisseurs de Dograh, ceux que propose « Models ».
# [.mark] l-agent-travaille, L4 : plus deux secrets qui ne sont pas des clés de modèle, choisis
# par référence comme les autres (A4 mot de passe du serveur de mail, A7 secret du workflow
# sur mesure). Ni « Models » ni un agent ne les proposent : seulement « Après l'appel ».
FOURNISSEURS_HORS_MODELES: tuple[str, ...] = ("smtp", "webhook")
FOURNISSEURS: tuple[str, ...] = (
    tuple(p.value for p in ServiceProviders) + FOURNISSEURS_HORS_MODELES
)
Fournisseur = Literal[FOURNISSEURS]  # type: ignore[valid-type]


class Usage(BaseModel):
    """Un endroit où la clé sert encore ; l'écran le traduit (``nom`` : outil ou agent)."""

    ou: Literal[
        "reglages_modele",
        "reglages_voix",
        "outil",
        "agent",
        "modeles_organisation",
        "modeles_agent",
        "apres_appel",
    ]
    nom: Optional[str] = None


# fiabilite-orchestration, lot 10 (F10) : « Protocole » est le menu d'avant (clé ``fournisseur`` des
# données, inchangée) ; « Fournisseur » est un texte libre (``nom_fournisseur``) et l'adresse du
# fournisseur (``adresse``) est rattachée à la clé. Une clé d'avant n'a ni l'un ni l'autre.
CLE_NOM_FOURNISSEUR = "nom_fournisseur"
CLE_ADRESSE = "adresse"
NOM_FOURNISSEUR_MAX = 80


def donnees_d_une_cle(
    fournisseur,
    cle: str,
    nom_fournisseur: Optional[str] = None,
    adresse: Optional[str] = None,
) -> dict:
    """Les données rangées d'une clé. Sans fournisseur libre ni adresse : exactement celles d'avant."""
    valeur = getattr(fournisseur, "value", fournisseur)
    donnees = {"token": cle, "fournisseur": valeur, MARQUE: True}
    if nom_fournisseur:
        donnees[CLE_NOM_FOURNISSEUR] = nom_fournisseur
    if adresse:
        donnees[CLE_ADRESSE] = adresse
    return donnees


def nom_fournisseur_de(identifiant) -> Optional[str]:
    valeur = (identifiant.credential_data or {}).get(CLE_NOM_FOURNISSEUR)
    return valeur if isinstance(valeur, str) and valeur else None


def adresse_de(identifiant) -> Optional[str]:
    valeur = (identifiant.credential_data or {}).get(CLE_ADRESSE)
    return valeur if isinstance(valeur, str) and valeur else None


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


async def _lire_les_endroits_ou_une_cle_sert(organization_id: int) -> dict:
    """Tout ce qui peut désigner une clé, lu UNE fois pour l'organisation (V2b : le tableau des clés demande
    les usages de toutes les clés d'un coup, jamais une lecture complète par clé)."""
    return {
        "reglages": await reglages_simules.lire_reglages(organization_id),
        "outils": [
            (outil.name, str(outil.definition or {}))
            for outil in await db_client.get_tools_for_organization(organization_id)
        ],
        "apres_appel": str(
            getattr(
                await db_client.get_configuration(
                    organization_id, OrganizationConfigurationKey.APRES_APPEL.value
                ),
                "value",
                None,
            )
            or {}
        ),
        "modeles": await get_organization_ai_model_configuration_v2(organization_id),
        "agents": [
            (
                agent.name,
                str(
                    getattr(
                        getattr(agent, "current_definition", None), "workflow_json", None
                    )
                    or {}
                ),
                (
                    str(getattr(agent, "workflow_configurations", None) or {}),
                    str(
                        getattr(
                            getattr(agent, "current_definition", None),
                            "workflow_configurations",
                            None,
                        )
                        or {}
                    ),
                ),
            )
            for agent in await db_client.get_all_workflows(
                organization_id=organization_id
            )
        ],
    }


def _usages_dans(uuid: str, donnees: dict) -> list[Usage]:
    reference = reference_de(uuid)
    usages: list[Usage] = []
    reglages = donnees["reglages"]
    if uuid in {reglages.appelant.identifiant, reglages.juge.identifiant}:
        usages.append(Usage(ou="reglages_modele"))
    if reglages.voix.identifiant == uuid:
        usages.append(Usage(ou="reglages_voix"))
    for nom, definition in donnees["outils"]:
        if uuid in definition:
            usages.append(Usage(ou="outil", nom=nom))
    # [.mark] L4 : la clé de la synthèse, le mot de passe du serveur de mail, le secret du webhook.
    if reference in donnees["apres_appel"]:
        usages.append(Usage(ou="apres_appel"))
    modeles = donnees["modeles"]
    if modeles is not None and reference in modeles.model_dump_json():
        usages.append(Usage(ou="modeles_organisation"))
    for nom, definition, configurations in donnees["agents"]:
        if uuid in definition:
            usages.append(Usage(ou="agent", nom=nom))
        if any(reference in c for c in configurations):
            usages.append(Usage(ou="modeles_agent", nom=nom))
    return usages


async def usages_de(uuid: str, organization_id: int) -> list[Usage]:
    """Où la clé sert encore dans l'organisation : les réglages de l'appelant simulé, les outils,
    la configuration de modèle de l'organisation (« Models »), et pour chaque agent sa version
    courante (récupération avant l'appel, webhook) et ses réglages de modèle (P23)."""
    return _usages_dans(uuid, await _lire_les_endroits_ou_une_cle_sert(organization_id))


async def usages_de_toutes(
    uuids: list[str], organization_id: int
) -> dict[str, list[Usage]]:
    """V2b : les usages de plusieurs clés avec UNE seule lecture de l'organisation (tableau des clés)."""
    donnees = await _lire_les_endroits_ou_une_cle_sert(organization_id)
    return {uuid: _usages_dans(uuid, donnees) for uuid in uuids}
