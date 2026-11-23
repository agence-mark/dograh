"""[.mark] Module Restauration, lot 26, M30 : les routes de la connaissance par sujets (documents lus par l'outil ``infos_pratiques``).

- ``GET /restauration/connaissance`` : les sujets de l'organisation (``conversations.voir``) ;
- ``PUT /restauration/connaissance/{sujet}`` ``{texte}`` : crée le sujet ou remplace son texte (``agents.modifier``, jamais par clé d'API).

Des routes du FORK (session d'un compte de l'équipe) ; l'organisation est celle de la session, jamais celle d'un corps de requête. Format d'erreur unique.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field

from api.db.models import UserModel
from api.services.auth.depends import get_user_with_selected_organization
from api.services.restauration.appel_et_memoire import connaissance

router = APIRouter(prefix="/restauration", tags=["restauration"])


class SujetDemande(BaseModel):
    model_config = ConfigDict(extra="forbid")
    texte: str = Field(min_length=1, max_length=connaissance.TEXTE_MAX)


class SujetRendu(BaseModel):
    sujet: str
    document_uuid: str


class SujetEcrit(SujetRendu):
    taille: int
    cree: bool


class SujetsRendus(BaseModel):
    sujets: list[SujetRendu]


@router.get("/connaissance", response_model=SujetsRendus)
async def get_sujets(user: UserModel = Depends(get_user_with_selected_organization)) -> SujetsRendus:
    """The subjects of the organization (one text document per subject, read whole by the practical-information tool)."""
    return SujetsRendus(sujets=await connaissance.lister(user.selected_organization_id))


@router.put("/connaissance/{sujet}", response_model=SujetEcrit)
async def put_sujet(
    corps: SujetDemande, sujet: str = Path(max_length=40), user: UserModel = Depends(get_user_with_selected_organization)
) -> SujetEcrit:
    """Create the subject or replace its text. The returned ``document_uuid`` is what the ``subjects`` setting of the tool expects."""
    try:
        return SujetEcrit(**await connaissance.ecrire(user.selected_organization_id, user.id, sujet, corps.texte))
    except connaissance.SujetRefuse as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from None
