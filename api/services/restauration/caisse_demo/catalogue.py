"""[.mark] Module Restauration, lot 20 : la carte d'un restaurant de test, rendue comme HubRise la rend (``GET /catalogs/:id``, réponse 04).

La carte d'un restaurant de test est gardée au format COMMUN (``mark-carte-commune/1``, celui que l'écran édite). La caisse la rend au format de LECTURE de
HubRise : tout se relie par IDENTIFIANTS (``category_id``, ``option_list_ids``…), alors que l'écriture se relie par ``ref``. Les identifiants sont stables
(dérivés du ``ref``), jamais tirés au sort : relire deux fois rend la même carte. Les étiquettes ``mark:`` voyagent telles quelles (HubRise les garde).
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from api.services.restauration.prises import hubrise_traduction as ht


def identifiant(genre: str, ref: str) -> str:
    """Un identifiant à la façon de HubRise (7 signes), stable pour un ``ref`` donné."""
    return hashlib.sha1(f"{genre}:{ref}".encode()).hexdigest()[:7]


def carte_vide() -> dict[str, Any]:
    return {"format": ht.FORMAT_CARTE, "categories": [], "produits": [], "groupes": [], "formules": []}


def en_lecture(ecrit: dict[str, Any]) -> dict[str, Any]:
    """Le ``data`` de l'écriture (``carte_vers_hubrise``) au format de lecture : identifiants, rattachements par identifiant."""
    categories = ecrit.get("categories", [])
    id_cat = {c["ref"]: identifiant("cat", c["ref"]) for c in categories}
    listes = ecrit.get("option_lists", [])
    id_liste = {x["ref"]: identifiant("liste", x["ref"]) for x in listes}
    sortie_categories = [
        {"id": id_cat[c["ref"]], "ref": c["ref"], "parent_id": id_cat.get(c.get("parent_ref")), "name": c["name"], "description": None, "image_ids": [], "tags": c.get("tags", [])}
        for c in categories
    ]
    produits = []
    for p in ecrit.get("products", []):
        pid = identifiant("prod", p["ref"])
        skus = [
            {
                "id": identifiant("sku", s["ref"]), "ref": s["ref"], "name": s["name"], "product_id": pid, "restrictions": {}, "price": s["price"], "price_overrides": [],
                "option_list_ids": [id_liste[r] for r in s.get("option_list_refs", []) if r in id_liste], "tags": s.get("tags", []), "barcodes": [], "custom_fields": {},
                "weight": None, "volume": None, "nb_servings": None,
            }
            for s in p.get("skus", [])
        ]
        produits.append(
            {
                "id": pid, "ref": p["ref"], "category_id": id_cat.get(p.get("category_ref")), "name": p["name"], "description": p.get("description"), "tags": p.get("tags", []),
                "nutrition": None, "tax_rate": None, "image_ids": [], "skus": skus,
            }
        )
    listes_lues = []
    for x in listes:
        lid = id_liste[x["ref"]]
        options = [
            {
                "id": identifiant("option", f"{x['ref']}/{o['ref']}"), "ref": o["ref"], "option_list_id": lid, "name": o["name"], "restrictions": {}, "price": o["price"],
                "price_overrides": [], "default": False, "tags": o.get("tags", []), "nutrition": None, "weight": None, "volume": None,
            }
            for o in x.get("options", [])
        ]
        listes_lues.append(
            {
                "id": lid, "ref": x["ref"], "name": x["name"], "min_selections": x.get("min_selections", 0), "max_selections": x.get("max_selections"),
                "multiple_selection": (x.get("max_selections") or 2) > 1, "type": "multiple", "tags": x.get("tags", []), "options": options,
            }
        )
    deals = []
    for d in ecrit.get("deals", []):
        lignes = [
            {
                "id": identifiant("ligne", f"{d['ref']}/{i}"), "label": ligne.get("label"), "pricing_effect": ligne.get("pricing_effect", "unchanged"), "pricing_value": ligne.get("pricing_value"),
                "skus": [{"id": identifiant("sku", s["ref"]), "ref": s["ref"], "extra_charge": None} for s in ligne.get("skus", [])],
            }
            for i, ligne in enumerate(d.get("lines", []))
        ]
        deals.append(
            {
                "id": identifiant("deal", d["ref"]), "ref": d["ref"], "category_id": None, "name": d["name"], "description": None, "restrictions": {}, "coupon_codes": [],
                "tags": d.get("tags", []), "image_ids": [], "lines": lignes,
            }
        )
    return {"variants": [], "categories": sortie_categories, "products": produits, "option_lists": listes_lues, "deals": deals, "discounts": [], "charges": []}


def catalogue_de_lecture(
    *, catalogue_id: str, compte_id: str, nom: str, carte: dict[str, Any], remises: list[dict[str, Any]], cree_le: datetime, frais: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """La réponse complète de ``GET /catalogs/:id`` pour la carte commune d'un restaurant de test."""
    data = en_lecture(ht.carte_vers_hubrise(carte or carte_vide()).donnees)
    data["discounts"] = [
        {"id": identifiant("remise", r["ref"]), "ref": r["ref"], "name": r["nom"], "description": None, "restrictions": {}, "coupon_codes": [],
         "pricing_effect": ht.EFFET_VERS_HUBRISE.get(r.get("effet"), "unchanged"), "pricing_value": r.get("valeur"), "image_ids": []}
        for r in remises or []
    ]
    # Les frais : seulement ceux que la caisse a écrits elle-même dans son catalogue (M53 : zones de livraison et frais de zone sont au module, jamais ici).
    data["charges"] = [{"id": identifiant("frais", f["ref"]), "restrictions": {}, **f} for f in frais or [] if f.get("ref")]
    return {"id": catalogue_id, "account_id": compte_id, "location_id": None, "name": nom, "created_at": cree_le.strftime("%Y-%m-%dT%H:%M:%SZ"), "data": data}


def codes_vendables(carte: dict[str, Any]) -> dict[str, int]:
    """``code de caisse -> prix en centimes`` des déclinaisons de la carte (ce que la caisse sait vendre) ; les options en prix aussi."""
    codes: dict[str, int] = {}
    for p in (carte or {}).get("produits", []):
        for d in p.get("declinaisons", []):
            if d.get("code_caisse"):
                codes[d["code_caisse"]] = int(d["prix"])
    for g in (carte or {}).get("groupes", []):
        for o in g.get("options", []):
            if o.get("code_caisse"):
                codes[o["code_caisse"]] = int(o.get("prix", 0))
    return codes
