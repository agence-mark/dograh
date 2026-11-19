"""[.mark] Brique QTE1 : le produit au poids (inventaire, famille 7 ; 1 carte sur 44, A33 ; HubRise : quantité décimale).

Un produit vendu au poids (``unite`` ``g`` ou ``kg``) se commande par la sous-case ``ajouter[].poids`` (« trois cents grammes », « 300 g », « un demi-kilo ») avec ``quantite`` à 1.
Le CODE lit le poids (``lire_poids``, portée telle quelle du banc B12), l'arrondit au pas de la carte (``arrondi``, dit), chiffre au prix au kilo (``prix_par_unite``) et dit le
prix lui-même (D33). Un poids illisible, ou dit sans unité (« deux cents »), est refusé avec la raison : le code ne devine jamais. La ligne porte le poids d'UNE portion dans
``poids_g`` (D55) ; ``quantite`` reste un entier.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer

UNITES_AU_POIDS = ("g", "kg")
RAISON_PAS_AU_POIDS = "pas_vendu_au_poids"
RAISON_POIDS_A_DIRE = "poids_a_dire"
RAISON_POIDS_ILLISIBLE = "poids_illisible"

NOMBRES = {"zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
           "cent": 100, "cents": 100, "mille": 1000, "demi": 0.5,
           # au-delà du banc B12 (qui ne lisait que jusqu'à dix) : « deux cent cinquante grammes », « quatre-vingts grammes »
           "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16, "vingt": 20, "vingts": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60}


def _nettoye(texte: Any) -> str:
    """Le texte sans accent ni majuscule ; la virgule d'un nombre décimal est gardée (« 1,2 kg » vaut 1.2 kg)."""
    s = unicodedata.normalize("NFD", str(texte or "")).encode("ascii", "ignore").decode().lower().replace(",", ".")
    return re.sub(r"\s+", " ", re.sub(r"[-_'’!?]", " ", s)).strip()


def lire_poids(texte: Any) -> int | None:
    """« trois cents grammes », « 300 g », « un demi-kilo », « 1,2 kg » en grammes ; ``None`` si illisible (le code ne devine pas)."""
    s = _nettoye(texte)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|kilo|kilos|kilogrammes?|g|gr|grammes?)\b", s)
    if m:
        v = float(m.group(1))
        return int(round(v * 1000)) if m.group(2).startswith("k") else int(round(v))
    mots = s.split()
    unite = next((w for w in mots if w.startswith("kilo") or w.startswith("gramme") or w in ("g", "kg")), None)
    if not unite:
        return None
    courant = 0
    for i, w in enumerate(mots):
        if w == "quatre" and i + 1 < len(mots) and mots[i + 1] in ("vingt", "vingts"):
            courant += 60  # « quatre vingts » : 4 puis 20 deviennent 80 (4 + 20 + 60)
        elif w in ("cent", "cents"):
            courant = (courant or 1) * 100
        elif w == "demi":
            courant = 0.5
        elif w in NOMBRES:
            courant += NOMBRES[w]
        elif w.isdigit():
            courant += int(w)
    if not courant:
        return None
    return int(round(courant * 1000)) if unite.startswith("kilo") or unite == "kg" else int(round(courant))


def est_vendu_au_poids(produit: dict[str, Any]) -> bool:
    return produit.get("unite") in UNITES_AU_POIDS and bool(produit.get("prix_par_unite"))


def prix_de_la_portion(produit: dict[str, Any], grammes: int) -> int:
    """Le prix d'UNE portion de ``grammes`` en centimes : le prix au kilo, à la moitié vers le haut (entiers seulement, jamais un flottant)."""
    return (grammes * int(produit["prix_par_unite"]) + 500) // 1000


def poids_retenu(produit: dict[str, Any], grammes: int) -> int:
    """Le poids dit, arrondi au pas supérieur de la carte (``arrondi``) ; au gramme sans pas."""
    pas = produit.get("arrondi")
    return -(-grammes // int(pas)) * int(pas) if pas else grammes


def brique_qte1_chiffrer_au_poids(produit: dict[str, Any], poids_dit: Any) -> dict[str, Any]:
    """Le résultat d'un article posé au poids : ``{"grammes", "prix", "arrondi_a"}`` (``arrondi_a`` : le poids retenu quand il diffère du poids dit), ou un refus (``raison``)."""
    au_poids = est_vendu_au_poids(produit)
    dit = str(poids_dit or "").strip()
    if not au_poids:
        return {"raison": RAISON_PAS_AU_POIDS, "article": produit["nom"]} if dit else {}
    if not dit:
        return {"raison": RAISON_POIDS_A_DIRE, "article": produit["nom"]}
    grammes = lire_poids(dit)
    if not grammes:
        return {"raison": RAISON_POIDS_ILLISIBLE, "article": produit["nom"], "dit": dit}
    retenu = poids_retenu(produit, grammes)
    return {"grammes": retenu, "prix": prix_de_la_portion(produit, retenu), **({"arrondi_a": retenu} if retenu != grammes else {})}


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        p["unite"], p["prix_par_unite"], p["arrondi"] = "piece", None, None
    return carte


enregistrer(Brique(
    "QTE1", "quantite_et_unite", "C", (("produits", "unite"), ("produits", "prix_par_unite"), ("produits", "arrondi")), brique_qte1_chiffrer_au_poids,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/QTE1",
    phrase="un article au poids se pose avec la sous-case poids ; le code lit le poids, l'arrondit au pas de la carte et dit le prix",
))
