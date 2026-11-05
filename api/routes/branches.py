"""[.mark] Partie 3, SA-L3b (05 § 12) : les branches d'agent (``/builder/branches``).

- ``GET  /builder/branches/{agent}``                          les branches, leurs versions, brouillons et parts ;
- ``POST /builder/branches/{agent}``                          crée une branche (0 % du trafic) et le brouillon de son auteur ;
- ``POST /builder/branches/{agent}/{branche}/publier``        le brouillon de la personne devient une version immuable de la branche ;
- ``PUT  /builder/branches/{agent}/repartition``              les parts de toutes les branches (total 100) : le seul mécanisme de part du trafic ;
- ``PUT  /builder/branches/{agent}/principale/version``       la principale sert une version précise (retour en arrière) ou suit de nouveau la publiée.

Tout est lu et écrit AVEC l'organisation de l'utilisateur (un agent ou une branche d'une autre organisation est un 404). Jamais par
une clé d'API pour les gestes de publication (mêmes règles que ``/builder/publication``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.db import db_client
from api.db.branches_client import ErreurDeBranche
from api.db.models import UserModel
from api.schemas.branches import BranchesVue, EpinglerLaPrincipale, NouvelleBranche, ProtectionDemandee, RepartitionDemandee
from api.services.auth.depends import get_user_with_selected_organization
from api.services.branches import service

router = APIRouter(tags=["builder-branches"])

CODES_HTTP = {"introuvable": 404, "nom_pris": 409, "sans_brouillon": 409, "principale": 409}


async def _agent_ou_404(user: UserModel, workflow_id: int):
    agent = await db_client.get_workflow(workflow_id, organization_id=user.selected_organization_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return agent


def _http(erreur: ErreurDeBranche) -> HTTPException:
    return HTTPException(status_code=CODES_HTTP.get(erreur.code, 422), detail=str(erreur))


@router.get("/builder/branches/{workflow_id}", response_model=BranchesVue)
async def lire_les_branches(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    agent = await _agent_ou_404(user, workflow_id)
    try:
        return await service.vue(user.selected_organization_id, agent, user.id)
    except ErreurDeBranche as erreur:
        raise _http(erreur) from None


@router.post("/builder/branches/{workflow_id}")
async def creer_une_branche(workflow_id: int, corps: NouvelleBranche, user: UserModel = Depends(get_user_with_selected_organization)):
    from api.services.equipe_mark.acces import journaliser

    agent = await _agent_ou_404(user, workflow_id)
    try:
        cree = await service.creer(
            user.selected_organization_id,
            agent,
            corps.nom,
            depuis_version=corps.depuis_version,
            user_id=user.id,
            protegee=corps.protegee,
        )
    except ErreurDeBranche as erreur:
        raise _http(erreur) from None
    await journaliser(user, "agents.branche_creee", user.selected_organization_id, {"agent": workflow_id, "branche": cree["id"]})
    return {"ok": True, **cree}


@router.post("/builder/branches/{workflow_id}/{branch_id}/publier")
async def publier_une_branche(workflow_id: int, branch_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    from api.services.equipe_mark.acces import journaliser

    agent = await _agent_ou_404(user, workflow_id)
    try:
        version = await service.publier(user.selected_organization_id, agent, branch_id, user.id)
    except ErreurDeBranche as erreur:
        raise _http(erreur) from None
    await journaliser(
        user,
        "agents.branche_publiee",
        user.selected_organization_id,
        {"agent": workflow_id, "branche": branch_id, "version": version["version_number"]},
    )
    return {"ok": True, **version}


@router.put("/builder/branches/{workflow_id}/repartition")
async def regler_la_repartition(
    workflow_id: int, corps: RepartitionDemandee, user: UserModel = Depends(get_user_with_selected_organization)
):
    from api.services.equipe_mark.acces import journaliser

    agent = await _agent_ou_404(user, workflow_id)
    try:
        resultat = await service.regler_la_repartition(user.selected_organization_id, agent, corps.parts)
    except ErreurDeBranche as erreur:
        raise _http(erreur) from None
    await journaliser(
        user, "agents.repartition_du_trafic", user.selected_organization_id, {"agent": workflow_id, "parts": resultat["parts"]}
    )
    return {"ok": True, **resultat}


@router.put("/builder/branches/{workflow_id}/principale/version")
async def epingler_la_principale(
    workflow_id: int, corps: EpinglerLaPrincipale, user: UserModel = Depends(get_user_with_selected_organization)
):
    from api.services.equipe_mark.acces import journaliser

    agent = await _agent_ou_404(user, workflow_id)
    try:
        resultat = await service.epingler_la_principale(user.selected_organization_id, agent, corps.version)
    except ErreurDeBranche as erreur:
        raise _http(erreur) from None
    await journaliser(user, "agents.principale_epinglee", user.selected_organization_id, {"agent": workflow_id, **resultat})
    return {"ok": True, **resultat}


@router.put("/builder/branches/{workflow_id}/principale/protection")
async def proteger_la_principale(
    workflow_id: int, corps: ProtectionDemandee, user: UserModel = Depends(get_user_with_selected_organization)
):
    """Pose ou lève la protection de la principale (un agent client en ligne reste protégé par la règle). Journalisé."""
    from api.services.equipe_mark.acces import journaliser

    agent = await _agent_ou_404(user, workflow_id)
    try:
        resultat = await service.proteger_la_principale(user.selected_organization_id, agent, corps.protegee)
    except ErreurDeBranche as erreur:
        raise _http(erreur) from None
    await journaliser(user, "agents.principale_protegee", user.selected_organization_id, {"agent": workflow_id, **resultat})
    return {"ok": True, **resultat}
