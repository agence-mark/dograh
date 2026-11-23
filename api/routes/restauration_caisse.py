"""[.mark] Module Restauration, lots 9 et 10 : les routes de la liaison à la caisse (contrat portail ↔ fork § 2).

Routes du portail (clé de l'organisation, permission au registre, établissement relu contre la base de l'organisation : 404 sinon) :

- ``POST /restauration/etablissements/{id}/caisse/brancher`` : début du branchement (« Brancher ma caisse ») : rend l'adresse d'autorisation.
- ``GET /restauration/etablissements/{id}/caisse`` : la fiche de liaison (prise, capacités, état, dernière erreur, dernière synchro).
- ``POST /restauration/etablissements/{id}/ruptures`` : une rupture (toujours possible), poussée à la caisse si la prise sait la poser.

Routes sans session de compte (exemptions écrites au registre, chacune avec sa garde) :

- ``GET /restauration/caisse/hubrise/retour`` : le retour de la page d'autorisation ; garde : ``state`` aléatoire, à usage unique, gardé en empreinte.
- ``POST /restauration/caisse/hubrise/rappel`` : les messages signés de la caisse ; garde : signature HMAC-SHA256 du corps brut, comparée à temps constant.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from loguru import logger

from api.db.models import UserModel
from api.routes.restauration import _connexion_de_l_etablissement, _refus
from api.schemas.restauration_caisse import (
    BrancherDemande,
    BrancherRendu,
    CaisseRendue,
    EssaiRendu,
    ImprimanteDemandee,
    ImprimanteRendue,
    OkCaisse,
    ResynchroRendue,
    RuptureDemandee,
    RuptureRendue,
)
from api.services.auth.depends import get_user_with_selected_organization
from api.services.base_client import rattachement
from api.services.restauration.caisse import caisse as service_caisse
from api.services.restauration.caisse import imprimante as service_imprimante
from api.services.restauration.caisse.prises import imprimante_cloudprnt as cloudprnt
from api.services.restauration.caisse.prises import hubrise_liaison, hubrise_reception
from api.services.restauration.caisse.prises.hubrise_client import ErreurHubrise

router = APIRouter(prefix="/restauration", tags=["restauration"])

LIMITE_PAR_MINUTE = 600  # messages acceptés par minute et par point de vente (la caisse en envoie bien moins) ; au-delà : 429, la caisse réessaie
LIMITE_IMPRIMANTE = 60  # interrogations par minute et par imprimante (elle en fait 12 à 20 : toutes les 3 à 5 s)
LIMITE_IMPRIMANTES_TOUTES = 6000  # par minute, toutes imprimantes
LIMITE_AVANT_SIGNATURE = 3000  # par minute, envois à la signature fausse confondus : ils ne bloquent jamais un message signé

_PAGE = (
    "<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>.mark</title></head>"
    "<body style='font-family:sans-serif;max-width:32rem;margin:4rem auto'><p>{fr}</p><p lang='en'>{en}</p></body></html>"
)
_REFUS_DU_RETOUR = {
    "state_invalide": 400, "base_absente": 409, "etablissement_inconnu": 404, "point_de_vente_deja_pris": 409,
}


@router.post("/etablissements/{etablissement_id}/caisse/brancher", response_model=BrancherRendu)
async def post_brancher(etablissement_id: int, corps: BrancherDemande, user: UserModel = Depends(get_user_with_selected_organization)) -> BrancherRendu:
    """Start connecting the till of the establishment: returns the authorization page address (a one-use state is kept, hashed)."""
    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    await connexion.close()  # l'établissement est relu ; le branchement lui-même ne touche la base qu'au retour
    try:
        adresse = await hubrise_liaison.commencer_le_branchement(user.selected_organization_id, etablissement_id, user.id)
    except hubrise_liaison.NonConfiguree:
        raise _refus(503, "This till connection is not configured on this server.") from None
    return BrancherRendu(adresse_autorisation=adresse)


@router.get("/etablissements/{etablissement_id}/caisse", response_model=CaisseRendue)
async def get_caisse(etablissement_id: int, user: UserModel = Depends(get_user_with_selected_organization)) -> CaisseRendue:
    """The till link sheet of the establishment: socket, capabilities, state, last error (a code) and last synchronisation."""
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    try:
        async with _schema_a_jour(connexion):
            return CaisseRendue.model_validate(await service_caisse.fiche_de_liaison(connexion, etablissement_id))
    finally:
        await connexion.close()


@router.delete("/etablissements/{etablissement_id}/caisse", response_model=OkCaisse)
async def delete_caisse(etablissement_id: int, user: UserModel = Depends(get_user_with_selected_organization)) -> OkCaisse:
    """Unplug the till of the establishment (lot 13, M6): the link, the stored token and the till state go; the menu and the orders already read are kept."""
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    try:
        async with _schema_a_jour(connexion):
            if not await service_caisse.debrancher(connexion, user.selected_organization_id, etablissement_id):
                raise _refus(409, "No till is plugged in to this establishment.")
    finally:
        await connexion.close()
    return OkCaisse(ok=True)


@router.post("/etablissements/{etablissement_id}/caisse/resynchroniser", response_model=ResynchroRendue)
async def post_resynchroniser(etablissement_id: int, user: UserModel = Depends(get_user_with_selected_organization)) -> ResynchroRendue:
    """Read the till again now (lot 13, M6): menu, stock-outs and state according to the socket sheet. The link says itself whether it worked."""
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    try:
        async with _schema_a_jour(connexion):
            bilan = await service_caisse.resynchroniser(
                connexion, user.selected_organization_id, etablissement_id, nom_base=await rattachement.nom_de_la_base(user.selected_organization_id)
            )
    finally:
        await connexion.close()
    if bilan is None:
        raise _refus(409, "No till is plugged in to this establishment.")
    return ResynchroRendue(ok=bilan["erreur"] is None, erreur=bilan["erreur"], carte=bilan["carte"] is not None, ruptures=bilan["ruptures"] is not None, etat=bilan["etat"] is not None)


@router.post("/etablissements/{etablissement_id}/caisse/commande-d-essai", response_model=EssaiRendu)
async def post_commande_d_essai(etablissement_id: int, user: UserModel = Depends(get_user_with_selected_organization)) -> EssaiRendu:
    """Send a one-item test order to the Lab's DEMO till (internal, no third party). Against a real till: refused, the real trial is lot 19 (lot 13, F8)."""
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    try:
        async with _schema_a_jour(connexion):
            rendu = await service_caisse.commande_d_essai(
                connexion, user.selected_organization_id, etablissement_id, nom_base=await rattachement.nom_de_la_base(user.selected_organization_id)
            )
    finally:
        await connexion.close()
    return EssaiRendu(**rendu)


