"""[.mark] Brique ART2 : le lot de N pièces (inventaire, famille 1).

Le nom porte un nombre de pièces, parfois en plusieurs formats (« 10 Tenders » ou « 16 Hot Wings »). Chaque format est une déclinaison de type ``pieces`` :
« un seau de dix » est le format dix, jamais dix articles. La question d'un format absent est celle de DEC1 (le mot « pièces », donné par le type).
"""

from __future__ import annotations

from api.services.commande.briques.registre import Brique, enregistrer

TYPE = "pieces"


def brique_art2_format_en_declinaison(declinaisons: list[dict]) -> list[dict]:
    """Les formats d'un lot : les déclinaisons de type ``pieces``, dans l'ordre de la carte ; une quantité dite n'en multiplie jamais les pièces."""
    return [d for d in declinaisons if d.get("type") == TYPE]


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        for d in p["declinaisons"]:
            if d.get("type") == TYPE:
                d["type"] = None
    return carte


enregistrer(Brique(
    "ART2", "article", "C", (("declinaisons", "type"),), brique_art2_format_en_declinaison,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/ART2",
    phrase="la question d'un format absent parle de pièces",
))
