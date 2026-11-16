"""[.mark] Module Restauration, lot 20 : le MOTEUR de la caisse de démo, qui répond avec l'interface de HubRise (``/v1``).

Écrit d'après la documentation de HubRise lue le 15/11 et les réponses enregistrées (``api/tests/mark/reponses_hubrise/``, numéro cité) : mêmes routes, mêmes
formes (``error_type``, 422 avec la liste des champs, 401 sans jeton valable, 404, 429 avec ``Retry-After``), mêmes montants écrits ``12.50 EUR``. La prise HubRise
réelle lui parle sans code spécial : seule son adresse change (liste fermée, Labo seulement).

Routes : ``GET|PATCH /location`` · ``GET|PUT /catalogs/:id`` · ``GET|PATCH|PUT /catalogs/:id/locations/:pdv/inventory`` · ``GET|POST /customer_lists/:id/customers``
· ``GET|POST /location/orders`` · ``GET|PATCH /location/orders/:id`` · ``GET|POST /callback`` · ``GET /callback/events`` · ``DELETE /callback/events/:id``.

Le COMPORTEMENT du restaurant de test (``comportement``) décide de ce que fait la caisse :

- ``reponse`` : ``accepte`` (défaut) · ``controle`` (refuse ce qui ne colle pas à sa carte, ``controles`` en liste fermée : ``produit_inconnu``, ``prix_different``,
  ``ferme``, ``remise_inconnue``, tous par défaut) · ``silence`` (ne répond pas) · ``panne`` (erreur 500) ;
- ``delai_s`` : le temps qu'elle met à répondre ; ``acceptation`` : ``auto`` (défaut, elle accepte et le dit par un message signé) · ``manuelle`` · ``refus`` ;
- ``doublon`` : ses messages sont rendus deux fois (``messages.py``) ; ``limite_commandes`` : lectures de commandes par minute (10, comme HubRise) ;
- ``rupture_plein_appel`` · ``carte_changee`` · ``commande_deux_fois`` : les imprévus pendant l'appel, déclenchés tout seuls (``imprevus.py``).

Jamais d'heure lue ici : la source d'heure de l'organisation du restaurant (D6). Un restaurant ne voit que SES données : le jeton retrouve le restaurant, et
chaque identifiant de l'adresse (catalogue, liste de clients, point de vente) est contrôlé contre lui.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import redis.asyncio as aioredis

from api.constants import REDIS_URL
from api.db import db_client
from api.db.bases_clients.horloge import horloge
from api.services.restauration.caisse_demo import garde, imprevus, messages
from api.services.restauration.caisse_demo.catalogue import carte_vide, catalogue_de_lecture, codes_vendables
from api.services.restauration.prises import hubrise_traduction as ht

STATUTS = ("new", "received", "accepted", "in_preparation", "awaiting_shipment", "awaiting_collection", "in_delivery", "completed", "rejected", "cancelled")
TYPES_DE_SERVICE = ("collection", "delivery", "eat_in")
CONTROLES = ("produit_inconnu", "prix_different", "ferme", "remise_inconnue")
LIMITE_PAR_MINUTE = 500
LIMITE_COMMANDES_PAR_MINUTE = 10  # lecture des commandes (documentation general-concepts)
COMMANDES_PAR_PAGE = 100
NOM_CANAL = "Caisse de démo .mark"
_MONTANT = re.compile(r"^-?\d+(\.\d{1,2})? [A-Z]{3}$")
_NOMBRE = re.compile(r"^-?\d+(\.\d+)?$")
MODE_DE_L_ETAT = {"ouvert": "normal", "deborde": "busy", "ferme": "paused"}
ETAT_DU_MODE = {v: k for k, v in MODE_DE_L_ETAT.items()}


@dataclass
class Reponse:
    code: int
    corps: Any = None
    entetes: dict[str, str] = field(default_factory=dict)
    silence: bool = False  # la caisse ne répond pas : l'appelant attend jusqu'à son délai
    delai_s: float = 0.0  # le temps qu'elle met à répondre


def erreur(code: int, message: str, type_: str, champs: list[tuple[str, str]] | None = None, **entetes: str) -> Reponse:
    corps: dict[str, Any] = {"message": message}
    if champs:
        corps["errors"] = [{"field": c, "message": m} for c, m in champs]
    corps["error_type"] = type_
    return Reponse(code, corps, dict(entetes))


def empreinte_du_jeton(jeton: str) -> str:
    return hashlib.sha256(jeton.encode("utf-8")).hexdigest()


def compte_de(restaurant: dict[str, Any]) -> str:
    return restaurant["point_de_vente"].rsplit("-", 1)[0]


def catalogue_id_de(restaurant: dict[str, Any]) -> str:
    return compte_de(restaurant) + "-cat"


def liste_de_clients_de(restaurant: dict[str, Any]) -> str:
    return compte_de(restaurant) + "-cli"


def _identifiant() -> str:
    return secrets.token_hex(4)[:7]


def _euros(centimes: int) -> str:
    return ht.euros(centimes)


def _centimes(montant: str) -> int:
    return ht.centimes(montant)


async def _debit(restaurant: dict[str, Any], categorie: str, limite: int) -> int | None:
    """``None`` : dans la limite ; sinon les secondes à attendre (429). Compteur par minute, partagé entre processus (Redis)."""
    maintenant = horloge(restaurant["organization_id"]).maintenant()
    fenetre = int(maintenant.timestamp() // 60)
    cle = f"mark:caissedemo:debit:{restaurant['id']}:{categorie}:{fenetre}"
    redis = aioredis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2, socket_connect_timeout=2)
    try:
        n = await redis.incr(cle)
        if n == 1:
            await redis.expire(cle, 90)
    except Exception:  # noqa: BLE001 -- R1 : un Redis en panne ne bloque pas la caisse de démo (pas de limite plutôt qu'une panne)
        return None
    finally:
        await redis.aclose()
    return None if n <= limite else max(1, 60 - int(maintenant.timestamp() % 60))


# --------------------------------------------------------------------------- les objets rendus


def point_de_vente_rendu(r: dict[str, Any]) -> dict[str, Any]:
    reglages = r["reglages"]
    mode = MODE_DE_L_ETAT.get(r["etat"], "normal")
    reception: dict[str, Any] = {"mode": mode}
    if mode == "busy":
        reception.update({"extra_preparation_time": r["minutes_en_plus"], "resume_at": reglages.get("reprise")})
    elif mode == "paused":
        reception["resume_at"] = reglages.get("reprise")
    return {
        "id": r["point_de_vente"], "name": r["nom"], "account": {"id": compte_de(r), "name": reglages.get("enseigne") or r["nom"], "currency": "EUR"},
        "address": reglages.get("adresse", "1 rue de Test"), "postal_code": reglages.get("code_postal", "60000"), "city": reglages.get("ville", "Beauvais"), "country": "FR",
        "timezone": {"name": "Europe/Paris", "offset": 3600}, "cutoff_time": "06:00", "opening_hours": reglages.get("horaires"),
        "preparation_time": reglages.get("delai", 20), "order_acceptance": reception, "custom_fields": {},
    }


def _client_rendu(r: dict[str, Any], c: dict[str, Any]) -> dict[str, Any]:
    cree = c.get("created_at") or r["cree_le"].strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "id": c["id"], "customer_list_id": liste_de_clients_de(r), "anonymised": False, "private_ref": None, "email": c.get("email"), "first_name": c.get("first_name"),
        "last_name": c.get("last_name"), "gender": None, "birth_date": None, "created_at": cree, "company_name": None, "phone": c.get("phone"), "phone_access_code": None,
        "address_1": c.get("address_1"), "address_2": None, "postal_code": c.get("postal_code"), "city": c.get("city"), "state": None, "country": None,
        "latitude": None, "longitude": None, "delivery_notes": c.get("delivery_notes"), "sms_marketing": False, "email_marketing": False, "nb_orders": c.get("nb_orders", 0),
        "order_total": c.get("order_total", "0.00 EUR"), "first_order_date": None, "last_order_date": None, "loyalty_cards": [], "custom_fields": {},
    }


# --------------------------------------------------------------------------- une commande reçue


def _valider_la_commande(corps: Any) -> list[tuple[str, str]]:
    """Les champs refusés, au format de HubRise (``/items/0/price`` : ``has invalid format ('12,50' given)``, réponses 15, 16, 17)."""
    if not isinstance(corps, dict):
        return [("/", "must be an object")]
    erreurs: list[tuple[str, str]] = []
    if "status" not in corps:
        erreurs.append(("/status", "is required"))
    elif corps["status"] not in STATUTS:
        erreurs.append(("/status", f"is not a valid status ('{corps['status']}' given)"))
    if corps.get("service_type") is not None and corps["service_type"] not in TYPES_DE_SERVICE:
        erreurs.append(("/service_type", f"is not a valid service type ('{corps['service_type']}' given)"))

    def montant(chemin: str, valeur: Any) -> None:
        if not isinstance(valeur, str) or not _MONTANT.match(valeur):
            erreurs.append((chemin, f"has invalid format ('{valeur}' given)"))

    items = corps.get("items", [])
    if not isinstance(items, list):
        erreurs.append(("/items", "must be an array"))
        items = []
    deals = corps.get("deals") or {}
    for i, a in enumerate(items):
        if not isinstance(a, dict):
            erreurs.append((f"/items/{i}", "must be an object"))
            continue
        if not a.get("product_name"):
            erreurs.append((f"/items/{i}/product_name", "is required"))
        montant(f"/items/{i}/price", a.get("price"))
        if not _NOMBRE.match(str(a.get("quantity", ""))):
            erreurs.append((f"/items/{i}/quantity", f"has invalid format ('{a.get('quantity')}' given)"))
        for j, o in enumerate(a.get("options") or []):
            if not isinstance(o, dict) or not o.get("name") or not o.get("option_list_name"):
                erreurs.append((f"/items/{i}/options/{j}", "name and option_list_name are required"))
                continue
            montant(f"/items/{i}/options/{j}/price", o.get("price"))
        cle = (a.get("deal_line") or {}).get("deal_key") if isinstance(a.get("deal_line"), dict) else None
        if cle is not None and str(cle) not in {str(k) for k in deals}:
            erreurs.append((f"/items/{i}/deals", f"deal not found ({{'key':'{cle}'}} given)"))
    for j, r in enumerate(corps.get("discounts") or []):
        if isinstance(r, dict) and r.get("price_off") is not None:
            montant(f"/discounts/{j}/price_off", r["price_off"])
    for j, c in enumerate(corps.get("charges") or []):
        if isinstance(c, dict):
            montant(f"/charges/{j}/price", c.get("price"))
    for j, p in enumerate(corps.get("payments") or []):
        if isinstance(p, dict):
            montant(f"/payments/{j}/amount", p.get("amount"))
    return erreurs


def _controler_comme_une_caisse_stricte(restaurant: dict[str, Any], corps: dict[str, Any]) -> list[tuple[str, str]]:
    """Ce que refuse une caisse qui compare la commande à SA carte (les codes d'erreur sont ceux du format de HubRise)."""
    actifs = set((restaurant["comportement"] or {}).get("controles") or CONTROLES)
    erreurs: list[tuple[str, str]] = []
    if "ferme" in actifs and restaurant["etat"] == "ferme":
        erreurs.append(("/", "the location is not accepting orders"))
    carte = restaurant["carte"] or carte_vide()
    vendables = codes_vendables(carte)
    for i, a in enumerate(corps.get("items") or []):
        code = a.get("sku_ref")
        if "produit_inconnu" in actifs and code not in vendables:
            erreurs.append((f"/items/{i}/sku_ref", f"sku not found ('{code}' given)"))
        elif "prix_different" in actifs and _centimes(a["price"]) != vendables[code]:
            erreurs.append((f"/items/{i}/price", f"does not match the catalog price ('{a['price']}' given)"))
        for j, o in enumerate(a.get("options") or []):
            if "produit_inconnu" in actifs and o.get("ref") and o["ref"] not in vendables:
                erreurs.append((f"/items/{i}/options/{j}/ref", f"option not found ('{o['ref']}' given)"))
    connues = {d["ref"] for d in (restaurant["reglages"] or {}).get("remises", [])}
    for j, d in enumerate(corps.get("discounts") or []):
        if "remise_inconnue" in actifs and d.get("ref") and d["ref"] not in connues:
            erreurs.append((f"/discounts/{j}/ref", f"discount not found ('{d['ref']}' given)"))
    return erreurs


def _calculer(corps: dict[str, Any]) -> dict[str, Any]:
    """Les montants que HubRise recalcule : sous-total par ligne (prix + options) × quantité, remise de ligne de formule, total, écart de paiement."""
    lignes = []
    total = 0
    for a in corps.get("items") or []:
        quantite = Decimal(str(a.get("quantity", 1)))
        unitaire = _centimes(a["price"])
        for o in a.get("options") or []:
            if not o.get("removed"):
                unitaire += _centimes(o.get("price") or "0.00 EUR") * int(o.get("quantity", 1))
        sous_total = int((Decimal(unitaire) * quantite).to_integral_value())
        ligne = a.get("deal_line") or {}
        if ligne.get("pricing_effect") == "percentage_off" and ligne.get("pricing_value") is not None:
            sous_total = int((Decimal(sous_total) * (Decimal(100) - Decimal(str(ligne["pricing_value"]))) / 100).to_integral_value())
        total += sous_total
        lignes.append(sous_total)
    total -= sum(_centimes(r["price_off"]) for r in corps.get("discounts") or [] if r.get("price_off"))
    total += sum(_centimes(c["price"]) for c in corps.get("charges") or [] if c.get("price"))
    payes = sum(_centimes(p["amount"]) for p in corps.get("payments") or [] if p.get("amount"))
    return {"sous_totaux": lignes, "total": total, "ecart": total - payes}


def _ordre_complet(restaurant: dict[str, Any], corps: dict[str, Any], identifiant: str, quand: str) -> dict[str, Any]:
    calcul = _calculer(corps)
    items = []
    for a, sous_total in zip(corps.get("items") or [], calcul["sous_totaux"], strict=True):
        items.append(
            {
                "id": _identifiant(), "private_ref": a.get("private_ref"), "product_name": a["product_name"], "sku_name": a.get("sku_name"), "sku_ref": a.get("sku_ref"),
                "price": a["price"], "quantity": f"{Decimal(str(a.get('quantity', 1))):.1f}", "subtotal": _euros(sous_total), "tax_rate": None, "subset": None,
                "customer_notes": a.get("customer_notes"), "points_earned": None, "points_used": None,
                "options": [{"quantity": 1, **o} for o in a.get("options") or []], "deleted": False,
                **({"deal_line": {"position": None, "pricing_value": None, **a["deal_line"]}} if a.get("deal_line") else {}),
            }
        )
    client = {
        "id": None, "customer_list_id": None, "anonymised": False, "private_ref": None, "email": None, "first_name": None, "last_name": None, "gender": None, "birth_date": None,
        "created_at": quand, "company_name": None, "phone": None, "phone_access_code": None, "address_1": None, "address_2": None, "postal_code": None, "city": None,
        "state": None, "country": None, "latitude": None, "longitude": None, "delivery_notes": None, "sms_marketing": False, "email_marketing": False, "nb_orders": 1,
        "order_total": _euros(calcul["total"]), "first_order_date": quand, "last_order_date": quand, "loyalty_cards": [], "custom_fields": {},
    } | (corps.get("customer") or {})
    return {
        "id": identifiant, "location_id": restaurant["point_de_vente"], "ref": None, "private_ref": corps.get("private_ref"), "status": corps["status"],
        "service_type": corps.get("service_type"), "service_type_ref": None, "created_at": quand, "created_by": NOM_CANAL, "channel": NOM_CANAL, "connection_name": None,
        "expected_time": corps.get("expected_time"), "expected_time_pickup": None, "asap": corps.get("expected_time") is None, "confirmed_time": None, "driver_pickup_url": None,
        "customer_notes": corps.get("customer_notes"), "seller_notes": None, "collection_code": None, "coupon_codes": [], "total": _euros(calcul["total"]),
        "total_discrepancy": None, "payment_discrepancy": _euros(calcul["ecart"]), "items": items, "deals": corps.get("deals") or {},
        "discounts": [
            {"id": _identifiant(), "private_ref": None, "ref": None, "pricing_effect": "price_off", "pricing_value": d.get("price_off"), "deleted": False, **d}
            for d in corps.get("discounts") or []
        ],
        "charges": [
            {"id": _identifiant(), "private_ref": None, "type": "other", "ref": None, "tax_rate": None, "charge_type": "other", "charge_ref": c.get("ref"), "charge_price": c.get("price"), "deleted": False, **c}
            for c in corps.get("charges") or []
        ],
        "payments": [{"id": _identifiant(), "private_ref": None, "type": "online", "info": None, "deleted": False, **p} for p in corps.get("payments") or []],
        "customer": client, "delivery_quotes": [], "delivery": None, "loyalty_operations": [], "custom_fields": {},
    }


# --------------------------------------------------------------------------- le moteur


class Moteur:
    """Répond à une requête ``/v1`` pour le restaurant de test que le jeton désigne. ``servir`` ne lève jamais : une erreur interne est un 500 sans détail."""

    async def servir(
        self, jeton: str | None, methode: str, chemin: str, params: dict[str, str] | None = None, corps: Any = None, *, exiger_labo: bool = False
    ) -> Reponse:
        """``exiger_labo`` : la route du réseau le pose ; le restaurant doit être celui de l'organisation Labo (sinon 401, comme un jeton faux)."""
        restaurant = await db_client.lire_restaurant_de_demo_par_jeton(empreinte_du_jeton(jeton)) if jeton else None
        if restaurant is not None and exiger_labo and not await garde.organisation_est_labo(restaurant["organization_id"]):
            restaurant = None
        if restaurant is None:
            return erreur(401, "The access token is invalid or the connection has been revoked", "unauthorized")
        comportement = restaurant["comportement"] or {}
        if comportement.get("reponse") == "silence":
            return Reponse(0, silence=True)
        if comportement.get("reponse") == "panne":
            return erreur(500, "Internal server error", "internal_server_error")
        attente = await _debit(restaurant, "general", LIMITE_PAR_MINUTE)
        if attente is not None:
            return erreur(429, "Rate limit exceeded", "too_many_requests", **{"Retry-After": str(attente)})
        reponse = await self._router(restaurant, methode.upper(), chemin.rstrip("/") or "/", params or {}, corps)
        reponse.delai_s = float(comportement.get("delai_s") or 0)
        return reponse

    async def _router(self, r: dict[str, Any], methode: str, chemin: str, params: dict[str, str], corps: Any) -> Reponse:
        if chemin == "/location":
            if methode == "GET":
                return Reponse(200, point_de_vente_rendu(r))
            if methode == "PATCH":
                return await self._changer_l_etat(r, corps)
        elif chemin == "/location/orders":
            if methode == "POST":
                return await self._creer_la_commande(r, corps)
            if methode == "GET":
                return await self._lister_les_commandes(r, params)
        elif m := re.fullmatch(r"/location/orders/([A-Za-z0-9]{1,20})", chemin):
            if methode == "GET":
                return await self._lire_la_commande(r, m.group(1))
            if methode == "PATCH":
                return await self._changer_la_commande(r, m.group(1), corps)
        elif m := re.fullmatch(r"/catalogs/([^/]+)", chemin):
            if m.group(1) != catalogue_id_de(r):
                return erreur(404, "Catalog does not exist", "not_found")
            if methode == "GET":
                lue = Reponse(200, self._catalogue(r))
                await imprevus.changer_un_prix_apres_la_lecture(r)  # la carte est rendue telle qu'elle était ; le prix change juste après
                return lue
            if methode == "PUT":
                return await self._ecrire_le_catalogue(r, corps)
        elif m := re.fullmatch(r"/catalogs/([^/]+)/locations/([^/]+)/inventory", chemin):
            if m.group(1) != catalogue_id_de(r) or m.group(2) != r["point_de_vente"]:
                return erreur(404, "Inventory does not exist", "not_found")
            if methode == "GET":
                return Reponse(200, r["stocks"])
            if methode in ("PATCH", "PUT"):
                return await self._ecrire_l_inventaire(r, corps, remplacer=methode == "PUT")
        elif m := re.fullmatch(r"/customer_lists/([^/]+)/customers", chemin):
            if m.group(1) != liste_de_clients_de(r):
                return erreur(404, "Customer list does not exist", "not_found")
            if methode == "GET":
                return self._chercher_les_clients(r, params)
            if methode == "POST":
                return await self._creer_le_client(r, corps)
        elif chemin == "/callback":
            if methode in ("GET",):
                return Reponse(200, {"url": r["callback_url"], "events": r["callback_evenements"] or {}})  # réponse 25a : jamais abonné = {}
            if methode == "POST":
                return await self._poser_le_rappel(r, corps)
        elif chemin == "/callback/events" and methode == "GET":
            return Reponse(200, await messages.evenements_gardes(r))
        elif m := re.fullmatch(r"/callback/events/([A-Za-z0-9]{1,40})", chemin):
            if methode == "DELETE":
                return Reponse(200, None) if await messages.acquitter(r, m.group(1)) else erreur(404, "Event does not exist", "not_found")
        return erreur(404, "Not found", "not_found")

    # ---- le point de vente
    async def _changer_l_etat(self, r: dict[str, Any], corps: Any) -> Reponse:
        """``PATCH /location`` : ``order_acceptance`` et/ou ``preparation_time`` (réponses 07, 08 et 24b : le temps de préparation SEUL est accepté, et gardé)."""
        corps = corps if isinstance(corps, dict) else {}
        reception, temps = corps.get("order_acceptance"), corps.get("preparation_time")
        if temps is not None and (isinstance(temps, bool) or not isinstance(temps, int) or temps < 0):
            return erreur(422, "Validation failed", "unprocessable_entity", [("/preparation_time", "has invalid format")])
        if temps is None or reception is not None:
            if not isinstance(reception, dict) or reception.get("mode") not in ETAT_DU_MODE:
                return erreur(422, "Validation failed", "unprocessable_entity", [("/order_acceptance/mode", "is not a valid mode")])
        champs: dict[str, Any] = {}
        reglages = dict(r["reglages"])
        if isinstance(reception, dict):
            champs = {"etat": ETAT_DU_MODE[reception["mode"]], "minutes_en_plus": int(reception.get("extra_preparation_time") or 0)}
            reglages["reprise"] = reception.get("resume_at")
        if temps is not None:
            reglages["delai"] = temps
        champs["reglages"] = reglages
        r2 = await db_client.modifier_restaurant_de_demo(r["organization_id"], r["id"], champs, horloge(r["organization_id"]).maintenant())
        return Reponse(200, point_de_vente_rendu(r2 or r))

    # ---- la carte et l'inventaire
    def _catalogue(self, r: dict[str, Any]) -> dict[str, Any]:
        return catalogue_de_lecture(
            catalogue_id=catalogue_id_de(r), compte_id=compte_de(r), nom=(r["reglages"].get("enseigne") or r["nom"]), carte=r["carte"], remises=r["reglages"].get("remises", []), cree_le=r["cree_le"],
            frais=r["reglages"].get("frais"),
        )

    async def _ecrire_le_catalogue(self, r: dict[str, Any], corps: Any) -> Reponse:
        if not isinstance(corps, dict) or not isinstance(corps.get("data"), dict):
            return erreur(422, "Validation failed", "unprocessable_entity", [("/data", "is required")])
        try:
            carte = ht.carte_de_hubrise({"data": corps["data"]}).carte
        except (KeyError, TypeError, ht.TraductionImpossible):
            return erreur(422, "Validation failed", "unprocessable_entity", [("/data", "has invalid format")])
        remises = [
            {"ref": d["ref"], "nom": d.get("name"), "effet": ht.EFFET_DE_HUBRISE.get(d.get("pricing_effect"), "inchange"), "valeur": d.get("pricing_value")}
            for d in corps["data"].get("discounts") or [] if isinstance(d, dict) and d.get("ref")
        ]
        frais = [c for c in corps["data"].get("charges") or [] if isinstance(c, dict) and c.get("ref")]
        champs = {"carte": carte, "reglages": {**r["reglages"], "remises": remises, "frais": frais}}
        r2 = await db_client.modifier_restaurant_de_demo(r["organization_id"], r["id"], champs, horloge(r["organization_id"]).maintenant())
        return Reponse(200, self._catalogue(r2 or r))

    async def _ecrire_l_inventaire(self, r: dict[str, Any], corps: Any, *, remplacer: bool) -> Reponse:
        if not isinstance(corps, list):
            return erreur(422, "Validation failed", "unprocessable_entity", [("/", "must be an array")])
        erreurs = [(f"/{i}", "sku_ref or option_ref is required") for i, ligne in enumerate(corps) if not isinstance(ligne, dict) or not (ligne.get("sku_ref") or ligne.get("option_ref"))]
        if erreurs:
            return erreur(422, "Validation failed", "unprocessable_entity", erreurs)
        actuel = {} if remplacer else {(s.get("sku_ref") or s.get("option_ref")): s for s in r["stocks"]}
        for ligne in corps:
            code = ligne.get("sku_ref") or ligne.get("option_ref")
            if ligne.get("stock") is None and not remplacer:
                actuel.pop(code, None)  # PATCH : « stock: null » retire la limite ; PUT l'ignore (documentation inventories)
            elif ligne.get("stock") is not None:
                actuel[code] = {("sku_ref" if ligne.get("sku_ref") else "option_ref"): code, "stock": f"{Decimal(str(ligne['stock'])):.1f}", "expires_at": ligne.get("expires_at")}
        stocks = list(actuel.values())
        await db_client.modifier_restaurant_de_demo(r["organization_id"], r["id"], {"stocks": stocks}, horloge(r["organization_id"]).maintenant())
        return Reponse(200, stocks)

    # ---- les clients
    def _chercher_les_clients(self, r: dict[str, Any], params: dict[str, str]) -> Reponse:
        telephone = params.get("phone")
        trouves = [c for c in r["clients"] if telephone is None or c.get("phone") == telephone]
        return Reponse(200, [_client_rendu(r, c) for c in trouves])

    async def _creer_le_client(self, r: dict[str, Any], corps: Any) -> Reponse:
        if not isinstance(corps, dict) or not (corps.get("phone") or corps.get("email") or corps.get("last_name")):
            return erreur(422, "Validation failed", "unprocessable_entity", [("/phone", "is required")])
        client = {"id": _identifiant(), "created_at": horloge(r["organization_id"]).maintenant().isoformat(), **{k: corps.get(k) for k in ("first_name", "last_name", "phone", "email", "address_1", "postal_code", "city", "delivery_notes")}}
        await db_client.modifier_restaurant_de_demo(r["organization_id"], r["id"], {"clients": [*r["clients"], client]}, horloge(r["organization_id"]).maintenant())
        return Reponse(200, _client_rendu(r, client))

    # ---- le rappel (les messages signés)
    async def _poser_le_rappel(self, r: dict[str, Any], corps: Any) -> Reponse:
        if not isinstance(corps, dict) or "url" not in corps:
            return erreur(422, "Validation failed", "unprocessable_entity", [("/url", "is required")])
        url = corps.get("url")
        if url is not None and not messages.url_de_rappel_permise(url):
            return erreur(422, "Validation failed", "unprocessable_entity", [("/url", "is not a valid callback url")])
        await db_client.modifier_restaurant_de_demo(
            r["organization_id"], r["id"], {"callback_url": url, "callback_evenements": corps.get("events")}, horloge(r["organization_id"]).maintenant()
        )
        return Reponse(200, {"url": url, "events": corps.get("events")})

    # ---- les commandes
    async def _creer_la_commande(self, r: dict[str, Any], corps: Any) -> Reponse:
        erreurs = _valider_la_commande(corps)
        if erreurs:
            return erreur(422, "Validation failed", "unprocessable_entity", erreurs)
        comportement = r["comportement"] or {}
        if comportement.get("reponse") == "controle":
            refus = _controler_comme_une_caisse_stricte(r, corps)
            if refus:
                return erreur(422, "Validation failed", "unprocessable_entity", refus)
        maintenant = horloge(r["organization_id"]).maintenant()
        identifiant = _identifiant()
        ordre = _ordre_complet(r, corps, identifiant, maintenant.isoformat())
        await db_client.ajouter_commande_de_demo(r["id"], identifiant, ordre["private_ref"], ordre["status"], ordre, maintenant)
        decision = {"auto": "accepted", "refus": "rejected"}.get(comportement.get("acceptation", "auto"))
        en_rupture = imprevus.rupture_visee(r, ordre)
        if en_rupture:
            decision = "rejected"  # le produit vient de passer en rupture : la caisse refuse la commande
        if decision and ordre["status"] in ("new", "received"):
            await self._decider(r, identifiant, decision, maintenant)  # la caisse accepte (ou refuse) après coup et le dit par un message signé
        if en_rupture:
            await imprevus.mettre_en_rupture(r, en_rupture)
        if comportement.get("commande_deux_fois"):
            await imprevus.recevoir_une_seconde_fois(r, ordre, _identifiant())
        return Reponse(200, ordre)

    async def _decider(self, r: dict[str, Any], identifiant: str, statut: str, maintenant) -> None:
        ligne = await db_client.lire_commande_de_demo(r["id"], identifiant)
        if ligne is None:
            return
        corps = {**ligne["corps"], "status": statut}
        await db_client.modifier_commande_de_demo(r["id"], identifiant, statut, corps, maintenant)
        await messages.poster(r, "order", "update", order_id=identifiant, new_state={"status": statut})

    async def _lire_la_commande(self, r: dict[str, Any], identifiant: str) -> Reponse:
        ligne = await db_client.lire_commande_de_demo(r["id"], identifiant)
        return Reponse(200, ligne["corps"]) if ligne else erreur(404, "Order does not exist", "not_found")

    async def _lister_les_commandes(self, r: dict[str, Any], params: dict[str, str]) -> Reponse:
        limite = int((r["comportement"] or {}).get("limite_commandes") or LIMITE_COMMANDES_PAR_MINUTE)
        attente = await _debit(r, "commandes", limite)
        if attente is not None:
            return erreur(429, "Rate limit exceeded", "too_many_requests", **{"Retry-After": str(attente)})
        try:
            nombre = max(1, min(int(params.get("count") or COMMANDES_PAR_PAGE), 1000))
        except ValueError:
            return erreur(422, "Validation failed", "unprocessable_entity", [("/count", "is not a number")])
        lignes = list(reversed(await db_client.lister_commandes_de_demo(r["id"], private_ref=params.get("private_ref"), limite=1000)))  # la plus ancienne d'abord (réponse 23)
        if params.get("status"):
            lignes = [x for x in lignes if x["statut"] == params["status"]]
        apres = params.get("after")
        if apres:
            ids = [x["ref"] for x in lignes]
            lignes = lignes[ids.index(apres) + 1:] if apres in ids else []
        page = lignes[:nombre]
        entetes = {"X-Cursor-Next": page[-1]["ref"]} if len(lignes) > nombre and page else {}
        return Reponse(200, [x["corps"] for x in page], entetes)

    async def _changer_la_commande(self, r: dict[str, Any], identifiant: str, corps: Any) -> Reponse:
        ligne = await db_client.lire_commande_de_demo(r["id"], identifiant)
        if ligne is None:
            return erreur(404, "Order does not exist", "not_found")
        if not isinstance(corps, dict):
            return erreur(422, "Validation failed", "unprocessable_entity", [("/", "must be an object")])
        if "status" in corps and corps["status"] not in STATUTS:
            return erreur(422, "Validation failed", "unprocessable_entity", [("/status", f"is not a valid status ('{corps['status']}' given)")])
        nouveau = {**ligne["corps"], **{k: v for k, v in corps.items() if k in ("status", "confirmed_time", "expected_time", "seller_notes")}}
        await db_client.modifier_commande_de_demo(r["id"], identifiant, nouveau["status"], nouveau, horloge(r["organization_id"]).maintenant())
        return Reponse(200, nouveau)


moteur = Moteur()
