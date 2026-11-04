"""[.mark] Copier un agent d'une organisation à une autre (U2 quinquies, E58, E33) : exporter du Labo vers un client, ramener d'un client au Labo.

- ``GET  /export-agent/{agent}/cibles?sens=``                les organisations où l'on peut copier (celles que le rôle ouvre), et si la copie existe déjà ;
- ``GET  /export-agent/{agent}/releve?sens=&cible=``         ce que l'agent emporte, une ligne par élément, avec les choix permis ;
- ``POST /export-agent/{agent}/copier``                      la copie, en brouillon, jamais publiée ; rejouée, elle rend la copie déjà faite.

L'organisation de la SOURCE vient de l'adresse (``get_user``), celle de la CIBLE du corps ; les deux sont relues contre ce que le rôle du
compte ouvre à chaque requête (404 sinon). Réservé à l'équipe .mark, par une session : une clé d'API reçoit 403. Permission au registre :
``clients.exporter_ramener``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user
from api.services.builder.constantes import organisation_bibliotheque
from api.services.equipe_mark.acces import acces_de, journaliser, organisation_accessible
from api.services.equipe_mark.espaces import lister_espaces
from api.services.export_agent import ecriture
from api.services.export_agent.modeles import (
    CibleProposee,
    CiblesResponse,
    CompteRendu,
    DemandeCopie,
    ErreurCopie,
    Releve,
    Sens,
)
from api.services.export_agent.releve import construire_le_releve, copie_deja_faite, verifier_le_sens
from api.services.relation.hub import exiger_equipe

router = APIRouter(prefix="/export-agent", tags=["export-agent"])


async def equipe(
    user: UserModel = Depends(get_user),
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> UserModel:
    await exiger_equipe(user, x_api_key)
    return user


def _http(erreur: ErreurCopie) -> HTTPException:
    return HTTPException(status_code=erreur.statut, detail=str(erreur))


async def _cible_ouverte(user: UserModel, cible: int) -> None:
    """La cible doit être une organisation que le rôle du compte ouvre ; sinon elle n'existe pas pour lui."""
    acces = await acces_de(user)
    if not await organisation_accessible(user.id, cible, acces, organisation_bibliotheque()):
        raise HTTPException(status_code=404, detail="Space not found")


@router.get("/{workflow_id}/cibles", response_model=CiblesResponse)
async def cibles(workflow_id: int, sens: Sens = Query(...), user: UserModel = Depends(equipe)) -> CiblesResponse:
    source = user.selected_organization_id
    if await db_client.get_workflow(workflow_id, organization_id=source) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    labo = organisation_bibliotheque()
    visibles = await lister_espaces(user)
    propositions: list[CibleProposee] = []
    for e in visibles:
        try:
            labo = verifier_le_sens(sens, source, e["id"])
        except ErreurCopie:
            continue
        deja = await copie_deja_faite(sens, labo, source, workflow_id, e["id"])
        propositions.append(CibleProposee(id=e["id"], nom=e["nom"], deja_copie=deja))
    return CiblesResponse(sens=sens, cibles=propositions)


@router.get("/{workflow_id}/releve", response_model=Releve)
async def releve(
    workflow_id: int, sens: Sens = Query(...), cible: int = Query(...), user: UserModel = Depends(equipe)
) -> Releve:
    await _cible_ouverte(user, cible)
    try:
        return await construire_le_releve(sens, workflow_id, user.selected_organization_id, cible)
    except ErreurCopie as erreur:
        raise _http(erreur)


@router.post("/{workflow_id}/copier", response_model=CompteRendu)
async def copier(workflow_id: int, corps: DemandeCopie, user: UserModel = Depends(equipe)) -> CompteRendu:
    source = user.selected_organization_id
    await _cible_ouverte(user, corps.cible_organization_id)
    noms = {e["id"]: e["nom"] for e in await lister_espaces(user)}
    try:
        compte = await ecriture.copier(
            user=user, sens=corps.sens, workflow_id=workflow_id, source=source, cible=corps.cible_organization_id,
            nom_de_la_source=noms.get(source, ""), demandes=corps.choix, avec_tests=corps.avec_tests,
        )
    except ErreurCopie as erreur:
        raise _http(erreur)
    await journaliser(
        user,
        "agent.ramener" if corps.sens == "ramener" else "agent.exporter",
        corps.cible_organization_id,
        {
            "source": source, "agent": workflow_id, "copie": compte.agent_id, "deja_copie": compte.deja_copie,
            "elements": len(compte.lignes), "tests": compte.tests_copies, "secrets_retires": compte.secrets_retires,
        },
    )
    return compte

