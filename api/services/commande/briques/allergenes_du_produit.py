"""[.mark] Brique INF1 : les allergènes d'un produit (inventaire, famille 9 ; D22, E21).

La carte ne rend que les allergènes VALIDÉS (une suggestion encore proposée est un inconnu : ``restauration_carte``). La règle : ``None`` = la fiche ne dit rien, jamais « sans »
(« je ne peux pas vous le confirmer ») ; une liste (même vide) permet de dire, d'après la fiche, que le produit contient ou ne contient pas ``code``.
"""

from __future__ import annotations

from api.services.commande.briques.registre import Brique, enregistrer


def brique_inf1_repondre_depuis_la_donnee(allergenes: list[str] | None, code: str) -> str:
    """``present`` (la fiche dit que le produit en contient), ``absent_de_la_fiche`` (la liste ne le nomme pas : c'est la fiche qui le dit) ou ``inconnu`` (aucune donnée)."""
    if allergenes is None:
        return "inconnu"
    return "present" if code in allergenes else "absent_de_la_fiche"


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        p["allergenes"] = None
    return carte


enregistrer(Brique(
    "INF1", "informations", "B", (("produits", "allergenes"),), brique_inf1_repondre_depuis_la_donnee,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/INF1",
    phrase="seuls les allergènes validés sont dits ; null : « je ne peux pas vous le confirmer »",
))
