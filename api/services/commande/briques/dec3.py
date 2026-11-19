"""[.mark] Brique DEC3 : la contenance (inventaire, famille 2).

Une boisson ou une portion en plusieurs contenances (canette, bouteille ; petite ou grande frite). La contenance n'est jamais supposée : elle se règle comme
DEC1 (la question numérotée), avec le mot que le type ``contenance`` donne. Alias déclaré.
"""

from __future__ import annotations

from api.services.commande.briques.dec1 import brique_dec1_demander_la_declinaison
from api.services.commande.briques.registre import Brique, enregistrer

TYPE = "contenance"


def brique_dec3_demander_la_contenance(declinaisons: list[dict]) -> dict:
    """La question de la contenance : celle de la déclinaison, au mot du type ``contenance`` ; refuse toute autre carte (aucune contenance n'est devinée)."""
    if not any(d.get("type") == TYPE for d in declinaisons):
        raise ValueError("Ces déclinaisons ne sont pas des contenances")
    return brique_dec1_demander_la_declinaison(declinaisons)


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        for d in p["declinaisons"]:
            if d.get("type") == TYPE:
                d["type"] = None
    return carte


enregistrer(Brique(
    "DEC3", "declinaison", "C", (("declinaisons", "type"),), brique_dec3_demander_la_contenance, alias_de="DEC1",
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/DEC3",
    phrase="la question d'une contenance absente parle de contenance",
))
