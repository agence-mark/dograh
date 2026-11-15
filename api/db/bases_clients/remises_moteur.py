"""[.mark] Mécanisme commun : le MOTEUR DE REMISES (module Restauration, lot 7, E-52).

Un panier d'unités (une unité = un exemplaire d'un article, au prix facturé), une règle (déclencheur, effet, périmètre), un
contexte : le moteur rend l'effet EXACT en centimes entiers, jamais un flottant, jamais au-delà de ce qui est dû. Pur : aucune
base, aucune lecture de l'heure (le moment est fourni par l'appelant). Aucun mot du métier : les noms des règles du module
(« deuxième à moitié prix », « passage en formule »…) vivent dans ``restauration_remise.py``, qui les traduit vers les SEPT
familles de règles d'ici.

Les familles (champ ``famille`` d'une règle) :

- ``pourcentage`` / ``montant`` : sur le périmètre (ou tout le panier), après un minimum éventuel ;
- ``lot_offert`` : ``X`` achetés, ``Y`` offerts, dans le même périmètre (les moins chers du groupe) ou dans un autre ;
- ``rang_reduit`` : un exemplaire sur ``rang`` est réduit d'un pourcentage (le moins cher du groupe) ;
- ``prix_fixe`` : les exemplaires du périmètre sont facturés à ce prix (la réduction est l'écart, jamais négative) ;
- ``ecart_de_rang`` : un exemplaire est facturé au prix d'un autre article (monter d'un cran pour le prix du cran du dessous) ;
- ``composition`` : un ensemble d'exemplaires (une case par périmètre) facturé à un prix d'ensemble ;
- ``tous_les`` : une règle que le client reconnu atteint à sa Nième achat.

Un effet peut AJOUTER un article offert (``ajout``) : il part alors à son prix, avec une remise du même montant (plan § 3.8).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

FAMILLES = frozenset({"pourcentage", "montant", "lot_offert", "rang_reduit", "prix_fixe", "ecart_de_rang", "composition", "tous_les"})


@dataclass(frozen=True)
class Unite:
    """Un exemplaire d'un article du panier : ``prix`` est le prix facturé de l'unité (choix et suppléments compris)."""

    ligne: int
    code: str
    prix: int
    produit: str | None = None
    categorie: str | None = None


@dataclass(frozen=True)
class Contexte:
    mode: str | None
    sous_total: int
    rang_du_client: int | None = None            # la Nième achat de ce client (None : client inconnu)
    prix_par_code: Mapping[str, int] = field(default_factory=dict)   # le prix du catalogue d'un article, pour un écart de rang
    maintenant: datetime | None = None


@dataclass(frozen=True)
class Effet:
    montant: int                                 # centimes, > 0
    ajout: tuple[tuple[str, int], ...] = ()       # (code, quantité) d'articles offerts à ajouter à l'achat
    unites: tuple[int, ...] = ()                  # les rangs d'unités concernées (pour dire de quoi il s'agit)


def _entier_positif(valeur: Any) -> int | None:
    return valeur if isinstance(valeur, int) and not isinstance(valeur, bool) and valeur > 0 else None


def _pourcentage(valeur: Any) -> float | None:
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)) or not 0 < valeur <= 100:
        return None
    return float(valeur)


def part_en_centimes(base: int, pourcentage: float) -> int:
    """``pourcentage`` de ``base`` au centime le plus proche (la moitié vers le haut), sans flottant : jamais plus que ``base``."""
    millièmes = round(pourcentage * 100)           # 12,5 % → 1250 (dix-millièmes)
    return min(base, (base * millièmes + 5000) // 10000)


def dans_le_perimetre(unite: Unite, perimetre: Mapping[str, Any] | None) -> bool:
    """Vide : tout. Sinon l'unité doit être dans UNE des listes données (codes, produits, catégories)."""
    if not perimetre:
        return True
    listes = [("codes", unite.code), ("produits", unite.produit), ("categories", unite.categorie)]
    donnees = [(cle, valeur) for cle, valeur in listes if perimetre.get(cle)]
    if not donnees:
        return True
    return any(valeur is not None and valeur in perimetre[cle] for cle, valeur in donnees)


def _du_perimetre(unites: Sequence[Unite], perimetre: Mapping[str, Any] | None) -> list[Unite]:
    return [u for u in unites if dans_le_perimetre(u, perimetre)]


def _chers_d_abord(unites: Sequence[Unite]) -> list[Unite]:
    return sorted(unites, key=lambda u: (-u.prix, u.ligne, u.code))


def _plafond(regle: Mapping[str, Any]) -> int | None:
    limite = regle.get("limite") or {}
    return _entier_positif(limite.get("max_par_achat"))


