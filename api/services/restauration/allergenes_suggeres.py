"""[.mark] Module Restauration, lot 15 (D22) : les allergènes PROPOSÉS depuis les ingrédients, puis validés par une personne.

La table officielle (``allergenes_inco.json`` : l'annexe II du règlement (UE) n° 1169/2011, lue sur EUR-Lex) rapproche un ingrédient d'un des quatorze allergènes.
Une suggestion est toujours PROPOSÉE, jamais affirmée : l'agent ne lit que les allergènes validés. Jamais une liste vide proposée (« aucun allergène » ne se déduit
jamais d'une liste d'ingrédients) ; un ingrédient composé que la table ne reconnaît pas (« sauce maison ») est rendu « à préciser ».
Les codes sont ceux de ``signalements.LES_QUATORZE`` (la seule liste) ; ce fichier ne les recopie pas.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from api.services.restauration.signalements import LES_QUATORZE

_FICHIER = Path(__file__).with_name("allergenes_inco.json")


@lru_cache(maxsize=1)
def table_inco() -> dict[str, Any]:
    """La table officielle, lue une fois : ``{source, adresse, lu_le, allergenes: {code: {annexe, intitule, ingredients}}, composes_a_preciser}``."""
    return json.loads(_FICHIER.read_text(encoding="utf-8"))


def allergenes_de_hubrise(valeurs: list[str] | None) -> list[str] | None:
    """Lot 16 (D22) : les 26 valeurs de ``nutrition.allergens`` de HubRise ramenées aux 14 codes, dans l'ordre où la caisse les donne. ``None`` (omis ou ``null``) = INCONNU ; ``[]`` = aucun allergène
    (la caisse le dit). Une valeur hors des 26 rend l'ensemble inconnu : jamais un « aucun » deviné depuis une valeur que nous ne savons pas lire."""
    if valeurs is None:
        return None
    ramenes = table_inco()["hubrise"]["valeurs"]
    if any(v not in ramenes for v in valeurs):
        return None
    return list(dict.fromkeys(ramenes[v] for v in valeurs))  # dans l'ordre où la caisse les donne, sans doublon (six céréales à gluten donnent un seul gluten)


def allergene_vers_hubrise(codes: list[str] | None) -> list[str] | None:
    """Le sens inverse, pour la caisse de démo : la valeur HubRise qui porte chacun des 14 codes (``None`` reste ``None``, ``[]`` reste ``[]``)."""
    if codes is None:
        return None
    emis = table_inco()["hubrise"]["emis_par_la_caisse_de_demo"]
    return [emis[c] for c in codes]


def objets_a_comparer(carte: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """Les produits et les options d'une carte au format commun, par ``(objet, ref)``, avec leurs allergènes (``None`` = inconnu) et leurs ingrédients."""
    sortie: dict[tuple[str, str], dict[str, Any]] = {}
    for p in carte.get("produits") or []:
        sortie[("produit", p["id"])] = {"nom": p.get("nom"), "allergenes": p.get("allergenes"), "ingredients": _noms(p.get("ingredients"))}
    for g in carte.get("groupes") or []:
        for o in g.get("options") or []:
            sortie[("option", o["id"])] = {"nom": o.get("nom"), "allergenes": o.get("allergenes"), "ingredients": []}
    return sortie


def ecarts_caisse_et_suggestion(en_place: dict[tuple[str, str], dict[str, Any]], caisse: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    """« Vérifier depuis ma caisse » (D22) : les ÉCARTS entre les allergènes en place (validés) et ceux que la caisse porte, avec ce que les ingrédients suggèrent. Un écart est
    SIGNALÉ, jamais tranché ni écrit : ``nature`` = ``different`` (les deux disent, pas pareil), ``caisse_seule`` (rien en place, la caisse dit) ou ``ici_seulement`` (la caisse ne dit rien).
    Deux données égales (ou inconnues toutes les deux) ne sont pas un écart."""
    ecarts = []
    for cle, la_caisse in caisse.items():
        ici = en_place.get(cle)
        if ici is None or ici["allergenes"] == la_caisse["allergenes"]:
            continue  # pas à la carte d'ici, ou d'accord
        nature = "ici_seulement" if la_caisse["allergenes"] is None else ("caisse_seule" if ici["allergenes"] is None else "different")
        suggestion = suggerer_les_allergenes(la_caisse["ingredients"] or ici["ingredients"])["codes"] or None
        ecarts.append({"objet": cle[0], "ref": cle[1], "nom": ici["nom"] or la_caisse["nom"], "nature": nature, "ici": ici["allergenes"], "caisse": la_caisse["allergenes"], "suggestion": suggestion})
    return ecarts


def _mot_entier(mot: str, texte: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(mot.casefold())}s?(?!\w)", texte) is not None


def _noms(ingredients: list[Any] | None) -> list[str]:
    """Les noms d'ingrédients d'un produit (la carte les range en ``{"nom", "retirable"}`` ou en texte)."""
    noms = [str(i.get("nom") if isinstance(i, dict) else i).strip() for i in ingredients or []]
    return [n for n in noms if n and n != "None"]


def suggerer_les_allergenes(ingredients: list[Any] | None) -> dict[str, Any]:
    """``{"codes": [...], "a_preciser": [...], "proposable": bool}`` d'après les ingrédients. ``codes`` dans l'ordre des quatorze ; ``a_preciser`` : les ingrédients
    composés que la table ne reconnaît pas ; ``proposable`` : faux sans aucun code (rien n'est proposé : jamais un « aucun » deviné)."""
    table = table_inco()
    noms = _noms(ingredients)
    trouves: set[str] = set()
    a_preciser: list[str] = []
    for nom in noms:
        bas = nom.casefold()
        codes = {c for c, v in table["allergenes"].items() if any(_mot_entier(m, bas) for m in v["ingredients"])}
        trouves |= codes
        if not codes and any(_mot_entier(m, bas) for m in table["composes_a_preciser"]):
            a_preciser.append(nom)
    codes = [c for c in LES_QUATORZE if c in trouves]
    return {"codes": codes, "a_preciser": a_preciser, "proposable": bool(codes)}
