"""[.mark] Brique RET5 : le retrait d'ingrédient (inventaire, famille 4 ; jamais vue sur les 44 cartes).

« Sans oignon » : un ingrédient retirable, ou une option retirable (« sans la sauce », ``retirable`` de l'option), se retire sans changer le prix, sauf prix de retrait (``prix_retrait``,
signé : un retrait qui rend de l'argent est négatif). Ce que la carte ne décrit pas devient une note de ligne (``retrait_en_note``, lot 4). Un retrait à prix part à la caisse comme une
option ``removed`` portant ce prix (D50). Code seulement, aucune case nouvelle (D66).
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer

LISTE_DES_RETRAITS = "Retraits"


def options_retirables(groupes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Les options retirables des groupes de l'article, par nom."""
    return {o["nom"]: o for g in groupes for o in g["options"] if o.get("retirable") and o.get("vendable", True)}


def brique_ret5_retirer(retires: list[str], retirables: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Les choix à prix que les retraits dits ajoutent à la ligne : une entrée ``retire`` par option retirable qui a un prix de retrait ; un retrait sans prix n'en fait pas."""
    sortie = []
    for nom in retires:
        o = retirables.get(nom)
        if o is not None and o.get("prix_retrait") is not None:
            sortie.append({"option_code": o["code_caisse"], "quantite": 1, "choix": [], "nom": nom, "prix": int(o["prix_retrait"]), "groupe": LISTE_DES_RETRAITS, "retire": True})
    return sortie


enregistrer(Brique(
    "RET5", "ajouts", "C", (("options", "retirable"), ("options", "prix_retrait")), brique_ret5_retirer,
    change_la_fiche_du_modele=False, vue_sur_carte=False, sans_la_brique=lambda carte: carte, carte_d_essai="briques/RET5",
    phrase="rien de nouveau pour le modèle : un retrait sans changer le prix, sauf prix de retrait",
))