def _effet_sur(base: int, effet: Mapping[str, Any]) -> int | None:
    if "pourcentage" in effet:
        pct = _pourcentage(effet["pourcentage"])
        return None if pct is None else part_en_centimes(base, pct)
    if "montant" in effet:
        m = _entier_positif(effet["montant"])
        return None if m is None else min(base, m)
    return None


def _article_offert(effet: Mapping[str, Any], ctx: Contexte) -> Effet | None:
    """« Un article offert » : il part à son prix du catalogue, avec une remise du même montant."""
    offert = effet.get("offert") or {}
    codes = offert.get("codes") or []
    if len(codes) != 1 or codes[0] not in ctx.prix_par_code:
        return None
    quantite = _entier_positif(offert.get("quantite")) or 1
    prix = ctx.prix_par_code[codes[0]]
    return Effet(prix * quantite, ((codes[0], quantite),)) if prix > 0 else None


def _simple(regle: Mapping[str, Any], unites: Sequence[Unite], ctx: Contexte) -> Effet | None:
    """Pourcentage ou montant ; ou, sur seuil et sur rang, un article offert."""
    declencheur, effet = regle.get("declencheur") or {}, regle.get("effet") or {}
    if "minimum" in declencheur and ctx.sous_total < (_entier_positif(declencheur["minimum"]) or 0):
        return None
    if regle.get("exige_un_minimum") and "minimum" not in declencheur:
        return None                                   # un seuil sans minimum ne s'applique à rien
    if "offert" in effet:
        return _article_offert(effet, ctx)
    cibles = _du_perimetre(unites, regle.get("perimetre"))
    base = ctx.sous_total if len(cibles) == len(unites) else sum(u.prix for u in cibles)
    montant = _effet_sur(base, effet)
    return Effet(montant, unites=tuple(u.ligne for u in cibles)) if montant else None


