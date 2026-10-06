"""[.mark] La bibliothèque de clés (chantier direct-et-passe-muette, lot 0, P15, P16).

Une clé de fournisseur (Mistral, ElevenLabs…) s'enregistre une fois, se choisit partout où un
réglage en demande une, et se supprime quand elle ne marche plus ou qu'elle est révoquée.

Bâtie sur le coffre d'identifiants de Dograh (``external_credentials``, chiffré, rangé par
organisation) : aucune migration. Une clé de la bibliothèque est un identifiant ``bearer_token``
dont les données portent son fournisseur et la marque ``mark_bibliotheque`` ; les identifiants
créés ailleurs (outils HTTP) n'y apparaissent pas.

Ce qui doit tenir : tout reste dans l'organisation de l'utilisateur ; la clé n'est jamais
renvoyée après l'enregistrement, pas même dans une erreur de saisie ; une suppression dit
d'abord où la clé sert (réglages de l'appelant simulé, outils, agents), puis le réglage qui la
désignait dit « key deleted » ; un nom libéré par une suppression se réutilise.
"""

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.enums import WebhookCredentialType
from api.services.auth.depends import get_user_with_selected_organization
from api.services.bibliotheque_cles import (
    FOURNISSEURS,
    Fournisseur,
    Usage,
    donnees_d_une_cle,
    fournisseur_de,
    nom_apres_suppression,
    usages_de,
)
from api.services.cles_reference import famille

router = APIRouter(prefix="/cles", tags=["cles"])

LONGUEUR_MIN, LONGUEUR_MAX = 8, 500


class Cle(BaseModel):
    """Une clé de la bibliothèque, telle que l'écran la voit : jamais la valeur."""

    uuid: str
    nom: str
    fournisseur: Fournisseur
    creee_le: Optional[datetime] = None


class NouvelleCle(BaseModel):
    fournisseur: Fournisseur
    nom: str = Field(min_length=1, max_length=80)
    # Bornes vérifiées dans la route : une erreur de validation de FastAPI renverrait la valeur.
    cle: str


class Suppression(BaseModel):
    status: Literal["deleted"] = "deleted"
    uuid: str
    usages: list[Usage]


class Designation(BaseModel):
    """Ce que devient l'identifiant qu'un réglage désigne : une clé de la bibliothèque, un
    identifiant d'avant la bibliothèque (toujours valable), ou rien (supprimé)."""

    etat: Literal["bibliotheque", "hors_bibliotheque", "supprimee"]
    nom: Optional[str] = None


def _vue(identifiant) -> Cle:
    return Cle(
        uuid=identifiant.credential_uuid,
        nom=identifiant.name,
        fournisseur=fournisseur_de(identifiant),
        creee_le=identifiant.created_at,
    )


async def _cle_de_la_bibliotheque(uuid: str, organization_id: int):
    identifiant = await db_client.get_credential_by_uuid(uuid, organization_id)
    if identifiant is None or fournisseur_de(identifiant) is None:
        raise HTTPException(status_code=404, detail="Key not found")
    return identifiant


@router.get("", response_model=list[Cle])
async def lister_les_cles(
    fournisseur: Optional[Fournisseur] = None,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    identifiants = await db_client.get_credentials_for_organization(
        user.selected_organization_id
    )
    cles = [_vue(i) for i in identifiants if fournisseur_de(i) is not None]
    if fournisseur:
        # Par famille : une clé OpenAI se propose aussi pour OpenAI Realtime (revue du lot 0 bis).
        cles = [c for c in cles if famille(c.fournisseur) == famille(fournisseur)]
    return sorted(cles, key=lambda c: (c.fournisseur, c.nom.lower()))


@router.post("", response_model=Cle, status_code=201)
async def ajouter_une_cle(
    request: NouvelleCle,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    org = user.selected_organization_id
    nom, cle = request.nom.strip(), request.cle.strip()
    if not nom:
        raise HTTPException(status_code=422, detail="Give the key a name")
    if not LONGUEUR_MIN <= len(cle) <= LONGUEUR_MAX:
        raise HTTPException(
            status_code=422,
            detail=f"A key holds {LONGUEUR_MIN} to {LONGUEUR_MAX} characters",
        )
    deja_pris = HTTPException(
        status_code=409, detail=f"A key named « {nom} » already exists"
    )
    if any(
        i.name == nom for i in await db_client.get_credentials_for_organization(org)
    ):
        raise deja_pris
    try:
        identifiant = await db_client.create_credential(
            organization_id=org,
            user_id=user.id,
            name=nom,
            credential_type=WebhookCredentialType.BEARER_TOKEN.value,
            credential_data=donnees_d_une_cle(request.fournisseur, cle),
        )
    except Exception as erreur:  # noqa: BLE001
        # Nom d'un identifiant supprimé hors de la bibliothèque (route /credentials de Dograh) ;
        # même lecture que la route de l'amont : aucun import de la base hors de api/db/.
        if "unique_org_credential_name" in str(erreur):
            raise deja_pris from None
        raise HTTPException(status_code=500, detail="Key not saved") from None
    return _vue(identifiant)


@router.get("/fournisseurs", response_model=list[str])
async def fournisseurs_des_cles(
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """P19 : les fournisseurs qu'une clé de la bibliothèque peut servir (ceux de « Models »)."""
    return list(FOURNISSEURS)


@router.get("/designee/{uuid}", response_model=Designation)
async def identifiant_designe(
    uuid: str,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    identifiant = await db_client.get_credential_by_uuid(
        uuid, user.selected_organization_id
    )
    if identifiant is None:
        return Designation(etat="supprimee")
    if fournisseur_de(identifiant) is None:
        return Designation(etat="hors_bibliotheque", nom=identifiant.name)
    return Designation(etat="bibliotheque", nom=identifiant.name)


@router.get("/{uuid}/usages", response_model=list[Usage])
async def usages_d_une_cle(
    uuid: str,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    await _cle_de_la_bibliotheque(uuid, user.selected_organization_id)
    return await usages_de(uuid, user.selected_organization_id)


@router.delete("/{uuid}", response_model=Suppression)
async def supprimer_une_cle(
    uuid: str,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    org = user.selected_organization_id
    identifiant = await _cle_de_la_bibliotheque(uuid, org)
    usages = await usages_de(uuid, org)
    await db_client.update_credential(
        uuid, org, name=nom_apres_suppression(identifiant.name, uuid)
    )
    if not await db_client.delete_credential(uuid, org):
        raise HTTPException(status_code=404, detail="Key not found")
    return Suppression(uuid=uuid, usages=usages)
