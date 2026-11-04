"""[.mark] Ce que le portail du client lit et écrit du Hub « Relation clients » (U3 septies, E78).

Réservé à une CLÉ D'API (le portail, avec la clé de ce client) : une session reçoit 403. Tout se fait dans
l'organisation de la clé ; la clé d'une autre organisation ne voit rien. Une note interne n'est JAMAIS rendue, les notes
sur un client et les témoignages n'ont pas de route ici.

* ``/organizations/relation/fils`` : les fils et demandes de logiciel du client, l'envoi d'un message ou d'une demande ;
* ``/organizations/relation/entree/verifier`` : le portail présente le lien d'entrée de .mark ; il est consommé (une
  seule fois, une minute, ce client seulement) et le portail ouvre avec le rôle .mark.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user_with_selected_organization
from api.services.relation import hub

router = APIRouter(prefix="/organizations/relation", tags=["relation"])


async def portail(
    user: UserModel = Depends(get_user_with_selected_organization),
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> UserModel:
    if not hub.est_une_cle_d_api(x_api_key):
        raise HTTPException(status_code=403, detail="Reserved to the client portal (API key)")
    return user


def _auteur(user: UserModel) -> str:
    texte = (getattr(user, "mark_auteur", None) or "portail : client")
    return texte.removeprefix("portail :").strip() or "client"


class MessagePortail(BaseModel):
    id: int
    cote: Literal["client", "mark"]
    auteur: str
    texte: str
    cree_le: datetime


class FilPortail(BaseModel):
    id: int
    sorte: str
    sujet: str
    etat: str
    logiciel: str | None
    catalogue: str | None
    etat_demande: str | None
    cree_le: datetime
    modifie_le: datetime
    dernier: MessagePortail | None = None
    messages: list[MessagePortail] | None = None


class FilIn(BaseModel):
    sorte: Literal["message", "demande_logiciel"] = "message"
    sujet: str = Field(min_length=1, max_length=200)
    texte: str = Field(min_length=1, max_length=8000)
    logiciel: str | None = Field(default=None, max_length=120)
    catalogue: str | None = Field(default=None, max_length=120)


class MessageIn(BaseModel):
    texte: str = Field(min_length=1, max_length=8000)


class VerifierIn(BaseModel):
    jeton: str = Field(min_length=10, max_length=200)


class EntreeVerifiee(BaseModel):
    entree_id: int
    auteur: str
    motif: str | None


_CHAMPS_FIL = (
    "id", "sorte", "sujet", "etat", "logiciel", "catalogue", "etat_demande", "cree_le", "modifie_le",
)


def _sortie(fil: dict) -> FilPortail:
    """Une liste blanche de champs : ni l'organisation, ni le suivi, ni la lecture interne ne sortent."""
    return FilPortail(
        **{k: fil[k] for k in _CHAMPS_FIL},
        dernier=MessagePortail(**fil["dernier"]) if fil.get("dernier") else None,
        messages=[MessagePortail(**m) for m in fil["messages"]] if "messages" in fil else None,
    )


@router.get("/fils", response_model=list[FilPortail])
async def mes_fils(user: UserModel = Depends(portail)) -> list[FilPortail]:
    fils = await db_client.lister_fils_relation([user.selected_organization_id], avec_internes=False)
    return [_sortie(f) for f in fils]


@router.get("/fils/{fil_id}", response_model=FilPortail)
async def mon_fil(fil_id: int, user: UserModel = Depends(portail)) -> FilPortail:
    fil = await db_client.lire_fil_relation(user.selected_organization_id, fil_id, avec_internes=False)
    if fil is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return _sortie(fil)


@router.post("/fils", response_model=FilPortail, status_code=201)
async def ecrire_a_mark(corps: FilIn, user: UserModel = Depends(portail)) -> FilPortail:
    """« Écrire à .mark » ou « Demander un logiciel » : un nouveau fil dans l'organisation de la clé."""
    if corps.sorte == "demande_logiciel" and not (corps.logiciel or "").strip():
        raise HTTPException(status_code=422, detail="A software request names the software")
    fil = await db_client.creer_fil_relation(
        user.selected_organization_id,
        sorte=corps.sorte,
        sujet=corps.sujet.strip(),
        auteur=_auteur(user),
        texte=corps.texte.strip(),
        logiciel=(corps.logiciel or "").strip() or None,
        catalogue=(corps.catalogue or "").strip() or None,
    )
    complet = await db_client.lire_fil_relation(user.selected_organization_id, fil["id"], avec_internes=False)
    return _sortie(complet)


@router.post("/fils/{fil_id}/messages", response_model=MessagePortail, status_code=201)
async def repondre_a_mark(fil_id: int, corps: MessageIn, user: UserModel = Depends(portail)) -> MessagePortail:
    message = await db_client.ajouter_message_relation(
        user.selected_organization_id, fil_id, cote="client", auteur=_auteur(user), texte=corps.texte.strip()
    )
    if message is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return MessagePortail(**message)


@router.post("/entree/verifier", response_model=EntreeVerifiee)
async def verifier_entree(corps: VerifierIn, user: UserModel = Depends(portail)) -> EntreeVerifiee:
    """Le lien d'entrée de .mark : valable une minute, une seule fois, pour CE client seulement.

    Inconnu, rejoué, expiré ou d'un autre client : la même réponse 403, sans dire lequel.
    """
    entree = await hub.consommer_lien(user.selected_organization_id, corps.jeton)
    if entree is None:
        raise HTTPException(status_code=403, detail="Invalid or expired entry link")
    return EntreeVerifiee(entree_id=entree["id"], auteur=entree["auteur"], motif=entree["motif"])


class EntreeTerminee(BaseModel):
    duree_secondes: int


@router.post("/entree/{entree_id}/fin", response_model=EntreeTerminee)
async def terminer_entree(entree_id: int, user: UserModel = Depends(portail)) -> EntreeTerminee:
    """V4 : le portail dit que la personne de .mark est sortie. Une seule fois, pour CE client seulement : la durée de la visite
    (``fin - entrée``) se lit ensuite dans le Hub. Inconnue, d'un autre client, jamais entrée ou déjà terminée : 404, sans dire laquelle."""
    fin = await db_client.terminer_entree_relation(user.selected_organization_id, entree_id, datetime.now(UTC))
    if fin is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    return EntreeTerminee(duree_secondes=fin["duree_secondes"])