@router.post("/etablissements/{etablissement_id}/ruptures", response_model=RuptureRendue)
async def post_rupture(etablissement_id: int, corps: RuptureDemandee, user: UserModel = Depends(get_user_with_selected_organization)) -> RuptureRendue:
    """Put a product (or an option) out of stock, or back. Always possible; pushed to the till when the socket can."""
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    try:
        async with _schema_a_jour(connexion):
            resultat, poussee = await service_caisse.poser_la_rupture(
                connexion, user.selected_organization_id, etablissement_id, corps.code_caisse, corps.disponible, corps.fin,
                nom_base=await rattachement.nom_de_la_base(user.selected_organization_id),
            )
    finally:
        await connexion.close()
    if resultat.statut == "INTROUVABLE":
        raise _refus(404, "Product not found in the menu of this establishment.")
    if resultat.statut != "OK":
        raise _refus(422, f"Invalid value: {resultat.manque or 'request'}.")
    return RuptureRendue(ok=True, poussee_a_la_caisse=poussee)


@router.get("/caisse/hubrise/retour", response_class=HTMLResponse, include_in_schema=False)
async def get_retour_hubrise(code: str | None = Query(default=None, max_length=300), state: str | None = Query(default=None, max_length=300), error: str | None = Query(default=None, max_length=60)):
    """The return of the authorization page. No account session: the guard is the one-use ``state`` (random, kept hashed, ten minutes)."""
    if error or not code or not state:
        return HTMLResponse(_PAGE.format(fr="La connexion de la caisse n'a pas abouti. Vous pouvez fermer cette page et réessayer.", en="The till connection did not complete. You can close this page and try again."), status_code=400)
    try:
        await hubrise_liaison.terminer_le_branchement(code, state)
    except hubrise_liaison.BranchementRefuse as refus:
        return HTMLResponse(_PAGE.format(fr="Ce lien n'est plus valable. Relancez la connexion depuis votre espace.", en="This link is no longer valid. Start the connection again from your space."), status_code=_REFUS_DU_RETOUR.get(refus.code, 400))
    except hubrise_liaison.NonConfiguree:
        raise HTTPException(status_code=503, detail="This till connection is not configured on this server.") from None
    except ErreurHubrise as erreur:
        logger.warning(f"[.mark] Till connection failed at the return: {erreur.code}")
        return HTMLResponse(_PAGE.format(fr="La caisse n'a pas répondu. Réessayez dans un instant.", en="The till did not answer. Try again in a moment."), status_code=502)
    return HTMLResponse(_PAGE.format(fr="Votre caisse est connectée. Vous pouvez fermer cette page.", en="Your till is connected. You can close this page."))


