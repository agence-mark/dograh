"""[.mark] Module Restauration, lot 3 : les traducteurs HubRise <-> format commun (fonctions PURES, aucun appel réseau).

Écrits d'après les réponses enregistrées le 15/11 (``hubrise-reponses/``, numéro cité) et le format commun du contrat
(carte ``mark-carte-commune/1``, commande du contrat § 2). Ce que HubRise ne représente pas (allergènes, TVA par mode,
ingrédients, étoile, rang, imbrication des choix, disponibilités) voyage dans une étiquette ``mark:`` portée par chaque objet,
pour que la carte fasse l'aller et retour SANS PERTE ; ce que la caisse change à la main (nom, prix, description, rattachements)
prime sur l'étiquette : la caisse est maître de ce qu'elle porte.

Un produit ou une option SANS code de caisse n'est jamais écrit (il est rendu dans ``signales``) : il ne serait pas vendable.
Les imbriqués sont aplatis à l'envoi d'une commande par ``adaptation.adapter_commande`` (HubRise n'a pas d'imbrication) ; ici
la carte garde le lien dans l'étiquette.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

PREFIXE_ETIQUETTE = "mark:"
FORMAT_CARTE = "mark-carte-commune/1"
MONNAIE = "EUR"

SERVICE_VERS_HUBRISE = {"emporter": "collection", "livraison": "delivery", "sur_place": "eat_in"}
SERVICE_DE_HUBRISE = {v: k for k, v in SERVICE_VERS_HUBRISE.items()}
# Statuts HubRise (réponses 21, 22 et documentation) -> étapes de la liste fermée de la fiche. Ce qui n'est pas connu devient
# ``inconnu`` (valeur permise du contrat § 3), jamais un vide silencieux.
ETAPE_DE_STATUT = {
    "received": "recue", "accepted": "acceptee", "in_preparation": "en_preparation",
    "awaiting_shipment": "prete", "awaiting_collection": "prete", "in_delivery": "prete",
    "completed": "terminee", "rejected": "refusee", "cancelled": "annulee",
}
EFFET_VERS_HUBRISE = {"inchange": "unchanged", "pourcentage": "percentage_off", "remise": "price_off"}
EFFET_DE_HUBRISE = {v: k for k, v in EFFET_VERS_HUBRISE.items()}
LISTE_DES_RETRAITS = "Retraits"
LIBELLE_MOYEN = {"carte": "Carte bancaire", "especes": "Espèces", "titre_restaurant": "Titre-restaurant", "cheque": "Chèque", "carte_livraison": "Carte bancaire à la livraison"}

_MONTANT = re.compile(r"^(-?\d+(?:\.\d{1,2})?) ([A-Z]{3})$")


class TraductionImpossible(ValueError):
    """Une valeur que le format commun ne peut pas porter (montant mal écrit, quantité décimale…)."""


def euros(centimes: int) -> str:
    """``1250`` -> ``"12.50 EUR"`` (la seule écriture que HubRise accepte : 16)."""
    if isinstance(centimes, bool) or not isinstance(centimes, int):
        raise TraductionImpossible(f"Un montant s'écrit en centimes entiers : {centimes!r}")
    signe = "-" if centimes < 0 else ""
    centimes = abs(centimes)
    return f"{signe}{centimes // 100}.{centimes % 100:02d} {MONNAIE}"


def centimes(montant: str | None) -> int:
    """``"12.50 EUR"`` -> ``1250``. Une autre monnaie ou une écriture à virgule est refusée."""
    trouve = _MONTANT.match(montant or "")
    if not trouve or trouve.group(2) != MONNAIE:
        raise TraductionImpossible(f"Montant mal écrit : {montant!r}")
    return int((Decimal(trouve.group(1)) * 100).to_integral_value())


def _quantite(valeur: Any) -> int:
    try:
        d = Decimal(str(valeur))
    except InvalidOperation:
        raise TraductionImpossible(f"Quantité illisible : {valeur!r}") from None
    if d != d.to_integral_value() or d < 0:
        raise TraductionImpossible(f"Quantité non entière : {valeur!r}")
    return int(d)


# --------------------------------------------------------------------------- étiquettes ``mark:``


def _etiquette(objet: dict) -> str:
    return PREFIXE_ETIQUETTE + json.dumps(objet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _lire_etiquette(tags: list | None) -> dict:
    for t in tags or []:
        if isinstance(t, str) and t.startswith(PREFIXE_ETIQUETTE):
            try:
                valeur = json.loads(t[len(PREFIXE_ETIQUETTE):])
            except ValueError:
                return {}
            return valeur if isinstance(valeur, dict) else {}
    return {}


# --------------------------------------------------------------------------- correspondance des codes


@dataclass
class Correspondance:
    """La table de correspondance des codes de la prise : notre ``code_caisse`` <-> l'identifiant propre à HubRise.
    Un code de caisse est le ``ref`` HubRise d'un sku ou d'une option ; la table dit aussi lequel des deux."""

    genre_de_code: dict[str, str] = field(default_factory=dict)  # code -> "declinaison" | "option"
    id_de_code: dict[str, str] = field(default_factory=dict)  # code -> identifiant HubRise (carte relue)
    code_de_id: dict[str, str] = field(default_factory=dict)

    def genre(self, code: str) -> str:
        if code not in self.genre_de_code:
            raise KeyError(f"Code de caisse inconnu de la carte de la prise : {code!r}")
        return self.genre_de_code[code]


def correspondance_de_la_carte(catalogue: dict) -> Correspondance:
    """Depuis la carte lue (réponse 04)."""
    t = Correspondance()
    donnees = catalogue.get("data", catalogue)
    for p in donnees.get("products", []):
        for s in p.get("skus", []):
            t.genre_de_code[s["ref"]] = "declinaison"
            if s.get("id"):
                t.id_de_code[s["ref"]], t.code_de_id[s["id"]] = s["id"], s["ref"]
    for liste in donnees.get("option_lists", []):
        for o in liste.get("options", []):
            t.genre_de_code[o["ref"]] = "option"
            if o.get("id"):
                t.id_de_code[o["ref"]], t.code_de_id[o["id"]] = o["id"], o["ref"]
    return t


# --------------------------------------------------------------------------- carte : commun -> HubRise (écriture par refs)


@dataclass
class CarteEcrite:
    donnees: dict
    signales: list[str]  # ce qui n'a pas de code de caisse : jamais envoyé


def _codes_de_la_categorie(carte: dict, categorie: str) -> list[str]:
    enfants = {categorie} | {c["id"] for c in carte.get("categories", []) if c.get("parent_id") == categorie}
    return [d["code_caisse"] for p in carte.get("produits", []) if p.get("categorie_id") in enfants for d in p.get("declinaisons", []) if d.get("code_caisse")]


def carte_vers_hubrise(carte: dict) -> CarteEcrite:
    """La carte du format commun, au format d'ÉCRITURE de HubRise (``PUT /catalogs/:id``, réponse 03 : tout par ``ref``)."""
    if carte.get("format") != FORMAT_CARTE:
        raise TraductionImpossible(f"Format attendu : {FORMAT_CARTE}")
    signales: list[str] = []
    # Documentation HubRise (catalogs, lue le 15/11) : à l'écriture le parent se dit ``parent_ref`` (le ``ref`` du parent) ; à la lecture, ``parent_id``.
    categories = [
        {"ref": c["id"], "name": c["nom"], **({"parent_ref": c["parent_id"]} if c.get("parent_id") else {}),
         "tags": [_etiquette({k: c.get(k) for k in ("parent_id", "ordre", "portee")})]}
        for c in carte.get("categories", [])
    ]
    produits = []
    for p in carte.get("produits", []):
        skus = []
        for d in p.get("declinaisons", []):
            if not d.get("code_caisse"):
                signales.append(d["id"])
                continue
            skus.append(
                {"ref": d["code_caisse"], "name": d["nom"], "price": euros(d["prix"]), "option_list_refs": list(p.get("groupes") or []),
                 "tags": [_etiquette({k: v for k, v in d.items() if k not in ("nom", "prix", "code_caisse")} | {"id": d["id"]})]}
            )
        if not skus:
            continue
        reste = {k: v for k, v in p.items() if k not in ("nom", "description", "declinaisons", "categorie_id")}
        produit = {"ref": p["id"], "category_ref": p.get("categorie_id"), "name": p["nom"], "skus": skus, "tags": [_etiquette(reste)]}
        if p.get("description"):
            produit["description"] = p["description"]
        produits.append(produit)
    listes = []
    for g in carte.get("groupes", []):
        options = []
        for o in g.get("options", []):
            if not o.get("code_caisse"):
                signales.append(o["id"])
                continue
            options.append(
                {"ref": o["code_caisse"], "name": o["nom"], "price": euros(o.get("prix", 0)),
                 "tags": [_etiquette({k: v for k, v in o.items() if k not in ("nom", "prix", "code_caisse")})]}
            )
        reste = {k: v for k, v in g.items() if k not in ("nom", "options", "min", "max")}
        listes.append({"ref": g["id"], "name": g["nom"], "min_selections": g.get("min", 0), "max_selections": g.get("max"), "options": options, "tags": [_etiquette(reste)]})
    deals = []
    for f in carte.get("formules", []):
        lignes = []
        for ligne in f.get("lignes", []):
            codes = list(ligne.get("codes") or [])
            for categorie in ligne.get("categories") or []:
                codes += _codes_de_la_categorie(carte, categorie)
            lignes.append({"label": ligne["nom"], "skus": [{"ref": c} for c in dict.fromkeys(codes)], "pricing_effect": EFFET_VERS_HUBRISE.get(ligne.get("effet"), "unchanged")})
        deals.append({"ref": f["id"], "name": f["nom"], "lines": lignes, "tags": [_etiquette({k: v for k, v in f.items() if k != "nom"})]})
    return CarteEcrite(
        {"categories": categories, "products": produits, "option_lists": listes, "deals": deals}, signales
    )


