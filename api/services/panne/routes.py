"""[.mark] The outage fallback on the network (L7).

- ``POST /telephony/twilio/panne/{run_id}/resultat``  Twilio, after ringing the second number:
  answered → hang up when it ends; not answered → the call-back promise prepared by the guard.
  ⛔ Signature checked with the run's own Twilio account, like the other Twilio webhooks.
- ``GET/PUT /organizations/panne``  the organization's emergency address (TwiML Bin) and the
  text of the Bin to paste in its Twilio console.
- ``POST /organizations/panne/rattrapage``  the calls lost while our server was down, now.

Scoped to the signed-in user's organization, except the webhook (derived from the run, then
proved by the signature).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, ValidationError
from starlette.responses import Response

from api.db import db_client
from api.db.models import UserModel
from api.enums import OrganizationConfigurationKey
from api.schemas.panne import DEFAUT_RAPPEL_SANS_DATE, ReglagesPanne
from api.services.auth.depends import get_user_with_selected_organization
from api.services.panne import consigne
from api.services.panne.gardien import CLE_FICHE

routeur_twilio = APIRouter(prefix="/telephony/twilio/panne", include_in_schema=False)
router = APIRouter(prefix="/organizations/panne", tags=["organizations"])

CLE = OrganizationConfigurationKey.PANNE.value


def _xml(texte: str) -> Response:
    return Response(content=texte, media_type="application/xml")


@routeur_twilio.post("/{run_id}/resultat")
async def post_resultat_du_renvoi(run_id: int, request: Request):
    from api.services.telephony.factory import get_telephony_provider_for_run

    run = await db_client.get_workflow_run_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    workflow = await db_client.get_workflow_by_id(run.workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    donnees = dict(await request.form())
    fournisseur = await get_telephony_provider_for_run(run, workflow.organization_id)
    if not await fournisseur.verify_inbound_signature(
        str(request.url), donnees, dict(request.headers)
    ):
        logger.warning(f"[run {run_id}] Invalid Twilio signature on the outage result")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    statut = str(donnees.get("DialCallStatus") or "")
    fiche = dict(run.gathered_context or {})
    trace = dict(fiche.get(CLE_FICHE) or {})
    trace["resultat_renvoi"] = statut or "inconnu"
    repondu = statut == "completed"
    trace["rappel_promis"] = not repondu
    try:
        await db_client.update_workflow_run(run_id, gathered_context={CLE_FICHE: trace})
    except Exception as erreur:  # noqa: BLE001 -- Twilio waits for its instruction
        logger.warning(f"[run {run_id}] Outage result not written: {erreur!r}")
    if repondu:
        return _xml(consigne.raccrocher())
    return _xml(
        trace.get("consigne_rappel") or consigne.rappel(DEFAUT_RAPPEL_SANS_DATE)
    )


class EcranPanne(BaseModel):
    reglages: ReglagesPanne
    texte_du_bin: str
    texte_du_bin_promesse: str


async def lire_reglages(organization_id: int) -> ReglagesPanne:
    ligne = await db_client.get_configuration(organization_id, CLE)
    try:
        return ReglagesPanne.model_validate((ligne.value if ligne else None) or {})
    except ValidationError:
        return ReglagesPanne()


@router.get("", response_model=EcranPanne)
async def get_panne(user: UserModel = Depends(get_user_with_selected_organization)):
    return EcranPanne(
        reglages=await lire_reglages(user.selected_organization_id),
        texte_du_bin=consigne.texte_du_bin(),
        texte_du_bin_promesse=consigne.texte_du_bin_promesse(),
    )


@router.put("", response_model=EcranPanne)
async def put_panne(
    reglages: ReglagesPanne,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    await db_client.upsert_configuration(
        user.selected_organization_id, CLE, reglages.model_dump()
    )
    return EcranPanne(
        reglages=reglages,
        texte_du_bin=consigne.texte_du_bin(),
        texte_du_bin_promesse=consigne.texte_du_bin_promesse(),
    )


class ResultatRattrapage(BaseModel):
    appels_lus: int
    demandes_creees: int
    deja_connus: int
    erreurs: list[str]


@router.post("/rattrapage", response_model=ResultatRattrapage)
async def post_rattrapage(
    user: UserModel = Depends(get_user_with_selected_organization),
):
    from api.services.panne.rattrapage import rattraper

    return ResultatRattrapage(**(await rattraper(user.selected_organization_id)))


class DemandeSecours(BaseModel):
    numero: str
    effacer: bool = False


class ResultatSecours(BaseModel):
    numero: str
    adresse: str | None
    ecrit: bool


@router.post("/adresse-de-secours", response_model=ResultatSecours)
async def post_adresse_de_secours(
    demande: DemandeSecours,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """PN5: write (or clear) the ``VoiceFallbackUrl`` of ONE number of this organization.

    ⛔ On a real Twilio account this changes the number in production: a gesture done by
    hand, from the screen, on Evan's go (A-VALIDER), never by a test or a script."""
    from api.services.etablissements.appel import etablissement_de_lappel
    from api.services.panne import twilio as client_twilio
    from api.services.panne.rattrapage import _comptes

    organization_id = user.selected_organization_id
    reglages = await lire_reglages(organization_id)
    if not demande.effacer and not (
        reglages.url_secours or reglages.url_secours_promesse
    ):
        raise HTTPException(
            status_code=422, detail="Set the emergency address (TwiML Bin) first."
        )
    compte = next(
        (
            (sid, jeton)
            for sid, jeton, numeros in await _comptes(organization_id)
            if demande.numero in numeros
        ),
        None,
    )
    if compte is None:
        raise HTTPException(
            status_code=404,
            detail="This number is not one of this organization's Twilio numbers.",
        )
    adresse = None
    if not demande.effacer:
        servi = await etablissement_de_lappel(
            organization_id, None, {"called_number": demande.numero}
        )
        second = (
            getattr(getattr(servi, "etablissement", None), "second_numero", None)
            or None
        )
        url, second = consigne.bin_de_secours(
            reglages.url_secours, reglages.url_secours_promesse, second
        )
        adresse = consigne.adresse_de_secours(url, second)
    try:
        ecrit = await client_twilio.ecrire_adresse_de_secours(
            compte[0], compte[1], demande.numero, adresse
        )
    except client_twilio.TwilioIndisponible as erreur:
        raise HTTPException(status_code=502, detail=str(erreur)) from None
    return ResultatSecours(numero=demande.numero, adresse=adresse, ecrit=ecrit)
