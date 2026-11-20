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

POIDS_MAXIMUM_G = 5000  # C5 : au-delà, le poids n'est jamais pris : « cent kilos de houmous » est une erreur de lecture, pas une commande (900 €) ; le modèle redemande
RAISON_AU_DESSUS_DU_MAXIMUM = "poids_au_dessus_du_maximum"
_UNITE_KILO = ("kg", "kilo", "kilos", "kilogramme", "kilogrammes")
_UNITE_GRAMME = ("g", "gr", "gramme", "grammes")
_MOTS_QUI_LIENT = frozenset({"de", "d", "du", "et", "un", "une"})


def _nettoye(texte: Any) -> str:
    """Le texte sans accent ni majuscule ; la virgule d'un nombre décimal est gardée (« 1,2 kg » vaut 1.2 kg)."""
    s = unicodedata.normalize("NFD", str(texte or "")).encode("ascii", "ignore").decode().lower().replace(",", ".")
    return re.sub(r"\s+", " ", re.sub(r"[-_'’!?]", " ", s)).strip()


def _fraction_ou_nombre(mots: list[str]) -> float | None:
    """Ce que disent les mots posés avant une unité : un nombre (``forme.lire_un_nombre``, la seule norme), « demi », « trois quarts », « un quart » ; ``None`` sinon."""
    from api.services.actions_communes.forme import lire_un_nombre

    mots = [m for m in mots if m not in ("de", "d", "du")]
    if mots and mots[-1] in ("demi", "demie", "demis"):
        return 0.5 if mots[:-1] in ([], ["un"], ["une"]) else None
    if mots and mots[-1] in ("quart", "quarts"):
        n = 1 if len(mots) == 1 else lire_un_nombre([m for m in mots[:-1] if m not in ("un", "une")] or ["un"])
        return None if n is None else n * 0.25
    if len(mots) == 1 and re.fullmatch(r"\d+(?:\.\d+)?", mots[0]):
        return float(mots[0])
    return float(n) if (n := lire_un_nombre(mots)) is not None else None


def lire_poids(texte: Any) -> int | None:
    """« trois cents grammes », « 300 g », « un demi-kilo », « 1,2 kg », « un kilo et demi », « un kilo deux cents », « trois quarts de kilo », « 2 x 300 g » en grammes ; ``None`` si illisible ou ambigu
    (le code ne devine pas). Les nombres en lettres passent par ``forme.lire_un_nombre`` (C5 : une seule norme de lecture, la même que « elle l'a dit » et que la garde des chiffres)."""
    s = _nettoye(texte)
    multiplicateur = 1
    m = re.match(r"(\d+)\s*(?:x|fois)\s*(?=\d)", s)
    if m:
        multiplicateur, s = int(m.group(1)), s[m.end():]
    mots = re.findall(r"\d+(?:\.\d+)?|[a-z]+", s)
    total, en_cours, i, vu = 0.0, [], 0, False
    while i < len(mots):
        w = mots[i]
        if w in _UNITE_KILO or w in _UNITE_GRAMME:
            valeur = _fraction_ou_nombre(en_cours)
            if valeur is None:
                return None
            en_cours = []
            if w in _UNITE_GRAMME:
                total += valeur
            else:
                total += valeur * 1000
                # « kilo + reste » : « un kilo et demi », « un kilo deux cents » ; un reste hors d'un nombre ou d'une fraction rend le poids illisible
                reste = [x for x in mots[i + 1:] if x != "et"]
                if reste:
                    plus = _fraction_ou_nombre(reste)
                    if plus is None:
                        return None
                    if reste[-1] in ("demi", "demie", "demis", "quart", "quarts"):
                        total += plus * 1000
                    elif 10 <= plus < 1000:
                        total += plus
                    else:
                        return None
                i = len(mots)
            vu = True
        elif w not in ("et",) or en_cours:
            en_cours.append(w)
        i += 1
    if not vu or en_cours or total <= 0 or total != int(total):
        return None
    return int(round(total * multiplicateur))


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
    if retenu > POIDS_MAXIMUM_G:
        return {"raison": RAISON_AU_DESSUS_DU_MAXIMUM, "article": produit["nom"], "maximum_g": POIDS_MAXIMUM_G}
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