# --------------------------------------------------------------------------- carte : HubRise (relue, par identifiants) -> commun


@dataclass
class CarteLue:
    carte: dict
    signales: list[str]  # ce que la caisse ne dit pas (prix de formule inconnu…)


def carte_de_hubrise(catalogue: dict) -> CarteLue:
    """La carte relue (réponse 04 : ``GET /catalogs/:id``) au format commun. L'étiquette ``mark:`` rend ce que HubRise ne
    porte pas ; le nom, le prix, la description et les rattachements de la caisse prévalent."""
    donnees = catalogue.get("data", catalogue)
    signales: list[str] = []
    # Relue, la carte relie par identifiants HubRise ; écrite (ou en essai), par ``ref`` : les deux se lisent.
    ref_de_categorie = {c.get("id", c["ref"]): c["ref"] for c in donnees.get("categories", [])} | {c["ref"]: c["ref"] for c in donnees.get("categories", [])}
    ref_de_liste = {x.get("id", x["ref"]): x["ref"] for x in donnees.get("option_lists", [])} | {x["ref"]: x["ref"] for x in donnees.get("option_lists", [])}
    categories = []
    for i, c in enumerate(donnees.get("categories", [])):
        e = _lire_etiquette(c.get("tags"))
        parent = ref_de_categorie.get(c.get("parent_id")) if c.get("parent_id") else e.get("parent_id")
        categories.append({"id": c["ref"], "nom": c["name"], "parent_id": parent, "ordre": e.get("ordre", i), "portee": e.get("portee") or "etablissement"})
    produits = []
    for p in donnees.get("products", []):
        e = _lire_etiquette(p.get("tags"))
        natifs: list[str] = []
        declinaisons = []
        for s in p.get("skus", []):
            es = _lire_etiquette(s.get("tags"))
            for liste_id in s.get("option_list_ids") or s.get("option_list_refs") or []:
                if ref_de_liste.get(liste_id) and ref_de_liste[liste_id] not in natifs:
                    natifs.append(ref_de_liste[liste_id])
            d = {"id": es.get("id") or s["ref"], "nom": s["name"], "code_caisse": s["ref"], "prix": centimes(s["price"]), "disponibilite": es.get("disponibilite")}
            declinaisons.append(d | {k: v for k, v in es.items() if k not in d})
        groupes = list(e["groupes"]) if set(e.get("groupes") or []) == set(natifs) and "groupes" in e else natifs
        produit = {k: v for k, v in e.items() if k not in ("groupes",)}
        produit.update(
            {
                "id": e.get("id") or p["ref"], "nom": p["name"], "description": p.get("description"),
                "categorie_id": ref_de_categorie.get(p.get("category_id") or p.get("category_ref")), "declinaisons": declinaisons, "groupes": groupes,
            }
        )
        produit.setdefault("ingredients", [])
        produit.setdefault("allergenes", None)  # inconnu, jamais « aucun »
        produit.setdefault("tva_par_mode", {})
        produit.setdefault("etoile", False)
        produits.append(produit)
    groupes_communs = []
    for liste in donnees.get("option_lists", []):
        e = _lire_etiquette(liste.get("tags"))
        options = []
        for o in liste.get("options", []):
            eo = _lire_etiquette(o.get("tags"))
            option = {
                "id": eo.get("id") or f"{liste['ref']}-{o['ref']}", "groupe_id": liste["ref"], "nom": o["name"], "code_caisse": o["ref"],
                "prix": centimes(o["price"]), "par_defaut": bool(eo["par_defaut"] if "par_defaut" in eo else o.get("default", False)), "retirable": bool(eo.get("retirable", False)),
            }
            options.append(option | {k: v for k, v in eo.items() if k not in option})
        maximum = liste.get("max_selections")
        groupe = {k: v for k, v in e.items()}
        groupe.update(
            {"id": liste["ref"], "nom": liste["name"], "min": liste.get("min_selections") or 0, "max": maximum if maximum is not None else max(len(options), 1), "options": options}
        )
        groupe.setdefault("max_par_option", 1)
        groupe.setdefault("defaut", [])
        groupe.setdefault("parent_option_id", None)
        groupe.setdefault("role", "choix")
        groupes_communs.append(groupe)
    formules = []
    for d in donnees.get("deals", []):
        e = _lire_etiquette(d.get("tags"))
        if "prix" not in e:
            signales.append(f"formule {d['ref']} : prix inconnu de la caisse")
        lignes = e.get("lignes")
        if lignes is None:
            lignes = [
                {"nom": ligne.get("label") or "", "codes": [s["ref"] for s in ligne.get("skus", [])], "effet": EFFET_DE_HUBRISE.get(ligne.get("pricing_effect"), "inchange")}
                for ligne in d.get("lines", [])
            ]
        formule = {k: v for k, v in e.items()}
        formule.update({"id": e.get("id") or d["ref"], "nom": d["name"], "code_caisse": e.get("code_caisse") or d["ref"], "prix": e.get("prix", 0), "lignes": lignes})
        formule.setdefault("categorie_id", ref_de_categorie.get(d.get("category_id")))
        formules.append(formule)
    return CarteLue(
        {"format": FORMAT_CARTE, "categories": categories, "produits": produits, "groupes": groupes_communs, "formules": formules}, signales
    )


