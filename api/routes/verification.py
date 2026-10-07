"""[.mark] The organization's « Caller verification » (chantier l-agent-collegue, L6, V2, G1).

- ``GET /organizations/verification-appelant``   the settings (the code's defaults when none)
- ``PUT /organizations/verification-appelant``   saved; a software that holds the records must
  be a declared translator of the domain « dossier »
- ``GET /organizations/verification-appelant/logiciels``  those translators, for the menu

The organization is always the signed-in user's (tenant isolation).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.db.models import UserModel
from api.schemas.verification import ReglagesVerification
from api.services.auth.depends import get_user_with_selected_organization
from api.services.verification.reglages import ecrire_reglages, lire_reglages

router = APIRouter(prefix="/organizations/verification-appelant", tags=["organizations"])


class LogicielDossier(BaseModel):
    systeme: str
    libelle: str


@router.get("", response_model=ReglagesVerification)
async def get_verification_appelant(user: UserModel = Depends(get_user_with_selected_organization)):
    return await lire_reglages(user.selected_organization_id)


@router.put("", response_model=ReglagesVerification)
async def put_verification_appelant(
    request: ReglagesVerification, user: UserModel = Depends(get_user_with_selected_organization)
):
    from api.services.hub.traducteurs import traducteur

    if request.logiciel is not None:
        t = traducteur(request.logiciel)
        if t is None or t.domaine != "dossier":
            raise HTTPException(
                status_code=422,
                detail=f"« {request.logiciel} » is not a software of the hub that holds records.",
            )
    return await ecrire_reglages(user.selected_organization_id, request)


@router.get("/logiciels", response_model=list[LogicielDossier])
async def get_logiciels_dossier(user: UserModel = Depends(get_user_with_selected_organization)):
    from api.services.hub.traducteurs import traducteurs

    return [LogicielDossier(systeme=t.systeme, libelle=t.libelle) for t in traducteurs("dossier")]
