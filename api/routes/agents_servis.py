"""[.mark] Les agents que l'organisation sert, pour le portail (chantier agents-specialises, lot 9 ; M9, M10,
D89, D90, A13, C7).

- ``GET /organizations/agents-servis`` : par agent, son nom, sa version publiée, ses numéros, sa fiche, les
  agents qu'il peut appeler et ceux qui l'appellent, ses capacités ; par groupe (un principal et ses
  spécialisés), qui appelle qui et les capacités de l'ensemble. Tout est lu dans Dograh.
- ``PUT /organizations/agents-servis/rattachement`` : .mark rattache (ou détache) des agents au portail ;
  rattacher un principal rattache ses spécialisés avec lui (A13). Écrit dans la base du client rattachée à
  l'organisation (``agent.rattache_le``), jamais ailleurs.

Toutes les routes lisent et écrivent DANS l'organisation de l'utilisateur ou de la clé d'API (C7) : la clé
d'une autre organisation ne voit rien, l'absence de clé est refusée par l'authentification.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from api.db.bases_clients.connexion import BaseClientIndisponible, connecter
from api.db.models import UserModel
from api.schemas.agents_servis import (
    AgentsServis,
    DemandeRattachement,
    ResultatRattachement,
)
from api.services.auth.depends import get_user_with_selected_organization
from api.services.base_client import rattachement
from api.services.groupe.agents_servis import lire_agents_servis, membres_a_rattacher

router = APIRouter(prefix="/organizations/agents-servis", tags=["organizations"])


async def _rattaches(organization_id: int) -> set[int]:
    """Les agents rattachés au portail ; sans base du client, ou base injoignable : aucun (une lecture
    ne tombe jamais pour cela)."""
    nom = await rattachement.nom_de_la_base(organization_id)
    if not nom:
        return set()
    try:
        connexion = await connecter(nom)
    except BaseClientIndisponible as erreur:
        logger.warning(
            f"[.mark] Attached agents of organization {organization_id} not read: {erreur}"
        )
        return set()
    try:
        from api.db.bases_clients.traces import agents_rattaches

        return await agents_rattaches(connexion)
    finally:
        await connexion.close()


@router.get("", response_model=AgentsServis)
async def get_agents_servis(
    user: UserModel = Depends(get_user_with_selected_organization),
):
    organization_id = user.selected_organization_id
    return await lire_agents_servis(organization_id, await _rattaches(organization_id))


@router.put("/rattachement", response_model=ResultatRattachement)
async def put_rattachement(
    request: DemandeRattachement,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """Attach (or detach) agents to the portal. An agent that is not this organization's is refused
    (404) whatever else the request says; a principal brings its specialised agents with it."""
    from api.db.bases_clients.traces import ecrire_agent_site, regler_rattachement

    organization_id = user.selected_organization_id
    nom_base = await rattachement.nom_de_la_base(organization_id)
    if not nom_base:
        raise HTTPException(
            status_code=409,
            detail="Attach a client database first: the attachment lives there.",
        )
    servis = await lire_agents_servis(organization_id)
    connus = {a.id: a for a in servis.agents}
    inconnus = [i for i in request.workflow_ids if i not in connus]
    if inconnus:
        # Tenant isolation: the id of another organization's agent is the same answer as no agent.
        raise HTTPException(status_code=404, detail="Agent not found")
    concernes = membres_a_rattacher(servis, request.workflow_ids)
    try:
        connexion = await connecter(nom_base)
    except BaseClientIndisponible as erreur:
        raise HTTPException(
            status_code=503, detail=f"{erreur} Nothing was changed."
        ) from None
    try:
        changes = await regler_rattachement(
            connexion, {i: connus[i].nom for i in concernes}, request.rattache
        )
        if request.rattache:
            # agent_site follows the agent's choice, so the portal knows which establishment each
            # attached agent serves (M3).
            for i in concernes:
                await ecrire_agent_site(
                    connexion,
                    dograh_workflow_id=i,
                    nom=connus[i].nom,
                    site_cle=connus[i].etablissement_id,
                )
    finally:
        await connexion.close()
    return ResultatRattachement(
        rattaches=changes if request.rattache else [],
        detaches=[] if request.rattache else changes,
        agents=concernes,
    )
