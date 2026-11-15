"""[.mark] Module Restauration, lots 22 et 6 : les routes du fork pour le portail (contrat portail ↔ fork § 2 et 3) : le flux en direct, la puce du temps.

``GET /restauration/flux?etablissements=1,2&role=equipe`` : un flux ``text/event-stream`` des établissements DE L'ORGANISATION de la clé
(ou de la session), jamais d'une autre. Permission : ``conversations.voir`` (ouverte à la clé du portail, registre des routes).

- L'organisation est celle de la requête ; chaque établissement demandé est relu contre la base de CETTE organisation avant
  d'ouvrir quoi que ce soit : un identifiant inconnu d'elle (d'une autre organisation, ou qui n'existe pas) fait refuser toute la
  demande (404, sans dire lequel), rien n'est lu.
- ``Last-Event-ID`` : la reprise rejoue ce qui a été manqué (sans perte ni doublon) ; ``event: flux.reprise_impossible`` quand des
  événements ont été retirés depuis : le client relit la base.
- ``role=tablette`` (Employé) : ``appel.tour`` (transcription) ne lui est jamais envoyé. Le portail, qui tient la clé, déclare le rôle
  de la personne qu'il sert ; sans ``role`` : ``equipe``.
- Aucune connexion de base n'est gardée pendant que le flux dure.

``GET`` et ``PUT /restauration/etablissements/{etablissement_id}/temps`` (lot 6) : la puce du temps du portail. Lire = voir les conversations ;
écrire = l'écriture du portail (``portail.ecrire`` pour une clé). L'établissement est relu contre la base de l'organisation de la requête (404
sinon, sans dire pourquoi) ; l'écriture est journalisée avec son auteur, diffusée sur le flux (``temps.change``) et refusée quand la caisse porte
l'état (409 : la puce l'affiche sans le modifier, E-49).

Lot 15 : ``POST /restauration/etablissements/{id}/commandes/{numero}/statut`` ``{de, vers}`` : un pas du chemin fermé fait par le restaurant
depuis le portail (Rush). Permission ``portail.ecrire`` pour une clé (``agents.modifier`` pour une session). L'établissement est relu
contre la base de CETTE organisation (404 sinon), la commande contre l'établissement (404 sinon). 409 ``DEJA_FAIT`` (le même geste
rejoué : rien n'est écrasé, rien n'est émis) ou ``INTERDIT`` (le pas n'est pas permis, ou ``de`` n'est plus le statut actuel).
"""

from __future__ import annotations

import re
from typing import Literal

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from api.db.bases_clients.connexion import BaseClientIndisponible, connecter
from api.db.bases_clients.restauration_commande import TRANSITIONS
from api.db.bases_clients.restauration_commun import etablissements_existants
from api.db.bases_clients.restauration_temps import PAS_DE_CHANGEMENT, ecrire_temps, fin_du_service, temps_par_type
from api.db.models import UserModel
from api.schemas.restauration import TempsDemande, TempsRendu
from api.services.auth.depends import get_user_with_selected_organization
from api.services.base_client import rattachement
from api.services.restauration import flux, statut

router = APIRouter(prefix="/restauration", tags=["restauration"])

MAX_ETABLISSEMENTS = 50
_LISTE = re.compile(r"^[0-9]{1,12}(,[0-9]{1,12})*$")


def _refus(code: int, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail=message)


async def _etablissements_de_l_organisation(organization_id: int, demandes: str) -> list[int]:
    if not _LISTE.match(demandes.strip()):
        raise _refus(422, "etablissements: a comma-separated list of establishment identifiers.")
    ids = list(dict.fromkeys(int(x) for x in demandes.strip().split(",")))
    if len(ids) > MAX_ETABLISSEMENTS or 0 in ids:
        raise _refus(422, f"etablissements: between 1 and {MAX_ETABLISSEMENTS} identifiers.")
    nom = await rattachement.nom_de_la_base(organization_id)
    if not nom:
        raise _refus(409, "Attach a client database first: the establishments live there.")
    try:
        connexion = await connecter(nom)
    except BaseClientIndisponible as erreur:
        raise _refus(503, str(erreur)) from None
    try:
        existants = await etablissements_existants(connexion, ids)
    finally:
        await connexion.close()
    if existants != set(ids):
        raise _refus(404, "Establishment not found.")  # sans dire lequel : jamais un moyen de sonder les identifiants d'une autre organisation
    return ids