# --------------------------------------------------------------------------- commande : commun -> HubRise


def prix_des_choix(choix: list[dict] | None) -> int:
    """Ce que les choix d'une ligne ajoutent à UNE unité (centimes), sous-choix compris ; un choix sans prix (ligne ancienne) ne compte pour rien."""
    return sum((int(c.get("prix") or 0) + prix_des_choix(c.get("choix"))) * int(c.get("quantite", 1)) for c in choix or [])


def _option_de_la_commande(c: dict) -> dict[str, Any]:
    try:
        option = {"option_list_name": c["groupe"], "ref": c["option_code"], "name": c["nom"], "price": euros(c["prix"])}
    except KeyError as erreur:
        raise TraductionImpossible(f"Choix enregistré sans {erreur.args[0]} : le nom, le prix et la liste sont ceux de la commande") from erreur
    return option | ({"quantity": c["quantite"]} if c.get("quantite", 1) != 1 else {})


def _options_de_la_commande(c: dict) -> list[dict[str, Any]]:
    """Un choix et ses sous-choix, à plat (HubRise porte une liste d'options : un choix dans un choix est une option de plus, à son prix)."""
    return [_option_de_la_commande(c), *(o for sous in c.get("choix") or [] for o in _options_de_la_commande(sous))]


def commande_vers_hubrise(commande: dict, *, formules: dict[str, dict] | None = None) -> dict:
    """La commande du format commun (déjà ``adapter_commande`` pour HubRise : sans imbrication) au corps de
    ``POST /location/orders`` (réponses 12 à 14). ``private_ref`` = NOTRE numéro : c'est lui qui sert l'anti-doublon (20).
    Les montants sont écrits ``12.50 EUR`` (16). HubRise recalcule le total (13) : on n'envoie pas le nôtre."""
    mode = commande["mode"]
    if mode not in SERVICE_VERS_HUBRISE:
        raise TraductionImpossible(f"Mode inconnu : {mode!r}")
    client = commande.get("client") or {}
    corps: dict[str, Any] = {"status": "new", "private_ref": str(commande["numero"]), "service_type": SERVICE_VERS_HUBRISE[mode]}
    contact = {"phone": client.get("telephone"), "first_name": client.get("prenom")}
    adresse = commande.get("adresse") or {}
    if not isinstance(adresse, dict):
        # Lot 1 (S03) : l'adresse est toujours une ``Adresse`` structurée (voie, code postal, commune) ; un texte n'est jamais deviné.
        raise TraductionImpossible("Adresse non structurée : voie, code postal et commune attendus")
    if adresse:
        contact |= {"address_1": adresse.get("voie") or adresse.get("ligne"), "postal_code": adresse.get("code_postal"), "city": adresse.get("commune")}
    corps["customer"] = {k: v for k, v in contact.items() if v}
    if commande.get("note"):
        corps["customer_notes"] = commande["note"]
    heure = commande.get("heure_voulue")
    if isinstance(heure, datetime):
        corps["expected_time"] = heure.isoformat()
    deals: dict[str, dict] = {}
    cles_de_formule: dict[str, str] = {}
    articles = []
    for ligne in commande.get("lignes", []):
        # D50 : ``prix_unitaire`` est tout compris (produit plus suppléments) ; la caisse reçoit le produit seul et chaque option à son prix, et recalcule le même total.
        article: dict[str, Any] = {
            "product_name": ligne["nom"], "sku_ref": ligne["code_caisse"], "price": euros(ligne["prix_unitaire"] - prix_des_choix(ligne.get("choix"))),
            "quantity": str(ligne.get("quantite", 1)),
        }
        if ligne.get("note"):
            article["customer_notes"] = ligne["note"]
        # Documentation HubRise (orders) : ``option_list_name`` et ``name`` sont obligatoires ; ``ref`` est facultatif, un retrait n'en a donc pas besoin.
        # Le nom, le prix et la liste sont ceux que la commande a enregistrés (une ligne qui ne les porte pas est une erreur, jamais un code à 0 €).
        options = [o for c in ligne.get("choix") or [] for o in _options_de_la_commande(c)]
        options += [{"option_list_name": LISTE_DES_RETRAITS, "name": r, "price": euros(0), "removed": True} for r in ligne.get("retires") or []]
        if options:
            article["options"] = options
        if ligne.get("formule_id"):
            fid = ligne["formule_id"]
            cle = cles_de_formule.setdefault(fid, str(len(cles_de_formule)))
            deals[cle] = {"name": (formules or {}).get(fid, {}).get("nom", fid), "ref": fid}
            article["deal_line"] = {"deal_key": cle, "label": ligne.get("etiquette_formule") or ligne["nom"], "pricing_effect": "unchanged"}
        articles.append(article)
    corps["items"] = articles
    if deals:
        corps["deals"] = deals
    remises = [
        {"name": r["nom"], "price_off": euros(r["montant"])} | ({"ref": r["ref_caisse"]} if r.get("ref_caisse") else {}) for r in commande.get("remises") or []
    ]
    if remises:
        corps["discounts"] = remises
    if commande.get("frais"):
        corps["charges"] = [{"name": "Livraison", "price": euros(commande["frais"])}]
    moyens = (commande.get("paiement") or {}).get("moyens") or []
    if moyens:
        corps["payments"] = [{"name": LIBELLE_MOYEN.get(m["moyen"], m["moyen"]), "ref": m["moyen"], "amount": euros(m["montant"])} for m in moyens]
    return corps


