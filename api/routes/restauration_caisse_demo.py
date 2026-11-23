"""[.mark] Module Restauration, lot 20 : les routes de la CAISSE DE DÉMO (Labo seulement, interrupteur d'environnement).

- ``GET|POST|PUT|PATCH|DELETE /restauration/caisse-demo/v1/{chemin}`` : l'interface de HubRise, servie par ``caisse_demo.moteur``. Sans session de compte : garde = jeton de
  la caisse de démo (en empreinte), organisation Labo, interrupteur allumé ; limite de débit par restaurant ; corps borné. Éteinte : 404.
- Les routes de l'écran (session d'un compte de l'équipe, organisation Labo seulement, 404 sinon pour ne rien dire de plus) :
  ``/restauration/caisse-demo/etat`` · ``/restaurants`` (liste, création, détail, réglage, copie, suppression) · ``/restaurants/{id}/gestes`` ·
  ``/restaurants/{id}/carte/import`` · ``/restaurants/{id}/carte/photo`` (scan W46) · ``/restaurants/{id}/brancher`` et ``/debrancher`` · ``/scenarios``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.responses import JSONResponse

from api.db import db_client
from api.db.models import UserModel
from api.schemas.restauration_caisse_demo import (
    BrancherDemo,
    CreerRestaurantDemande,
    EnregistrerScenarioDemande,
    GesteDemande,
    ImporterLaCarteDemande,
    LirePhotoDemande,
    MettreEnPlaceDemande,
    ReglerRestaurantDemande,
)
from api.services.auth.depends import get_user_with_selected_organization
from api.services.restauration.caisse.caisse_demo import branchement, garde, restaurants, scenarios
from api.services.restauration.caisse.caisse_demo.moteur import moteur
from api.services.restauration.caisse.prises import hubrise_traduction as ht

router = APIRouter(prefix="/restauration/caisse-demo", tags=["restauration"])

TAILLE_MAX_CORPS = 1_000_000  # octets d'une requête à la caisse de démo (HubRise en accepte bien moins)
DELAI_SILENCE_S = 15.0  # une caisse qui « ne répond pas » : plus que le délai de la prise (10 s), puis la connexion tombe
DELAI_MAX_S = 30.0
TAILLE_MAX_CARTE = 2_000_000
ENTETES_SANS_SECRET = {"retry-after", "x-cursor-next"}


def _refus(code: int, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail=message)


async def _labo(user: UserModel) -> int:
    """L'organisation du compte, si elle est le Labo et l'interrupteur allumé ; sinon 404 (la caisse de démo n'existe pas pour les autres)."""
    if not await garde.caisse_de_demo_permise(user.selected_organization_id):
        raise _refus(404, "Not found.")
    return user.selected_organization_id


# --------------------------------------------------------------------------- l'interface de HubRise (sans session : garde = jeton de la caisse de démo)


@router.api_route("/v1/{chemin:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
async def interface_de_la_caisse(chemin: str, request: Request) -> Response:
    """The demo till answers like HubRise (``/v1``). Off by default; Labo only."""
    if not garde.interrupteur_allume():
        raise _refus(404, "Not found.")
    brut = await request.body()
    if len(brut) > TAILLE_MAX_CORPS:
        return JSONResponse({"message": "Payload too large", "error_type": "payload_too_large"}, status_code=413)
    corps: Any = None
    if brut:
        try:
            corps = json.loads(brut)
        except ValueError:
            return JSONResponse({"message": "Invalid JSON", "error_type": "bad_request"}, status_code=400)
    reponse = await moteur.servir(request.headers.get("x-access-token"), request.method, "/" + chemin, dict(request.query_params), corps, exiger_labo=True)
    if reponse.silence:
        await asyncio.sleep(DELAI_SILENCE_S)
        return Response(status_code=504)
    if reponse.delai_s:
        await asyncio.sleep(min(reponse.delai_s, DELAI_MAX_S))
    entetes = {k: v for k, v in reponse.entetes.items() if k.lower() in ENTETES_SANS_SECRET}
    if reponse.corps is None:
        return Response(status_code=reponse.code, headers=entetes)
    return JSONResponse(reponse.corps, status_code=reponse.code, headers=entetes)


# --------------------------------------------------------------------------- l'écran Outils › Simulateurs › Caisse / POS


def _commande_rendue(c: dict[str, Any]) -> dict[str, Any]:
    o = c["corps"]
    return {
        "ref": c["ref"], "numero": c["private_ref"], "statut": c["statut"], "mode": o.get("service_type"), "total": o.get("total"), "heure_confirmee": o.get("confirmed_time"),
        "creee_le": c["cree_le"].isoformat(),
        "lignes": [
            {"nom": a.get("product_name"), "taille": a.get("sku_name"), "quantite": a.get("quantity"), "prix": a.get("subtotal"), "options": [x.get("name") for x in a.get("options") or [] if not x.get("removed")],
             # lot 16 : un retrait (« sans champignons ») n'est jamais lu comme un ajout : ``removed`` de la documentation HubRise
             "retires": [x.get("name") for x in a.get("options") or [] if x.get("removed")]}
            for a in o.get("items") or []
        ],
        "remises": [d.get("name") for d in o.get("discounts") or []], "paiements": [p.get("name") for p in o.get("payments") or []],
        # Nuit du 18/11 : ce que la caisse a reçu du client et la note (consigne pour le livreur), pour comparer à ce que la personne a dit.
        "client": {
            "prenom": (o.get("customer") or {}).get("first_name"), "telephone": (o.get("customer") or {}).get("phone"),
            "adresse": (o.get("customer") or {}).get("address_1"), "consigne_livraison": (o.get("customer") or {}).get("delivery_notes"),
        },
        "note": o.get("customer_notes"), "heure_voulue": o.get("expected_time"),
    }


async def _rendu(organization_id: int, r: dict[str, Any], *, detail: bool = False) -> dict[str, Any]:
    cle = await branchement.etablissement_du_restaurant(organization_id, r)
    sortie: dict[str, Any] = {
        "id": r["id"], "nom": r["nom"], "point_de_vente": r["point_de_vente"], "etat": r["etat"], "minutes_en_plus": r["minutes_en_plus"], "reglages": r["reglages"],
        "comportement": r["comportement"], "scenario": r["scenario"], "etablissement_cle": cle, "branche": cle is not None,
    }
    if detail:
        sortie.update(
            {
                "carte": r["carte"], "stocks": r["stocks"], "clients": r["clients"],
                "commandes": [_commande_rendue(c) for c in await db_client.lister_commandes_de_demo(r["id"], limite=50)],
                "messages": [
                    {"id": m["id"], "type": f"{m['corps']['resource_type']}.{m['corps']['event_type']}", "statut": m["statut"], "tentatives": m["tentatives"]}
                    for m in await db_client.lister_messages_de_demo(r["id"], 30)
                ],
            }
        )
    return sortie


async def _restaurant(organization_id: int, restaurant_id: int) -> dict[str, Any]:
    r = await db_client.lire_restaurant_de_demo(organization_id, restaurant_id)
    if r is None:
        raise _refus(404, "Test restaurant not found.")
    return r


def _valeur_refusee(erreur: Exception) -> HTTPException:
    return _refus(422, str(erreur))


@router.get("/etat")
async def get_etat(user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, Any]:
    """Whether the demo till exists for this account: the screen only shows itself when it does (Labo, switch on)."""
    return {"active": await garde.caisse_de_demo_permise(user.selected_organization_id), "adresse_interne": True}


@router.get("/appels/{appel_id}/reservation")
async def get_reservation_de_l_appel(
    appel_id: int = Path(ge=1, le=10**15), etablissement_id: int = Query(ge=1, le=10**12), user: UserModel = Depends(get_user_with_selected_organization)
) -> dict[str, Any]:
    """The booking this test call has made (time, covers, state, tables; never the caller's name or number): the Till / POS window shows it live. 404 when there is none."""
    org = await _labo(user)
    reservation = await branchement.reservation_de_l_appel(org, etablissement_id, appel_id)
    if reservation is None:
        raise _refus(404, "No booking for this call.")
    return reservation


@router.get("/restaurants")
async def get_restaurants(user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, Any]:
    org = await _labo(user)
    await scenarios.livrer(org)
    liste = [await _rendu(org, r) for r in await db_client.lister_restaurants_de_demo(org)]
    return {
        "restaurants": liste, "scenarios": [{"cle": k, **v} for k, v in (await scenarios.lire(org)).items()],
        "etablissements": await branchement.etablissements_du_labo(org),
    }


@router.post("/restaurants")
async def post_restaurant(corps: CreerRestaurantDemande, user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, Any]:
    org = await _labo(user)
    try:
        if corps.modele_de is not None:
            cree = await restaurants.dupliquer(org, corps.modele_de, corps.nom)
            if cree is None:
                raise _refus(404, "Test restaurant not found.")
        else:
            cree = await restaurants.creer(org, corps.nom)
        if corps.scenario:
            await scenarios.livrer(org)
            if await scenarios.mettre_en_place(org, cree["id"], corps.scenario) is None:
                raise _refus(404, "Scenario not found.")
    except restaurants.RestaurantDeTestRefuse as erreur:
        raise _valeur_refusee(erreur) from None
    return await _rendu(org, await _restaurant(org, cree["id"]), detail=True)


@router.get("/restaurants/{restaurant_id}")
async def get_restaurant(restaurant_id: int, user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, Any]:
    org = await _labo(user)
    return await _rendu(org, await _restaurant(org, restaurant_id), detail=True)


@router.put("/restaurants/{restaurant_id}")
async def put_restaurant(restaurant_id: int, corps: ReglerRestaurantDemande, user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, Any]:
    org = await _labo(user)
    try:
        r = await restaurants.regler(org, restaurant_id, corps.model_dump(exclude_none=True))
    except restaurants.RestaurantDeTestRefuse as erreur:
        raise _valeur_refusee(erreur) from None
    if r is None:
        raise _refus(404, "Test restaurant not found.")
    return await _rendu(org, r, detail=True)


@router.post("/restaurants/{restaurant_id}/dupliquer")
async def post_dupliquer(restaurant_id: int, user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, Any]:
    org = await _labo(user)
    cree = await restaurants.dupliquer(org, restaurant_id)
    if cree is None:
        raise _refus(404, "Test restaurant not found.")
    return await _rendu(org, cree, detail=True)


@router.delete("/restaurants/{restaurant_id}")
async def delete_restaurant(restaurant_id: int, user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, bool]:
    org = await _labo(user)
    await branchement.debrancher(org, restaurant_id)  # libère le point de vente avant de retirer le restaurant
    if not await db_client.supprimer_restaurant_de_demo(org, restaurant_id):
        raise _refus(404, "Test restaurant not found.")
    return {"ok": True}


@router.post("/restaurants/{restaurant_id}/gestes")
async def post_geste(restaurant_id: int, corps: GesteDemande, user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, bool]:
    """The till does something during a call (out of stock, price, state, order status): it says so with a signed message, like a real till."""
    org = await _labo(user)
    await _restaurant(org, restaurant_id)
    ok = False
    if corps.geste == "rupture" and corps.code and corps.disponible is not None:
        ok = await restaurants.poser_une_rupture(org, restaurant_id, corps.code, corps.disponible)
    elif corps.geste == "prix" and corps.code and corps.prix is not None:
        ok = await restaurants.changer_un_prix(org, restaurant_id, corps.code, corps.prix)
    elif corps.geste == "etat" and corps.etat:
        ok = await restaurants.changer_l_etat_par_la_caisse(org, restaurant_id, corps.etat, corps.minutes_en_plus or 0)
    elif corps.geste == "commande" and corps.ref and (corps.statut or corps.heure_confirmee):
        ok = await restaurants.changer_une_commande(org, restaurant_id, corps.ref, corps.statut, corps.heure_confirmee)
    if not ok:
        raise _refus(422, "Nothing to do: unknown code, order or missing field.")
    return {"ok": True}


@router.post("/restaurants/{restaurant_id}/carte/import")
async def post_import_carte(restaurant_id: int, corps: ImporterLaCarteDemande, user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, Any]:
    """Replace the menu of the test restaurant by a menu file in the common format."""
    org = await _labo(user)
    if len(json.dumps(corps.carte, default=str)) > TAILLE_MAX_CARTE:
        raise _refus(413, "The menu file is too large.")
    try:
        ht.carte_vers_hubrise(corps.carte)  # une carte que la caisse ne saurait pas rendre est refusée avant d'être gardée
        r = await restaurants.regler(org, restaurant_id, {"carte": corps.carte})
    except (restaurants.RestaurantDeTestRefuse, ht.TraductionImpossible, KeyError, TypeError, ValueError, AttributeError):
        raise _refus(422, "The file is not a menu in the common format. Nothing was imported.") from None
    if r is None:
        raise _refus(404, "Test restaurant not found.")
    return {"produits": len(r["carte"].get("produits", [])), "categories": len(r["carte"].get("categories", []))}


@router.post("/restaurants/{restaurant_id}/brancher")
async def post_brancher(restaurant_id: int, corps: BrancherDemo, user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, Any]:
    """This test restaurant becomes the one the agent of the establishment plays (the real HubRise socket is plugged in to the demo till)."""
    org = await _labo(user)
    try:
        bilan = await branchement.brancher(org, user.id, restaurant_id, corps.etablissement_id)
    except branchement.BranchementDeDemoRefuse as erreur:
        code = {"non_permis": 404, "restaurant_inconnu": 404, "etablissement_inconnu": 404, "base_absente": 409, "deja_pris": 409}[erreur.code]
        raise _refus(code, "Cannot plug the test restaurant in.") from None
    return {"ok": True, "passif": bilan["passif"]}


@router.post("/restaurants/{restaurant_id}/debrancher")
async def post_debrancher(restaurant_id: int, user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, bool]:
    org = await _labo(user)
    await _restaurant(org, restaurant_id)
    return {"ok": await branchement.debrancher(org, restaurant_id)}


@router.post("/restaurants/{restaurant_id}/scenario")
async def post_mettre_en_place(restaurant_id: int, corps: MettreEnPlaceDemande, user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, Any]:
    org = await _labo(user)
    await _restaurant(org, restaurant_id)
    await scenarios.livrer(org)
    r = await scenarios.mettre_en_place(org, restaurant_id, corps.scenario)
    if r is None:
        raise _refus(404, "Scenario not found.")
    return await _rendu(org, r, detail=True)


@router.post("/restaurants/{restaurant_id}/scenarios")
async def post_enregistrer_scenario(restaurant_id: int, corps: EnregistrerScenarioDemande, user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, str]:
    org = await _labo(user)
    try:
        return {"cle": await scenarios.enregistrer(org, restaurant_id, corps.nom)}
    except scenarios.ScenarioRefuse as erreur:
        raise _valeur_refusee(erreur) from None


@router.delete("/scenarios/{cle}")
async def delete_scenario(cle: str, user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, bool]:
    org = await _labo(user)
    if not await scenarios.supprimer(org, cle):
        raise _refus(404, "Scenario not found.")
    return {"ok": True}


@router.post("/restaurants/{restaurant_id}/carte/photo")
async def post_lire_une_photo(restaurant_id: int, corps: LirePhotoDemande, user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, Any]:
    """Read a photo of a menu (scan W46) and propose it in the common format: nothing is written, the person reviews then imports."""
    from api.routes.restauration_scan import lire_une_photo

    org = await _labo(user)
    await _restaurant(org, restaurant_id)
    return await lire_une_photo(org, corps, avec_codes=True)  # un restaurant de test doit pouvoir VENDRE : un code de caisse est fabriqué
