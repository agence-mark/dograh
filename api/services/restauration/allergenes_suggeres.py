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