# --------------------------------------------------------------------------- commande, état, inventaire : HubRise -> commun


def etape_de_statut(statut: str | None) -> str:
    return ETAPE_DE_STATUT.get(statut or "", "inconnu")


def commande_de_hubrise(ordre: dict) -> dict:
    """Une commande lue chez HubRise (réponses 12, 21, 22, 23) au format commun, pour ce que la prise dit : étape, heure, total,
    lignes. Sans ``private_ref`` la commande vient de la caisse (``cree_par = caisse``)."""
    lignes = []
    for a in ordre.get("items", []):
        if a.get("deleted"):
            continue
        options = a.get("options") or []
        lignes.append(
            {
                "code_caisse": a.get("sku_ref"), "nom": a.get("product_name"), "prix_unitaire": centimes(a["price"]), "quantite": _quantite(a.get("quantity", 1)),
                "note": a.get("customer_notes"),
                # Lot 26 (M10) : ce que les options payantes ajoutent à UNE unité (centimes), pour chiffrer une commande créée dans la caisse.
                "supplements": sum(centimes(o["price"]) * _quantite(o.get("quantity", 1)) for o in options if not o.get("removed") and o.get("price")),
                "choix": [{"option_code": o.get("ref"), "quantite": _quantite(o.get("quantity", 1)), "nom": o.get("name")} for o in options if not o.get("removed")],
                "retires": [o["name"] for o in options if o.get("removed")],
            }
        )
    heure = ordre.get("confirmed_time") or ordre.get("expected_time")
    return {
        "numero": ordre.get("private_ref"), "ref_fournisseur": ordre.get("id"), "etape": etape_de_statut(ordre.get("status")),
        "mode": SERVICE_DE_HUBRISE.get(ordre.get("service_type"), None),
        "heure_annoncee": datetime.fromisoformat(heure) if heure else None,
        "cree_le": datetime.fromisoformat(ordre["created_at"]) if ordre.get("created_at") else None,
        # L'heure que la CAISSE a confirmée (temps de préparation allongé…) : la seule qui dit « la caisse a changé l'heure » ; ``expected_time`` est la nôtre.
        "heure_confirmee": datetime.fromisoformat(ordre["confirmed_time"]) if ordre.get("confirmed_time") else None,
        "total": centimes(ordre["total"]) if ordre.get("total") else None,
        "lignes": lignes, "cree_par": "agent" if ordre.get("private_ref") else "caisse",
    }


