"""[.mark] Brique OFF2 : la remise en pourcentage (inventaire, famille 8 ; A21 : « -20 % sur les plats chauds », A18).

Même principe qu'OFF1 : la famille ``pourcentage`` du moteur commun de remises calcule le montant au centime, sur le périmètre de la remise (catégories, produits, modes) ;
la remise se déduit EN FIN DE CALCUL (le sous-total net, D33). Cette entrée la nomme au registre et y délègue. Le montant que le modèle dit est celui que le code calcule (un fait, C6 n° 11).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from api.db.bases_clients import remises_moteur as moteur
from api.services.commande.briques.registre import Brique, enregistrer


def brique_off2_en_fin_de_calcul(pourcentage: float, unites: Sequence[moteur.Unite], perimetre: dict[str, Any] | None = None, mode: str | None = None) -> dict[str, Any]:
    """Le montant d'une remise de ``pourcentage`` % sur ce qui est dans son périmètre : ``{"montant", "unites"}`` en centimes, ``{}`` quand rien n'est à réduire."""
    regle = {"famille": "pourcentage", "effet": {"pourcentage": pourcentage}, "perimetre": perimetre or {}}
    effet = moteur.evaluer(regle, unites, moteur.Contexte(mode, sum(u.prix for u in unites)))
    return {"montant": effet.montant, "unites": list(effet.unites)} if effet else {}


enregistrer(Brique(
    "OFF2", "offres", "C", (), brique_off2_en_fin_de_calcul, change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=lambda carte: carte, carte_d_essai="briques/OFF2",
    phrase="une remise en pourcentage se déduit en fin de calcul sur son périmètre ; le montant est un fait du code, que le modèle dit",
))