async def _sous_la_limite(cle: str, limite: int) -> bool:
    """Un compteur par minute (clé qui s'efface seule) : ``False`` au-delà de ``limite``."""
    from api.services.restauration.caisse.prises.hubrise_liaison import _redis

    redis = await _redis()
    try:
        total = await redis.incr(cle)
        if total == 1:
            await redis.expire(cle, 60)
        return total <= limite
    finally:
        await redis.aclose()


@router.post("/caisse/hubrise/rappel", include_in_schema=False)
async def post_rappel_hubrise(request: Request, signature: str | None = Header(default=None, alias="X-HubRise-Hmac-SHA256")):
    """The signed messages of the till. No account session: the guard is the HMAC-SHA256 signature of the raw body (constant time).
    Answers fast: the work is queued. A message from an unknown point of sale is logged and acknowledged (HubRise must not resend it)."""
    corps = await request.body()
    if len(corps) > hubrise_reception.TAILLE_MAX_OCTETS:
        raise HTTPException(status_code=413, detail="Message too large.")
    try:
        secret = hubrise_liaison.secret_de_signature()
    except hubrise_liaison.NonConfiguree:
        raise HTTPException(status_code=503, detail="This till connection is not configured on this server.") from None
    if not hubrise_reception.signature_valide(corps, signature, secret):
        # Revue de clôture (2) : seuls les envois REFUSÉS comptent dans la limite commune, jamais un message signé : un inconnu qui
        # inonde la route ne bloque pas les vrais messages de HubRise (le coût avant signature reste borné par la taille maximale).
        if not await _sous_la_limite("mark:resto:hubrise:refus:tous", LIMITE_AVANT_SIGNATURE):
            raise HTTPException(status_code=429, detail="Too many requests.")
        raise HTTPException(status_code=401, detail="Invalid signature.")  # 4xx : HubRise ne renvoie pas un message que nous refusons
    message = hubrise_reception.lire_le_message(corps)
    if message is None:
        return {"ok": True, "ignore": True}
    if not await _sous_la_limite(f"mark:resto:hubrise:debit:{message['location_id'][:80]}", LIMITE_PAR_MINUTE):
        raise HTTPException(status_code=429, detail="Too many requests.")
    try:
        await hubrise_reception.mettre_en_file(message)
    except Exception as erreur:  # noqa: BLE001 -- file indisponible : 5xx, HubRise renverra le message (6 tentatives de 1 à 32 minutes)
        logger.error(f"[.mark] HubRise message not queued: {type(erreur).__name__}")
        raise HTTPException(status_code=503, detail="Temporarily unavailable.") from None
    return {"ok": True}


