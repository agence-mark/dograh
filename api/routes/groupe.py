"""[.mark] Chantier agents-specialises, lot 10 (A9, A10) : les routes d'un groupe d'agents.

Un groupe = un agent principal + ses spécialisés, rangés dans un sous-dossier. Les routes
d'orchestration (créer, retirer, archiver, publier, lire) vivent ici ; la logique est dans
``services/groupe/groupe.py``. Toute route filtre par ``organization_id`` de l'appelant.
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from api.db import db_client
from api.db.models import UserModel
from api.routes.workflow import publier_un_agent
from api.services.auth.depends import get_user
from api.services.groupe import groupe as service

router = APIRouter(prefix="/workflow")


class NomRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def nettoyer(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty")
        return v


class CreerPrincipalRequest(NomRequest):
    # Le dossier dans lequel le groupe prend son sous-dossier (absent : premier niveau).
    folder_id: int | None = None


class CreerPrincipalResponse(BaseModel):
    workflow_id: int
    folder_id: int


class CreerSpecialiseResponse(BaseModel):
    workflow_id: int


class MembreDuGroupe(BaseModel):
    id: int
    name: str
    cerveau_propre: bool = False
    folder_id: int | None = None
    status: str | None = None


class PrincipalDuGroupe(BaseModel):
    id: int
    name: str
    folder_id: int | None = None


class GroupeResponse(BaseModel):
    principal: PrincipalDuGroupe | None = None
    agent_principal_id: int | None = None
    specialises: list[MembreDuGroupe] = []


class LienDeGroupe(BaseModel):
    id: int
    role: str  # "principal" ou "specialise"
    agent_principal_id: int | None = None
    agents_specialises: list[int] = []
    cerveau_propre: bool = False


class LiensDesGroupesResponse(BaseModel):
    agents: list[LienDeGroupe] = []


class ArchiverPrincipalRequest(BaseModel):
    # « garder » : les spécialisés restent comme agents seuls ; « archiver » : avec lui.
    specialises: str = "garder"


class AgentPublie(BaseModel):
    id: int
    name: str
    version_number: int | None = None


class Refus(BaseModel):
    id: int
    name: str
    detail: str


class PublierGroupeResponse(BaseModel):
    publies: list[AgentPublie] = []
    deja_a_jour: list[int] = []
    refus: Refus | None = None


def _vers_http(erreur: service.GroupeError) -> HTTPException:
    return HTTPException(status_code=erreur.status_code, detail=str(erreur))


def _detail(e: HTTPException) -> str:
    detail = e.detail
    if isinstance(detail, str):
        return detail
    try:
        return json.dumps(detail, ensure_ascii=False)[:2000]
    except Exception:  # noqa: BLE001
        return str(detail)


@router.get("/groupes")
async def lire_les_groupes(
    user: UserModel = Depends(get_user),
) -> LiensDesGroupesResponse:
    """Les agents actifs de l'organisation qui sont dans un groupe, avec leur rôle (liste d'agents)."""
    liens = await service.liens_des_groupes(user.selected_organization_id)
    return LiensDesGroupesResponse(agents=[LienDeGroupe(**lien) for lien in liens])


@router.post("/groupe")
async def creer_un_groupe(
    request: CreerPrincipalRequest, user: UserModel = Depends(get_user)
) -> CreerPrincipalResponse:
    """Crée l'agent principal d'un nouveau groupe et son sous-dossier (carte « Graphe avec
    agents spécialisés » de la modale de création)."""
    try:
        workflow_id, folder_id = await service.creer_principal(
            nom=request.name,
            organization_id=user.selected_organization_id,
            user_id=user.id,
            dossier_parent_id=request.folder_id,
        )
    except service.GroupeError as e:
        raise _vers_http(e)
    return CreerPrincipalResponse(workflow_id=workflow_id, folder_id=folder_id)


@router.post("/{workflow_id}/groupe/specialise")
async def creer_un_specialise(
    workflow_id: int, request: NomRequest, user: UserModel = Depends(get_user)
) -> CreerSpecialiseResponse:
    """Crée un spécialisé du groupe de ce principal (graphe minimal, clés communes copiées,
    rangé dans le sous-dossier, outil de passation posé chez le principal)."""
    try:
        nouveau = await service.creer_specialise(
            principal_id=workflow_id,
            nom=request.name,
            organization_id=user.selected_organization_id,
            user_id=user.id,
        )
    except service.GroupeError as e:
        raise _vers_http(e)
    return CreerSpecialiseResponse(workflow_id=nouveau)


@router.get("/{workflow_id}/groupe")
async def lire_un_groupe(
    workflow_id: int, user: UserModel = Depends(get_user)
) -> GroupeResponse:
    """Le groupe de cet agent (principal ou spécialisé) ; un agent seul rend un groupe vide."""
    groupe = await service.lire_groupe(workflow_id, user.selected_organization_id)
    if groupe is None:
        if (
            await db_client.get_workflow(
                workflow_id, organization_id=user.selected_organization_id
            )
            is None
        ):
            raise HTTPException(
                status_code=404, detail=f"Workflow with id {workflow_id} not found"
            )
        return GroupeResponse()
    return GroupeResponse(**groupe)


@router.post("/{workflow_id}/groupe/retirer")
async def retirer_un_specialise(
    workflow_id: int, user: UserModel = Depends(get_user)
) -> dict[str, bool]:
    """Retire un spécialisé de son groupe : il redevient un agent seul."""
    try:
        await service.retirer_du_groupe(
            specialise_id=workflow_id, organization_id=user.selected_organization_id
        )
    except service.GroupeError as e:
        raise _vers_http(e)
    return {"success": True}


@router.post("/{workflow_id}/groupe/archiver")
async def archiver_un_principal(
    workflow_id: int,
    request: ArchiverPrincipalRequest,
    user: UserModel = Depends(get_user),
) -> dict[str, list[int]]:
    """Archive un principal et dit quoi faire de ses spécialisés (les garder, ou les archiver)."""
    try:
        touches = await service.archiver_principal(
            principal_id=workflow_id,
            organization_id=user.selected_organization_id,
            specialises=request.specialises,
        )
    except service.GroupeError as e:
        raise _vers_http(e)
    return {"specialises": touches}


@router.post("/{workflow_id}/groupe/completer")
async def completer_le_groupe(
    workflow_id: int, user: UserModel = Depends(get_user)
) -> dict[str, list[str]]:
    """Complète le groupe de ce principal (D6, orchestrateur-trois-cerveaux) : un nœud de fin pour
    chaque collègue, une étape de retour pour l'accueil, prompts « à rédiger avec Evan ». Rien n'est
    retiré ni réécrit ; le résultat reste en brouillon (la publication est un geste à part). Rend,
    par identifiant d'agent, ce qui a été ajouté (vide : rien à faire)."""
    try:
        rendu = await service.completer_le_groupe(workflow_id, user.selected_organization_id)
    except service.GroupeError as e:
        raise _vers_http(e)
    return {str(agent_id): ajouts for agent_id, ajouts in rendu.items()}


