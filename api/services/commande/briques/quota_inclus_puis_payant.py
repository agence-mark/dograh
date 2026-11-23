"""[.mark] Brique OPT3 : le quota inclus puis payant (inventaire, famille 3 ; règle du conflit D31).

N éléments compris dans le prix, les suivants se paient (bubble tea : un topping compris, le second 0,50 €). Le nombre inclus vit SUR LE GROUPE (``inclus``) ; une table
déclinaison x groupe le surcharge pour une taille (DEC2 : ``quotas``) ; une formule ne le change jamais. Le prix au-delà est celui du groupe (``prix_au_dela``) ou, à défaut,
celui de l'option. Les éléments comptent dans l'ordre où ils sont dits.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_opt3_facturer_au_dela(groupe: dict[str, Any], option: dict[str, Any], deja: int, quantite: int) -> tuple[int, int, int]:
    """``(gratuites, payantes, prix_unitaire_paye)`` pour ``quantite`` unités de cette option, ``deja`` unités du groupe étant déjà prises. Sans quota inclus : tout se paie
    au prix de l'option (le comportement d'avant)."""
    inclus = groupe.get("inclus")
    if inclus is None:
        return 0, quantite, option["prix"]
    gratuites = max(0, min(quantite, inclus - deja))
    prix = groupe["prix_au_dela"] if groupe.get("prix_au_dela") is not None else option["prix"]
    return gratuites, quantite - gratuites, prix


def _sans(carte: dict) -> dict:
    for g in carte["groupes"]:
        g["inclus"], g["prix_au_dela"] = None, None
    return carte


enregistrer(Brique(
    "OPT3", "options", "C", (("groupes", "inclus"), ("groupes", "prix_au_dela")), brique_opt3_facturer_au_dela,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/OPT3",
    phrase="la question du groupe dit combien sont compris et le prix de chacun au-delà",
))