@router.get(
    "/flux",
    responses={200: {"description": "Server-sent events: one event per change, resumable with Last-Event-ID.", "content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
async def get_flux(
    request: Request,
    etablissements: str = Query(description="Establishment identifiers of the organization, separated by commas."),
    role: Literal["equipe", "tablette"] = Query(default="equipe", description="``tablette``: the transcription (appel.tour) is never sent."),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """The live feed of the establishments, for the portal and the fork screens."""
    ids = await _etablissements_de_l_organisation(user.selected_organization_id, etablissements)
    generateur = flux.ecouter(
        user.selected_organization_id, ids, role=role, reprise=last_event_id, est_deconnecte=request.is_disconnected,
        nb_battements_max=_battements_max(),
    )
    return StreamingResponse(
        generateur, media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}
    )


def _battements_max() -> int:
    """Une seule valeur de production ; les tests la baissent pour qu'une réponse en flux se termine."""
    return flux.NB_BATTEMENTS_MAX


# --------------------------------------------------------------------------- la puce du temps (lot 6)


async def _connexion_de_l_etablissement(organization_id: int, etablissement_id: int):
    """La connexion à la base de l'organisation, après avoir relu l'établissement dedans : un identifiant inconnu d'elle (d'une autre organisation,
    ou qui n'existe pas) est un 404 sans dire lequel."""
    nom = await rattachement.nom_de_la_base(organization_id)
    if not nom:
        raise _refus(409, "Attach a client database first: the establishments live there.")
    try:
        connexion = await connecter(nom)
    except BaseClientIndisponible as erreur:
        raise _refus(503, str(erreur)) from None
    try:
        if await etablissements_existants(connexion, [etablissement_id]) != {etablissement_id}:
            raise _refus(404, "Establishment not found.")
    except BaseException:
        await connexion.close()
        raise
    return connexion


@router.get("/etablissements/{etablissement_id}/temps", response_model=TempsRendu)
async def get_temps(etablissement_id: int, user: UserModel = Depends(get_user_with_selected_organization)) -> TempsRendu:
    """The state of each order type of the establishment and what the agent announces now (by zone for delivery)."""
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    try:
        async with _schema_a_jour(connexion):
            return TempsRendu.model_validate(await temps_par_type(connexion, etablissement_id))
    finally:
        await connexion.close()


@router.put("/etablissements/{etablissement_id}/temps", response_model=TempsRendu)
async def put_temps(etablissement_id: int, corps: TempsDemande, user: UserModel = Depends(get_user_with_selected_organization)) -> TempsRendu:
    """Set the time added on top of an order type (and its pause). Refused (409) when the till carries the state: the chip shows it, never changes it."""
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de_l_etablissement(user.selected_organization_id, etablissement_id)
    try:
        async with _schema_a_jour(connexion):
            jusqu_a = corps.jusqu_a
            if jusqu_a == "fin_du_service":
                jusqu_a = await fin_du_service(connexion, etablissement_id)
            pause = PAS_DE_CHANGEMENT
            if "pause" in corps.model_fields_set:
                pause = None if corps.pause is None else corps.pause.model_dump(exclude_none=True)
            r = await ecrire_temps(
                connexion, etablissement_id, corps.type, corps.minutes_ajoutees, jusqu_a, pause, source="portail", auteur=rattachement.auteur_de(user)
            )
            if r.statut == "REFUSEE":
                raise _refus(409, "The state is carried by the till: it is shown here and changed there.")
            if r.statut != "OK":
                raise _refus(422, f"Invalid value: {r.manque or 'request'}.")
            rendu = TempsRendu.model_validate(await temps_par_type(connexion, etablissement_id))
    finally:
        await connexion.close()
    await flux.emettre(user.selected_organization_id, etablissement_id, "temps.change", {"type": corps.type})
    return rendu


# --------------------------------------------------------------------------- le statut d'une commande (lot 15)


class ChangementDeStatut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    de: Literal[tuple(sorted(TRANSITIONS))]  # type: ignore[valid-type]
    vers: Literal[tuple(sorted(TRANSITIONS))]  # type: ignore[valid-type]


class StatutRendu(BaseModel):
    statut: str
    caisse_informee: bool


@router.post("/etablissements/{etablissement_id}/commandes/{numero}/statut", response_model=StatutRendu)
async def post_statut(
    corps: ChangementDeStatut,
    etablissement_id: int = Path(ge=1, le=10**12),
    numero: uuid.UUID = Path(),
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """One step of the closed order path, made by the restaurant from the portal."""
    from api.routes.base_client import _schema_a_jour

    organisation = user.selected_organization_id
    nom = await rattachement.nom_de_la_base(organisation)
    if not nom:
        raise _refus(409, "Attach a client database first: the establishments live there.")
    try:
        connexion = await connecter(nom)
    except BaseClientIndisponible as erreur:
        raise _refus(503, str(erreur)) from None
    try:
        if await etablissements_existants(connexion, [etablissement_id]) != {etablissement_id}:
            raise _refus(404, "Establishment not found.")
        async with _schema_a_jour(connexion):
            resultat, informee = await statut.changer_le_statut(organisation, connexion, etablissement_id, numero, corps.de, corps.vers)
    finally:
        await connexion.close()
    if resultat.statut == "OK":
        return StatutRendu(statut=corps.vers, caisse_informee=informee)
    if resultat.statut == "INTROUVABLE":
        raise _refus(404, "Order not found.")
    if resultat.statut in ("DEJA_FAIT", "INTERDIT"):
        raise HTTPException(status_code=409, detail={"code": resultat.statut, "statut": resultat.faits.get("statut_actuel")})
    raise _refus(422, "Invalid status.")