@router.post("/{workflow_id}/groupe/publier")
async def publier_le_groupe(
    workflow_id: int, user: UserModel = Depends(get_user)
) -> PublierGroupeResponse:
    """Publie tout le groupe, agent par agent (spécialisés d'abord, le principal en dernier),
    et s'arrête au premier refus en le disant. Un agent sans brouillon est déjà à jour."""
    organisation = user.selected_organization_id
    groupe = await service.lire_groupe(workflow_id, organisation)
    if groupe is None or groupe.get("principal") is None:
        raise HTTPException(
            status_code=404, detail=f"No group found for workflow {workflow_id}"
        )
    ordre = [(m["id"], m["name"]) for m in groupe["specialises"]]
    ordre.append((groupe["principal"]["id"], groupe["principal"]["name"]))

    reponse = PublierGroupeResponse()
    for agent_id, nom in ordre:
        if await db_client.get_draft_version(agent_id) is None:
            reponse.deja_a_jour.append(agent_id)
            continue
        try:
            publie = await publier_un_agent(agent_id, user)
        except HTTPException as e:
            reponse.refus = Refus(id=agent_id, name=nom, detail=_detail(e))
            return reponse
        reponse.publies.append(
            AgentPublie(
                id=agent_id, name=nom, version_number=publie.get("version_number")
            )
        )
    return reponse
