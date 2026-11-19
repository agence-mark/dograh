"""[.mark] Brique PRX5 : le prix « à partir de » (inventaire, famille 6 ; la plupart des fiches de commande en ligne).

Le prix affiché d'un article à tailles ou à choix obligatoires payants est un prix de départ : le total se fait avec les choix. La lecture d'un article rend le fait ``prix``
(``montant`` : le plus bas total possible, ``a_partir_de`` : vrai dès qu'un autre total est possible) ; le chiffre est dit par le code (D33), jamais le prix de départ comme prix
final. Fonction pure : aucune requête, la carte chargée suffit.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def _prix_possibles(options: list[dict[str, Any]]) -> list[int]:
    return sorted(int(o["prix"]) for o in options if o.get("vendable") and not o.get("rupture"))


def brique_prx5_jamais_le_prix_de_depart_comme_final(article: dict[str, Any]) -> dict[str, Any] | None:
    """``{"montant", "a_partir_de"}`` pour un article de la carte (la vue de ``article_de_la_carte``), ou ``None`` (formule, ou aucune déclinaison vendable)."""
    if article.get("formule"):
        return None
    prix = [int(d["prix"]) for d in article.get("declinaisons") or [] if d.get("vendable") and not d.get("rupture")]
    if not prix:
        return None
    montant, variable = min(prix), len(set(prix)) > 1
    for g in article.get("groupes") or []:
        if g.get("role") not in (None, "choix") or int(g.get("min") or 0) < 1:
            continue
        possibles = _prix_possibles(g.get("options") or [])
        if len(possibles) < g["min"]:
            continue
        montant += sum(possibles[: g["min"]])
        variable = variable or len(set(possibles)) > 1
    return {"montant": montant, "a_partir_de": variable}


def _sans(carte: dict) -> dict:
    """La brique ne pose aucune donnée : elle lit les tailles et les choix payants de la carte. Sans elle, un seul prix possible par article."""
    for p in carte["produits"]:
        p["declinaisons"] = p["declinaisons"][:1]
    for g in carte["groupes"]:
        for o in g["options"]:
            o["prix"] = 0
    return carte


enregistrer(Brique(
    "PRX5", "prix_et_conditions", "C", (), brique_prx5_jamais_le_prix_de_depart_comme_final,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/PRX5",
    phrase="la lecture d'un article rend son prix, « à partir de » quand plusieurs totaux sont possibles",
))
