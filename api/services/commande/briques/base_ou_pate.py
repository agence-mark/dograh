"""[.mark] Brique DEC4 : la base ou la pâte au choix (inventaire, famille 2).

Une base (tomate, crème, croûte garnie) avec ou sans surcoût, sur certains produits seulement : un groupe de choix obligatoire (un seul), son surcoût est le prix
de l'option. Un produit qui n'a pas ce groupe refuse la base dite (HORS_CARTE avec la raison), jamais une base posée dans le vide.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_dec4_une_base_par_article(article: dict[str, Any]) -> list[dict[str, Any]]:
    """Les groupes d'un article dont on choisit exactement une option (la base) ; vide : l'article n'a pas ce choix."""
    return [g for g in article.get("groupes") or [] if g["min"] == 1 and g["max"] == 1]


def _sans(carte: dict) -> dict:
    ids = {g["id"] for g in carte["groupes"] if g["min"] == 1 and g["max"] == 1}
    carte["groupes"] = [g for g in carte["groupes"] if g["id"] not in ids]
    for p in carte["produits"]:
        p["groupes"] = [g for g in p.get("groupes") or [] if g not in ids]
    return carte


enregistrer(Brique(
    "DEC4", "declinaison", "C", (("groupes", "min"), ("groupes", "max")), brique_dec4_une_base_par_article,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/DEC4",
    phrase="la question du groupe de la base, avec le prix de chaque option",
))
