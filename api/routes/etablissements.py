"""[.mark] The establishments of the organization, on screen (chantier l-agent-travaille, L1).

Four routes, all scoped to the user's selected organization:

- ``GET  /organizations/etablissements``          the catalogue (strict reading);
- ``PUT  /organizations/etablissements``          replace it; every bound checked
  BEFORE writing (422, nothing written): hours that parse, a commune at its
  postal code, called numbers that are the organization's own Telephony numbers;
- ``GET  /organizations/etablissements/numeros``  the organization's numbers, for
  the choice list of an establishment;
- ``POST /organizations/etablissements/agent``    what an agent's calls will read,
  establishment by establishment, with the level each value comes from -- the
  same functions as the call (E8: one rule on screen and in the code).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, Field, ValidationError

from api.db import db_client
from api.db.models import UserModel
from api.schemas.etablissements import (
    CatalogueEtablissements,
    EtablissementsDeLagent,
    NumeroDeLorganisation,
)
from api.services.auth.depends import get_user_with_selected_organization
from api.services.communes.adresse import (
    AdresseInvalide,
    texte_adresse,
    valider_adresse_saisie,
)
from api.services.etablissements.appel import etablissements_de_lagent
from api.services.etablissements.stockage import (
    enregistrer_etablissements,
    lire_etablissements_strict,
)

router = APIRouter(prefix="/organizations/etablissements", tags=["organizations"])


def _refus(message: str, loc: list) -> HTTPException:
    return HTTPException(status_code=422, detail=[{"msg": message, "loc": loc}])


@router.get("", response_model=CatalogueEtablissements)
async def get_etablissements(user: UserModel = Depends(get_user_with_selected_organization)):
    """⛔ Strict: shown empty because unreadable, the next save would replace them."""
    try:
        return await lire_etablissements_strict(user.selected_organization_id)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Establishments unreadable for the screen: {erreur!r}")
        raise HTTPException(
            status_code=500,
            detail=(
                "The establishments saved for this organization cannot be read. "
                "Nothing was changed; saving now would replace them."
            ),
        ) from None


async def _numeros_de_lorganisation(organization_id: int) -> list[NumeroDeLorganisation]:
    lignes = await db_client.lister_numeros_de_lorganisation(organization_id)
    return [
        NumeroDeLorganisation(numero=adresse, libelle=libelle, agent=nom)
        for adresse, libelle, _agent, nom, _actif in lignes
    ]


@router.get("/numeros", response_model=list[NumeroDeLorganisation])
async def get_numeros(user: UserModel = Depends(get_user_with_selected_organization)):
    return await _numeros_de_lorganisation(user.selected_organization_id)


@router.put("", response_model=CatalogueEtablissements)
async def save_etablissements(
    request: CatalogueEtablissements,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    from api.services.pipecat.etat_ouverture import (
        HorairesInvalides,
        vers_expression_osm,
    )

    organization_id = user.selected_organization_id
    siens = {n.numero for n in await _numeros_de_lorganisation(organization_id)}
    verifies = []
    for rang, etablissement in enumerate(request.etablissements):
        loc = ["body", "etablissements", rang]
        if etablissement.horaires_ouverture:
            try:
                vers_expression_osm(etablissement.horaires_ouverture)
            except HorairesInvalides as erreur:
                raise _refus(f"{etablissement.nom}: {erreur}", loc + ["horaires_ouverture"]) from None
        for numero in etablissement.numeros:
            if numero not in siens:
                # Tenant isolation: a called number must be one of THIS organization's.
                raise _refus(
                    f"{etablissement.nom}: {numero} is not a Telephony number of this organization.",
                    loc + ["numeros"],
                )
        adresse = etablissement.adresse
        if adresse is not None:
            try:
                adresse = await valider_adresse_saisie(adresse)
            except AdresseInvalide as erreur:
                raise _refus(f"{etablissement.nom}: {erreur}", loc + ["adresse"]) from None
        verifies.append(etablissement.model_copy(update={"adresse": adresse}))
    return await enregistrer_etablissements(
        organization_id, request.model_copy(update={"etablissements": verifies})
    )


class DemandeEtablissementsDeLagent(BaseModel):
    workflow_id: int
    horaires_ouverture: str | None = Field(default=None, description="The agent's own hours, as on its screen.")
    adresse_etablissement: dict | None = Field(default=None, description="The agent's own address, as on its screen.")


@router.post("/agent", response_model=EtablissementsDeLagent)
async def post_etablissements_de_lagent(
    request: DemandeEtablissementsDeLagent,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    organization_id = user.selected_organization_id
    workflow = await db_client.get_workflow(request.workflow_id, organization_id=organization_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        catalogue = await lire_etablissements_strict(organization_id)
    except (ValidationError, ValueError):
        catalogue = CatalogueEtablissements()
    lignes = await db_client.lister_numeros_de_lorganisation(organization_id)
    numeros = [adresse for adresse, _l, agent, _n, _a in lignes if agent == request.workflow_id]

    from api.services.annonce.stockage import lire_annonce_ouverture
    from api.services.organization_preferences import get_organization_preferences

    preferences = await get_organization_preferences(organization_id)
    adresse_org = getattr(preferences, "adresse_etablissement", None)
    return etablissements_de_lagent(
        catalogue,
        numeros,
        {
            "horaires_ouverture": request.horaires_ouverture,
            "adresse_etablissement": request.adresse_etablissement,
        },
        texte_adresse(adresse_org) if adresse_org else None,
        await lire_annonce_ouverture(organization_id),
    )