def etat_de_hubrise(point_de_vente: dict) -> dict:
    """``order_acceptance`` du point de vente (réponses 01, 07, 08) -> ``EtatCaisse``. ``busy`` = débordé (+ minutes) ;
    tout autre mode que ``normal`` et ``busy`` est lu comme une PAUSE (le plus prudent) ; ``resume_at`` = la reprise."""
    reception = point_de_vente.get("order_acceptance") or {}
    mode = reception.get("mode", "normal")
    etat = {"mode": "normal" if mode == "normal" else "deborde" if mode == "busy" else "pause", "minutes_en_plus": 0, "reprise": None}
    if etat["mode"] == "deborde":
        etat["minutes_en_plus"] = int(reception.get("extra_preparation_time") or 0)
    if reception.get("resume_at"):
        etat["reprise"] = datetime.fromisoformat(reception["resume_at"])
    etat["temps_preparation"] = point_de_vente.get("preparation_time")
    etat["horaires"] = point_de_vente.get("opening_hours")  # ``None`` : la caisse n'en a pas posé (ne signale rien)
    return etat


def etat_vers_hubrise(etat: dict) -> dict:
    """``EtatCaisse`` -> corps de ``PATCH /location`` (réponses 07 et 08)."""
    mode = etat["mode"]
    if mode == "normal":
        return {"order_acceptance": {"mode": "normal"}}
    if mode == "deborde":
        corps = {"mode": "busy", "extra_preparation_time": int(etat.get("minutes_en_plus") or 0)}
    elif mode == "pause":
        corps = {"mode": "paused"}
    else:
        raise TraductionImpossible(f"Mode inconnu : {mode!r}")
    if etat.get("reprise"):
        corps["resume_at"] = etat["reprise"].isoformat()
    return {"order_acceptance": corps}