# --------------------------------------------------------------------------- l'imprimante (Star CloudPRNT)


@router.post("/etablissements/{etablissement_id}/imprimante", response_model=ImprimanteRendue)
async def post_imprimante(etablissement_id: int, corps: ImprimanteDemandee, user: UserModel = Depends(get_user_with_selected_organization)) -> ImprimanteRendue:
    """Put (or replace) the printer of the establishment. Returns the address to enter in the printer, once (the secret is kept hashed only)."""
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    try:
        async with _schema_a_jour(connexion):
            jeton = await service_imprimante.poser_l_imprimante(
                connexion, user.selected_organization_id, etablissement_id, nom=corps.nom, mode_planifiee=corps.mode_planifiee, minutes_avant=corps.minutes_avant
            )
    finally:
        await connexion.close()
    return ImprimanteRendue(adresse=service_imprimante.adresse_de_l_imprimante(jeton))


async def _imprimante_du_jeton(jeton: str):
    """``(connexion, organisation, imprimante)`` ou 404 (toujours la même réponse : jamais un moyen de sonder les jetons) ; limite de débit par jeton."""
    import hashlib

    if not await _sous_la_limite("mark:resto:imprimante:debit:tous", LIMITE_IMPRIMANTES_TOUTES):
        raise HTTPException(status_code=429, detail="Too many requests.")
    if not await _sous_la_limite("mark:resto:imprimante:debit:" + hashlib.sha256(jeton.encode()).hexdigest()[:24], LIMITE_IMPRIMANTE):
        raise HTTPException(status_code=429, detail="Too many requests.")
    trouvee = await service_imprimante.retrouver(jeton)
    if trouvee is None:
        raise HTTPException(status_code=404, detail="Not found.")
    return trouvee


@router.post("/imprimante/{jeton}", include_in_schema=False)
async def post_interrogation_imprimante(jeton: str, request: Request):
    """The CloudPRNT poll. No account session: the guard is the printer token (kept hashed). Answers ``jobReady``."""
    connexion, organisation, imprimante = await _imprimante_du_jeton(jeton)
    try:
        try:
            corps = await request.json()
        except ValueError:
            corps = {}
        return JSONResponse(await cloudprnt.interroger(connexion, organisation, imprimante, corps if isinstance(corps, dict) else {}))
    finally:
        await connexion.close()


@router.get("/imprimante/{jeton}", include_in_schema=False)
async def get_ticket_imprimante(
    jeton: str, type: str | None = Query(default=None, max_length=80), token: str | None = Query(default=None, max_length=64), mac: str | None = Query(default=None, max_length=40)
):
    """The CloudPRNT job fetch: the ticket of the order named by ``token``, in the requested media type."""
    connexion, organisation, imprimante = await _imprimante_du_jeton(jeton)
    try:
        rendu = await cloudprnt.donner_le_ticket(connexion, organisation, imprimante, type, token)
    finally:
        await connexion.close()
    if rendu is None:
        raise HTTPException(status_code=404, detail="Not found.")
    return Response(content=rendu[0], media_type=rendu[1])


@router.delete("/imprimante/{jeton}", include_in_schema=False)
async def delete_ticket_imprimante(
    jeton: str, code: str | None = Query(default=None, max_length=60), token: str | None = Query(default=None, max_length=64), mac: str | None = Query(default=None, max_length=40)
):
    """The CloudPRNT result: ``code`` starting with 2 = printed ; 520 = download failed (kept) ; other = a print error (the restaurant is warned)."""
    connexion, organisation, imprimante = await _imprimante_du_jeton(jeton)
    try:
        return {"resultat": await cloudprnt.confirmer(connexion, organisation, imprimante, code, token)}
    finally:
        await connexion.close()
