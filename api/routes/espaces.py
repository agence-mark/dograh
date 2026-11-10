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


class EspaceDeLAgentResponse(BaseModel):
    """L'espace où vit un agent : de quoi dire « cet agent est dans l'espace … » avec un lien, au lieu d'un « introuvable »."""

    workflow_id: int
    id: int
    nom: str
    espace: str  # "labo" | "client"
    selectionne: bool


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
    # Clôture SA-5 (É8) : les colonnes de la maquette, lues du run (motif, résumé, issue, durée, qui a jugé, note).
    motif: str | None = None
    resume: str | None = None
    resume_source: str | None = None
    issue: str | None = None
    duree: int | None = None
    juge_par: str | None = None
    note_juge: float | None = None


class ConversationsEquipeResponse(BaseModel):
    conversations: list[ConversationEquipe]
    total: int
    limit: int
    offset: int
    # Les motifs des organisations ouvertes, proposés au filtre « Tous les motifs ».
    motifs: list[str] = []


@router.get("", response_model=EspacesResponse)
async def lister_les_espaces(user: UserModel = Depends(get_user)) -> EspacesResponse:
    return EspacesResponse(espaces=[EspaceResponse(**e) for e in await espaces.lister_espaces(user)])


@router.get("/agent/{workflow_id}", response_model=EspaceDeLAgentResponse)
async def espace_d_un_agent(workflow_id: int, user: UserModel = Depends(get_user)) -> EspaceDeLAgentResponse:
    """L'espace d'un agent, SEULEMENT s'il est dans un espace que le compte ouvre : un agent d'un espace fermé reste un 404,
    comme un agent qui n'existe pas (le cloisonnement ne fuit pas par ce message)."""
    organisation = await db_client.get_workflow_organization_id(workflow_id)
    cible = None
    if organisation is not None:
        cible = next((e for e in await espaces.lister_espaces(user) if e["id"] == organisation), None)
    if cible is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return EspaceDeLAgentResponse(
        workflow_id=workflow_id, id=cible["id"], nom=cible["nom"], espace=cible["espace"], selectionne=cible["selectionne"]
    )


@router.get("/conversations", response_model=ConversationsEquipeResponse)
async def conversations_de_l_equipe(
    organization_id: int | None = Query(None, description="Une seule organisation (sinon toutes celles que le rôle ouvre)"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    motif: str | None = Query(None, max_length=80, description="Motif exact"),
    recherche: str | None = Query(None, max_length=80, description="Un mot du motif, de l'issue, du résumé, de l'agent ou du client"),
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
    terme = (recherche or "").strip().casefold()
    nommees = [i for i in cible if terme and terme in par_id.get(i, "").casefold()] if len(terme) >= 3 else None
    lignes, total = await db_client.lister_conversations_des_organisations(
        organisations=cible, limit=limit, offset=offset, motif=motif, recherche=recherche, organisations_nommees=nommees
    )
    motifs = await db_client.lister_motifs_des_organisations(cible)
    return ConversationsEquipeResponse(
        conversations=[
            ConversationEquipe(**ligne, organization_nom=par_id.get(ligne["organization_id"], ""))
            for ligne in lignes
        ],
        total=total,
        limit=limit,
        offset=offset,
        motifs=motifs,
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
