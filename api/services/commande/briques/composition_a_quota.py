"""[.mark] Brique RET7 : la composition libre à quota (inventaire, famille 4).

Une base plus N éléments par catégorie à prix fixe (poké : 1 base, 1 protéine, 4 légumes, 1 fruit) : un groupe par catégorie (minimum, maximum). Tout passe par ``ajouter[].composition`` : le
code range chaque mot dans son groupe, compte le quota et refuse le dépassement avec la raison ; la relecture groupée à la fin redit tout (B9 § 3, B10 § 4).
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_ret7_composer(groupes: list[dict[str, Any]], comptes: dict[str, int]) -> list[dict[str, Any]]:
    """Les catégories de la composition qui attendent encore des éléments (en dessous de leur minimum), avec ce qui manque, dans l'ordre de la carte."""
    return [{"groupe": g["nom"], "manque": g["min"] - comptes.get(g["id"], 0)} for g in groupes if comptes.get(g["id"], 0) < g["min"]]


def _sans(carte: dict) -> dict:
    retires = {g["id"] for g in carte["groupes"] if g["role"] == "choix"}
    carte["groupes"] = [g for g in carte["groupes"] if g["id"] not in retires]
    for p in carte["produits"]:
        p["groupes"] = [g for g in p.get("groupes") or [] if g not in retires]
    return carte


enregistrer(Brique(
    "RET7", "ajouts", "C", (("groupes", "min"), ("groupes", "max")), brique_ret7_composer,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/RET7",
    phrase="la case de composition existe ; la question de chaque catégorie porte son minimum et son maximum",
))
