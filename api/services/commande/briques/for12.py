"""[.mark] Brique FOR12 : le choix entre deux contenus (inventaire, famille 5 ; « 1 bouteille 1,5 L OU 3 canettes »).

Une ligne offre des alternatives (``alternatives`` : ``[{"codes", "quantite"}]``) : la ligne prend UNE alternative, jamais un mélange (``alternatives_melangees``, avec les
alternatives) ; ses choix vont jusqu'à la quantité de l'alternative ; un seul produit dit d'une alternative à plusieurs unités en remplit la quantité (« des canettes de
coca » : trois canettes).
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer

RAISON = "alternatives_melangees"


def alternative_de(ligne: dict[str, Any], code: str) -> dict[str, Any]:
    for k, a in enumerate(ligne.get("alternatives") or []):
        if code in (a.get("codes") or []):
            return {"alternative": k, "quantite_de_l_alternative": int(a.get("quantite") or 1)}
    return {}


def brique_for12_une_alternative(etape: dict[str, Any], choix: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Les choix de l'étape dans une seule alternative, à sa quantité : ``(choix, None)``, ou ``(choix, refus)``."""
    if not etape.get("alternatives") or not choix:
        return choix, None
    options = {o["code"]: o for o in etape["options"]}
    rangs = {options[c["option_code"]].get("alternative") for c in choix if c["option_code"] in options}
    if len(rangs) > 1:
        return choix, {"raison": RAISON, "etape": etape["nom"],
                       "choix": [" ou ".join(o["nom"] for o in etape["options"] if o.get("alternative") == k) for k in range(len(etape["alternatives"]))]}
    rang = next(iter(rangs), None)
    if rang is None:
        return choix, None
    voulu = int(etape["alternatives"][rang].get("quantite") or 1)
    total = sum(int(c.get("quantite", 1)) for c in choix)
    if len(choix) == 1 and total < voulu:
        return [{**choix[0], "quantite": voulu}], None
    if total > voulu:
        return choix, {"raison": "plusieurs_choix", "etape": etape["nom"], "maximum": voulu}
    return choix, None


def minimum_de_l_etape(etape: dict[str, Any], choix: list[dict[str, Any]]) -> int:
    """Le nombre de choix qui remplit l'étape : à alternatives, la quantité de l'alternative prise (« une bouteille » remplit une étape de trois canettes,
    conversation FOR12-A du lot 11) ; sinon, ou rien de pris, son minimum."""
    if not etape.get("alternatives") or not choix:
        return int(etape["min"])
    rangs = {o.get("alternative") for o in etape["options"] if any(c["option_code"] == o["code"] for c in choix)} - {None}
    if len(rangs) != 1:
        return int(etape["min"])
    voulu = int(etape["alternatives"][next(iter(rangs))].get("quantite") or 1)
    return min(int(etape["min"]), voulu) if etape["min"] else 0


def _sans(carte: dict) -> dict:
    for f in carte["formules"]:
        for ligne in f["lignes"]:
            ligne.pop("alternatives", None)
    return carte


enregistrer(Brique(
    "FOR12", "formules", "C", (("formules", "lignes"),), brique_for12_une_alternative,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/FOR12",
    phrase="une alternative à la fois ; un mélange est refusé avec les alternatives",
))
