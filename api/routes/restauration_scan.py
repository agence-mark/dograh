"""[.mark] Module Restauration, lot 20 (scan W46) : lire la photo d'une carte, par les clés de l'organisation (éteint par défaut, une lecture coûte).

- ``GET|PUT /restauration/scan-carte`` : le réglage (allumé ou éteint) de l'organisation ;
- ``POST /restauration/etablissements/{id}/carte/photo`` : une photo -> une PROPOSITION de carte au format commun (rien n'est écrit : la personne la relit puis l'importe
  par ``carte/import``) ; l'établissement est relu contre la base de l'organisation (404 sinon) ;
- la même lecture sert la carte d'un restaurant de test de la caisse de démo (``routes/restauration_caisse_demo.py``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from api.db.models import UserModel
from api.routes.restauration import _connexion_de_l_etablissement
from api.schemas.restauration_caisse_demo import LirePhotoDemande
from api.services.auth.depends import get_user_with_selected_organization
from api.services.restauration.carte_et_allergenes import scan_carte

router = APIRouter(prefix="/restauration", tags=["restauration"])

# code du refus -> (statut, message court qui dit quoi faire ; jamais le texte d'un fournisseur)
REFUS = {
    "eteint": (403, "Photo reading is off: turn it on first."),
    "cle_absente": (409, "No model key is set for this organization: add one first."),
    "image_refusee": (422, "The photo is not valid (JPEG, PNG or WebP, 8 MB at most)."),
    "trop_de_lectures": (429, "Too many photo readings this hour: try again later."),
    "fournisseur": (502, "The model did not answer: nothing was read. Try again."),
    "reponse_illisible": (502, "The photo could not be read as a menu: try a sharper photo."),
}


class ScanReglage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actif: bool


async def lire_une_photo(organization_id: int, corps: LirePhotoDemande, *, avec_codes: bool) -> dict[str, Any]:
    try:
        return await scan_carte.lire_la_photo_de_l_organisation(organization_id, corps.image, corps.type_image, avec_codes=avec_codes)
    except scan_carte.ScanRefuse as refus:
        statut, message = REFUS[refus.code]
        raise HTTPException(status_code=statut, detail=message) from None


@router.get("/scan-carte")
async def get_scan(user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, bool]:
    return {"actif": await scan_carte.est_allume(user.selected_organization_id)}


@router.put("/scan-carte")
async def put_scan(corps: ScanReglage, user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, bool]:
    await scan_carte.allumer(user.selected_organization_id, corps.actif)
    return {"actif": corps.actif}


@router.post("/etablissements/{etablissement_id}/carte/photo")
async def post_photo(etablissement_id: int, corps: LirePhotoDemande, user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, Any]:
    """A photo of the menu becomes a PROPOSAL in the common format (nothing is written): the codes come from the till, so none is made up."""
    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    await connexion.close()  # l'établissement est relu ; la lecture ne touche pas la base
    return await lire_une_photo(user.selected_organization_id, corps, avec_codes=False)
