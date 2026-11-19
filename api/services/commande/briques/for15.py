"""[.mark] Brique FOR15 : la boisson ou le buffet à volonté (inventaire, famille 5).

Une ligne ``a_volonte`` : un choix compris, aucune quantité facturée (la quantité dite ne multiplie rien) ; la caisse le reçoit en note de ligne (aucun modèle de caisse
ne l'exprime, inventaire § 5 : ``regle_inconnue_en_note``) ; le retour porte le fait ``a_volonte``.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_for15_a_volonte(etape: dict[str, Any], choix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Les choix d'une ligne à volonté : un par produit, quantité 1 (rien n'est facturé à la quantité)."""
    if not etape.get("a_volonte"):
        return choix
    vus: dict[str, dict[str, Any]] = {}
    for c in choix:
        vus.setdefault(c["option_code"], {**c, "quantite": 1})
    return list(vus.values())


def note_a_volonte(etape_nom: str) -> str:
    return f"{etape_nom} à volonté"


def _sans(carte: dict) -> dict:
    for f in carte["formules"]:
        for ligne in f["lignes"]:
            ligne.pop("a_volonte", None)
    return carte


enregistrer(Brique(
    "FOR15", "formules", "C", (("formules", "lignes"),), brique_for15_a_volonte,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/FOR15",
    phrase="rien de nouveau : la ligne à volonté n'a aucune quantité facturée",
))
