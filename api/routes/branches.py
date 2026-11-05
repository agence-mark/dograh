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

from fastapi import APIRouter, Depends, HTTPException, Query

from api.db import db_client
from api.db.branches_client import ErreurDeBranche
from api.db.models import UserModel
from api.schemas.branches import (
    ApercuDeFusion,
    ApercuDeMiseAJour,
    BranchesVue,
    ComparaisonVue,
    EpinglerLaPrincipale,
    FusionDemandee,
    MiseAJourDemandee,
    NouvelleBranche,
    ProtectionDemandee,
    RepartitionDemandee,
)
from api.services.auth.depends import get_user_with_selected_organization
from api.services.branches import comparaison, fusion, service

router = APIRouter(tags=["builder-branches"])

CODES_HTTP = {
    "introuvable": 404,
    "nom_pris": 409,
    "sans_brouillon": 409,
    "principale": 409,
    "perime": 409,
    "brouillon_en_attente": 409,
    "sans_version": 409,
    "a_jour": 409,
    "depassee": 409,
    "cote": 422,
}


async def _agent_ou_404(user: UserModel, workflow_id: int):
    agent = await db_client.get_workflow(workflow_id, organization_id=user.selected_organization_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return agent


def _http(erreur: ErreurDeBranche) -> HTTPException:
    return HTTPException(status_code=CODES_HTTP.get(erreur.code, 422), detail=str(erreur))


@router.get("/builder/branches/{workflow_id}/comparer", response_model=ComparaisonVue)
async def comparer_en_duel(
    workflow_id: int,
    gauche: str = Query(description="'branche:<id>' or 'version:<number>'"),
    droite: str = Query(description="'branche:<id>' or 'version:<number>'"),
    jours: int = Query(default=7, ge=1, le=90),
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """Deux branches ou deux versions face à face : part, appels, résolution, transferts, note du juge, coût, latence, et la
    différence de configuration. Lecture seule, chiffres des vrais appels."""
    agent = await _agent_ou_404(user, workflow_id)
    try:
        return await comparaison.comparer(user.selected_organization_id, agent, gauche, droite, jours)
    except ErreurDeBranche as erreur:
        raise _http(erreur) from None


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


# --- fusion et mise à jour (SA-L3c) ---------------------------------------------------------------------------------------------------


@router.get("/builder/branches/{workflow_id}/{branch_id}/fusion", response_model=ApercuDeFusion)
async def apercu_de_la_fusion(workflow_id: int, branch_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    """Ce que la fusion de la branche dans la principale changerait, champ par champ. Aucune écriture."""
    agent = await _agent_ou_404(user, workflow_id)
    try:
        apercu = await fusion.apercu_de_la_fusion(user.selected_organization_id, agent, branch_id)
        apercu["defaisable"] = await fusion.derniere_fusion_defaisable(user.selected_organization_id, agent, branch_id)
        return apercu
    except ErreurDeBranche as erreur:
        raise _http(erreur) from None


@router.post("/builder/branches/{workflow_id}/{branch_id}/fusion")
async def fusionner_une_branche(
    workflow_id: int, branch_id: int, corps: FusionDemandee, user: UserModel = Depends(get_user_with_selected_organization)
):
    """Fusionne la branche dans la principale (une version publiée, la part de trafic reprise, la branche archivée)."""
    from api.services.equipe_mark.acces import journaliser

    agent = await _agent_ou_404(user, workflow_id)
    try:
        resultat = await fusion.fusionner(
            user.selected_organization_id,
            agent,
            branch_id,
            choix=corps.choix,
            relue=corps.relue,
            version_branche=corps.version_branche,
            version_cible=corps.version_cible,
            user=user,
        )
    except ErreurDeBranche as erreur:
        raise _http(erreur) from None
    await journaliser(
        user,
        "agents.branche_fusionnee",
        user.selected_organization_id,
        {"agent": workflow_id, "branche": branch_id, "version": resultat["version"], "relue": corps.relue, "choix": len(corps.choix)},
    )
    return {"ok": True, **resultat}


@router.post("/builder/branches/{workflow_id}/{branch_id}/fusion/defaire")
async def defaire_la_fusion(workflow_id: int, branch_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    """Défait la dernière fusion de cette branche, tant que l'agent n'a pas été publié depuis."""
    from api.services.equipe_mark.acces import journaliser

    agent = await _agent_ou_404(user, workflow_id)
    try:
        resultat = await fusion.defaire_la_fusion(user.selected_organization_id, agent, branch_id)
    except ErreurDeBranche as erreur:
        raise _http(erreur) from None
    await journaliser(user, "agents.fusion_defaite", user.selected_organization_id, {"agent": workflow_id, "branche": branch_id, **resultat})
    return {"ok": True, **resultat}


@router.get("/builder/branches/{workflow_id}/{branch_id}/mise-a-jour", response_model=ApercuDeMiseAJour)
async def apercu_de_la_mise_a_jour(workflow_id: int, branch_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    """Ce que la mise à jour depuis la principale ramènerait dans la branche, champ par champ. Aucune écriture."""
    agent = await _agent_ou_404(user, workflow_id)
    try:
        return await fusion.apercu_de_la_mise_a_jour(user.selected_organization_id, agent, branch_id, user.id)
    except ErreurDeBranche as erreur:
        raise _http(erreur) from None


@router.post("/builder/branches/{workflow_id}/{branch_id}/mise-a-jour")
async def mettre_a_jour_une_branche(
    workflow_id: int, branch_id: int, corps: MiseAJourDemandee, user: UserModel = Depends(get_user_with_selected_organization)
):
    """Ramène les nouveautés de la principale dans le brouillon de la personne sur la branche ; « Revenir avant » la défait."""
    from api.services.equipe_mark.acces import journaliser

    agent = await _agent_ou_404(user, workflow_id)
    try:
        resultat = await fusion.mettre_a_jour(
            user.selected_organization_id,
            agent,
            branch_id,
            user,
            choix=corps.choix,
            base_attendue=corps.base_attendue,
            version_principale=corps.version_principale,
        )
    except ErreurDeBranche as erreur:
        raise _http(erreur) from None
    await journaliser(
        user, "agents.branche_mise_a_jour", user.selected_organization_id, {"agent": workflow_id, "branche": branch_id, "choix": len(corps.choix)}
    )
    return {"ok": True, **resultat}