def ruptures_de_hubrise(inventaire: list[dict]) -> list[dict]:
    """L'inventaire lu (réponses 05, 06) -> ruptures : un stock à zéro est une rupture ; ``expires_at`` en est la fin."""
    sorties = []
    for ligne in inventaire:
        code = ligne.get("sku_ref") or ligne.get("option_ref")
        if not code:
            continue
        stock = ligne.get("stock")
        sorties.append(
            {
                "code_caisse": code, "genre": "declinaison" if ligne.get("sku_ref") else "option",
                "disponible": stock is None or Decimal(str(stock)) > 0, "stock": None if stock is None else int(Decimal(str(stock))),
                "fin": datetime.fromisoformat(ligne["expires_at"]) if ligne.get("expires_at") else None,
            }
        )
    return sorties


def rupture_vers_hubrise(code_caisse: str, genre: str, disponible: bool, fin: datetime | None = None) -> dict:
    """Une rupture posée par nous -> une ligne de ``PATCH /location/inventory`` (réponse 05). ``genre`` : ``declinaison`` ou ``option``.
    Une reprise (``disponible``) met ``stock`` à ``null``, ce qui retire la limite : seul ``PATCH`` le comprend (documentation inventories, lue le
    15/11 : ``PUT`` ignore les entrées à ``null`` et remet à zéro celles qu'il ne cite pas, JAMAIS ``PUT`` pour une rupture isolée)."""
    cle = {"declinaison": "sku_ref", "option": "option_ref"}[genre]
    ligne: dict[str, Any] = {cle: code_caisse, "stock": None if disponible else "0"}
    if fin is not None and not disponible:
        ligne["expires_at"] = fin.isoformat()
    return ligne
