"""[.mark] Partie 3, SA-L3d (décision 21) : épingler la version de chaque outil dans une version d'agent.

Fonctions à passer une SESSION ouverte (elles servent les clients de la couche de données, jamais une route). Règle unique :
une version d'agent ne suit JAMAIS seule une nouvelle version d'un outil (un outil touche un vrai logiciel) ; elle joue la version
qu'elle a figée, jusqu'à ce qu'une personne passe à la nouvelle dans le brouillon, la teste et la publie.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from api.db.models import ToolModel, WorkflowDefinitionModel


# Clôture, lot B (D17) : la même colonne porte aussi la version de chaque bloc réutilisable (clé ``bloc:<slug>``). Tout code qui lit
# les épingles comme ``{tool_uuid: numéro}`` passe par ``sans_blocs`` ; les blocs se lisent par ``seulement_blocs``.
PREFIXE_BLOC = "bloc:"


def sans_blocs(epingles: Any) -> dict[str, int]:
    """Les épingles d'OUTILS seulement (les clés ``bloc:`` sont ignorées)."""
    return {u: n for u, n in (copie(epingles) or {}).items() if not u.startswith(PREFIXE_BLOC)}


def seulement_blocs(epingles: Any) -> dict[str, int]:
    """``{slug: version}`` des blocs épinglés (sans le préfixe)."""
    return {u[len(PREFIXE_BLOC):]: n for u, n in (copie(epingles) or {}).items() if u.startswith(PREFIXE_BLOC)}


def uuids_du_graphe(graphe: Any) -> list[str]:
    """Les identifiants d'outils posés sur les étapes d'un graphe (dictionnaire de l'éditeur), dans l'ordre, sans doublon."""
    vus: list[str] = []
    noeuds = graphe.get("nodes") if isinstance(graphe, dict) else None
    for noeud in noeuds or []:
        donnees = noeud.get("data") if isinstance(noeud, dict) else None
        for u in (donnees or {}).get("tool_uuids") or []:
            if isinstance(u, str) and u not in vus:
                vus.append(u)
    return vus


def copie(epingles: Any) -> dict[str, int] | None:
    """Une copie propre des épingles d'une version (ou ``None``) : un brouillon créé depuis une version part de ses épingles."""
    if not isinstance(epingles, dict) or not epingles:
        return None
    return {str(u): n for u, n in epingles.items() if isinstance(n, int) and not isinstance(n, bool)}


async def versions_courantes(session, organization_id: int, uuids: list[str]) -> dict[str, int]:
    """``{uuid: version courante}`` des outils de CETTE organisation (un identifiant inconnu ou d'une autre organisation n'y est pas)."""
    if not uuids:
        return {}
    lignes = await session.execute(
        select(ToolModel.tool_uuid, ToolModel.version_courante).where(
            ToolModel.tool_uuid.in_(uuids), ToolModel.organization_id == organization_id
        )
    )
    return {u: v for u, v in lignes.all()}


async def figer(
    session,
    definition: WorkflowDefinitionModel,
    organization_id: int,
    *,
    choix: dict[str, int] | None = None,
    garder_les_blocs: bool = False,
) -> dict[str, int] | None:
    """Fige les épingles d'une version qu'on PUBLIE : pour chaque outil cité par son graphe, la version déjà épinglée (ou celle de
    ``choix``), sinon la version courante au moment de publier. Une épingle d'un outil que le graphe ne cite plus est retirée.

    Clôture, lot B (D17) : les blocs réutilisables sans ``@vN`` sont épinglés à la dernière Recette quand leur mode effectif est
    « figer » (réglage du bloc, sinon de l'agent, sinon figé si l'agent est protégé). ``garder_les_blocs`` (la fusion) garde ceux de
    ``choix`` et ne complète que les blocs qui n'en ont pas."""
    uuids = uuids_du_graphe(definition.workflow_json)
    courantes = await versions_courantes(session, organization_id, uuids)
    acquises = sans_blocs(choix) or sans_blocs(definition.outils_epingles)
    epingles = {u: acquises.get(u) or courantes[u] for u in uuids if u in courantes}
    epingles.update(await _epingles_de_blocs(session, definition, choix if garder_les_blocs else None))
    definition.outils_epingles = epingles or None
    return definition.outils_epingles


async def _epingles_de_blocs(session, definition: WorkflowDefinitionModel, gardees: dict[str, int] | None) -> dict[str, int]:
    from api.db import protection_principale
    from api.services.etiquettes_prompt import blocs_modes

    configurations = definition.workflow_configurations if isinstance(definition.workflow_configurations, dict) else {}
    protegee = False
    if definition.workflow_id is not None:
        protegee = await protection_principale.est_protegee(session, definition.workflow_id)
    posees = await blocs_modes.epingles_a_la_publication(definition.workflow_json, configurations, protegee)
    if gardees is not None:
        posees.update({f"{PREFIXE_BLOC}{s}": n for s, n in seulement_blocs(gardees).items() if f"{PREFIXE_BLOC}{s}" in posees})
    return posees
