"""[.mark] Les espaces (U2) : le sélecteur d'espace, le marquage du Labo, le nom d'affichage, la vue de l'équipe sur les conversations.

Les permissions sont au registre (``services/equipe_mark/registre_routes.py``) : lire les espaces = membre, régler un
espace = ``atelier.regler``, lire les conversations de toutes les organisations ouvertes = ``conversations.voir``.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user
from api.services.builder.constantes import organisation_bibliotheque
from api.services.equipe_mark import espaces
from api.services.equipe_mark.acces import (
    acces_de,
    journaliser,
    organisation_accessible,
)

router = APIRouter(prefix="/espaces", tags=["espaces"])


class EspaceResponse(BaseModel):
    id: int
    nom: str
    provider_id: str
    espace: str  # "labo" | "client"
    selectionne: bool


class EspacesResponse(BaseModel):
    espaces: list[EspaceResponse]


class ReglerEspaceRequest(BaseModel):
    """Seuls les champs envoyés changent : ``nom_affichage`` (vide ou null = retiré), ``labo``."""

    nom_affichage: str | None = Field(default=None, max_length=espaces.NOM_MAX * 2)
    labo: bool | None = None


class ReglerEspaceResponse(BaseModel):
    id: int
    nom: str
    espace: str


class ConversationEquipe(BaseModel):
    id: int
    name: str
    workflow_id: int
    workflow_name: str | None
    organization_id: int | None
    organization_nom: str
    mode: str
    is_completed: bool
    created_at: datetime


class ConversationsEquipeResponse(BaseModel):
    conversations: list[ConversationEquipe]
    total: int
    limit: int
    offset: int


@router.get("", response_model=EspacesResponse)
async def lister_les_espaces(user: UserModel = Depends(get_user)) -> EspacesResponse:
    return EspacesResponse(espaces=[EspaceResponse(**e) for e in await espaces.lister_espaces(user)])


@router.get("/conversations", response_model=ConversationsEquipeResponse)
async def conversations_de_l_equipe(
    organization_id: int | None = Query(None, description="Une seule organisation (sinon toutes celles que le rôle ouvre)"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: UserModel = Depends(get_user),
) -> ConversationsEquipeResponse:
    """Les conversations de TOUTES les organisations que le rôle du compte ouvre (modèle de ``superuser/workflow-runs``)."""
    visibles = await espaces.lister_espaces(user)
    par_id = {e["id"]: e["nom"] for e in visibles}
    if organization_id is not None:
        if organization_id not in par_id:
            raise HTTPException(status_code=404, detail="Space not found")
        cible = [organization_id]
    else:
        cible = list(par_id)
    lignes, total = await db_client.lister_conversations_des_organisations(
        organisations=cible, limit=limit, offset=offset
    )
    return ConversationsEquipeResponse(
        conversations=[
            ConversationEquipe(**ligne, organization_nom=par_id.get(ligne["organization_id"], ""))
            for ligne in lignes
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.put("/{organization_id}", response_model=ReglerEspaceResponse)
async def regler_un_espace(
    organization_id: int,
    corps: ReglerEspaceRequest,
    user: UserModel = Depends(get_user),
) -> ReglerEspaceResponse:
    """Nomme un espace et/ou le marque comme Labo (un seul Labo : le marquage précédent est retiré)."""
    acces = await acces_de(user)
    if not await organisation_accessible(
        user.id, organization_id, acces, organisation_bibliotheque()
    ):
        raise HTTPException(status_code=404, detail="Space not found")
    envoyes = corps.model_fields_set
    if "labo" in envoyes and corps.labo is not None:
        await espaces.definir_labo(organization_id, corps.labo)
        await journaliser(
            user, "espace.labo", organization_id, {"labo": corps.labo}
        )
    if "nom_affichage" in envoyes:
        nom = await espaces.definir_nom_affichage(organization_id, corps.nom_affichage)
        await journaliser(user, "espace.nom", organization_id, {"nom": nom})
    actuel = next((e for e in await espaces.lister_espaces(user) if e["id"] == organization_id), None)
    if actuel is None:
        raise HTTPException(status_code=404, detail="Space not found")
    return ReglerEspaceResponse(id=actuel["id"], nom=actuel["nom"], espace=actuel["espace"])