def _lot_offert(regle: Mapping[str, Any], unites: Sequence[Unite], ctx: Contexte) -> Effet | None:
    d, e = regle.get("declencheur") or {}, regle.get("effet") or {}
    x, y = _entier_positif(d.get("achetes")), _entier_positif(e.get("offerts"))
    if x is None or y is None:
        return None
    achetes = _chers_d_abord(_du_perimetre(unites, regle.get("perimetre")))
    plafond = _plafond(regle)
    if e.get("perimetre_offert"):
        n = len(achetes) // x
        utilises = {id(u) for u in achetes[: n * x]}
        pool = sorted((u for u in _du_perimetre(unites, e["perimetre_offert"]) if id(u) not in utilises), key=lambda u: (u.prix, u.ligne))
        n = min(n, len(pool) // y)
        if plafond:
            n = min(n, plafond)
        gratuits = pool[: n * y]
    else:
        n = len(achetes) // (x + y)
        if plafond:
            n = min(n, plafond)
        gratuits = [u for g in range(n) for u in achetes[g * (x + y) + x : (g + 1) * (x + y)]]
    montant = sum(u.prix for u in gratuits)
    return Effet(montant, unites=tuple(u.ligne for u in gratuits)) if montant > 0 else None


def _rang_reduit(regle: Mapping[str, Any], unites: Sequence[Unite], ctx: Contexte) -> Effet | None:
    rang = _entier_positif((regle.get("declencheur") or {}).get("rang")) or 2
    pct = _pourcentage((regle.get("effet") or {}).get("pourcentage"))
    if pct is None or rang < 2:
        return None
    rangees = _chers_d_abord(_du_perimetre(unites, regle.get("perimetre")))
    reduites = [rangees[i] for i in range(rang - 1, len(rangees), rang)]
    plafond = _plafond(regle)
    if plafond:
        reduites = reduites[:plafond]
    montant = sum(part_en_centimes(u.prix, pct) for u in reduites)
    return Effet(montant, unites=tuple(u.ligne for u in reduites)) if montant > 0 else None


def _prix_fixe(regle: Mapping[str, Any], unites: Sequence[Unite], ctx: Contexte) -> Effet | None:
    e = regle.get("effet") or {}
    cibles = _chers_d_abord(_du_perimetre(unites, regle.get("perimetre")))
    plafond = _plafond(regle)
    if plafond:
        cibles = cibles[:plafond]
    if "prix" in e:
        prix = e["prix"] if isinstance(e["prix"], int) and not isinstance(e["prix"], bool) and e["prix"] >= 0 else None
        if prix is None:
            return None
        montant = sum(max(0, u.prix - prix) for u in cibles)
    else:
        pct = _pourcentage(e.get("pourcentage"))
        if pct is None:
            return None
        montant = sum(part_en_centimes(u.prix, pct) for u in cibles)
    return Effet(montant, unites=tuple(u.ligne for u in cibles)) if montant > 0 else None


def _ecart_de_rang(regle: Mapping[str, Any], unites: Sequence[Unite], ctx: Contexte) -> Effet | None:
    base = (regle.get("effet") or {}).get("prix_de")
    prix_de_base = ctx.prix_par_code.get(base) if isinstance(base, str) else None
    if prix_de_base is None:
        return None
    cibles = _chers_d_abord(_du_perimetre(unites, regle.get("perimetre")))
    plafond = _plafond(regle)
    if plafond:
        cibles = cibles[:plafond]
    montant = sum(max(0, u.prix - prix_de_base) for u in cibles)
    return Effet(montant, unites=tuple(u.ligne for u in cibles)) if montant > 0 else None


def _composition(regle: Mapping[str, Any], unites: Sequence[Unite], ctx: Contexte) -> Effet | None:
    cases = (regle.get("declencheur") or {}).get("composition")
    prix = (regle.get("effet") or {}).get("prix")
    if not isinstance(cases, list) or not cases or not isinstance(prix, int) or isinstance(prix, bool) or prix < 0:
        return None
    restantes = list(unites)
    total, prises = 0, []
    plafond = _plafond(regle) or 99
    for _ in range(plafond):
        ensemble: list[Unite] = []
        reste = list(restantes)
        for case in cases:
            quantite = _entier_positif(case.get("quantite")) or 1
            candidates = _chers_d_abord(_du_perimetre(reste, case.get("perimetre")))
            if len(candidates) < quantite:
                ensemble = []
                break
            choisies = candidates[:quantite]
            ensemble.extend(choisies)
            reste = [u for u in reste if all(u is not c for c in choisies)]
        if not ensemble:
            break
        ecart = sum(u.prix for u in ensemble) - prix
        if ecart <= 0:
            break                                      # l'ensemble ne coûte pas plus que son prix : aucune remise
        total += ecart
        prises.extend(u.ligne for u in ensemble)
        restantes = reste
    return Effet(total, unites=tuple(prises)) if total > 0 else None


def _tous_les(regle: Mapping[str, Any], unites: Sequence[Unite], ctx: Contexte) -> Effet | None:
    n = _entier_positif((regle.get("declencheur") or {}).get("tous_les"))
    if n is None or ctx.rang_du_client is None or ctx.rang_du_client % n != 0:
        return None
    effet = regle.get("effet") or {}
    if "offert" in effet:
        return _article_offert(effet, ctx)
    montant = _effet_sur(ctx.sous_total, effet)
    return Effet(montant) if montant else None


_FAMILLES = {
    "pourcentage": _simple, "montant": _simple, "lot_offert": _lot_offert, "rang_reduit": _rang_reduit, "prix_fixe": _prix_fixe,
    "ecart_de_rang": _ecart_de_rang, "composition": _composition, "tous_les": _tous_les,
}


def evaluer(regle: Mapping[str, Any], unites: Sequence[Unite], ctx: Contexte) -> Effet | None:
    """L'effet exact de ``regle`` sur ``unites``, ou ``None`` : elle ne s'applique pas à ce panier. Jamais au-delà du sous-total."""
    famille = regle.get("famille")
    calcul = _FAMILLES.get(famille)
    if calcul is None or not unites:
        return None
    modes = (regle.get("perimetre") or {}).get("modes")
    if modes and ctx.mode not in modes:
        return None
    effet = calcul(regle, unites, ctx)
    if effet is None or effet.montant <= 0:
        return None
    plafond = ctx.sous_total + sum(prix for _, quantite in effet.ajout for prix in [ctx.prix_par_code.get(_, 0) * quantite])
    return Effet(min(effet.montant, plafond), effet.ajout, effet.unites)


def choisir_au_mieux(candidates: Sequence[Mapping[str, Any]], sous_total: int) -> list[Mapping[str, Any]]:
    """Parmi les remises qui s'appliquent (chacune avec ``cumul`` et ``montant``), l'ensemble le plus avantageux pour le client :
    la meilleure remise ``exclusive`` seule, OU toutes les ``cumulable`` ensemble, selon ce qui rend le plus. Le total des remises ne
    dépasse jamais ``sous_total`` (la dernière est rognée). Déterministe : à montant égal, l'ordre de la liste."""
    vivantes = [c for c in candidates if c.get("montant")]
    exclusives = [c for c in vivantes if c["cumul"] == "exclusive"]
    cumulables = [c for c in vivantes if c["cumul"] == "cumulable"]
    meilleure = max(exclusives, key=lambda c: c["montant"], default=None)
    jeu_a = [meilleure] if meilleure else []
    jeu_b = cumulables
    choisi = jeu_a if sum(c["montant"] for c in jeu_a) > sum(c["montant"] for c in jeu_b) else jeu_b
    reste, sortie = sous_total, []
    for c in choisi:
        montant = min(c["montant"], reste)
        if montant <= 0:
            break
        reste -= montant
        sortie.append({**c, "montant": montant})
    return sortie
