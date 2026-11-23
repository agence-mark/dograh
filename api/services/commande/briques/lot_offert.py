"""[.mark] Brique OFF1 : N achetés, M offerts (inventaire, famille 8 ; A7 : « trois barquettes achetées, la quatrième offerte »).

La règle vit déjà dans le moteur commun de remises (``remises_moteur``, famille ``lot_offert`` : le moins cher du lot est offert, jamais au-delà du plafond de la remise) et la
table des douze mécanismes (``x_achetes_y_offert``). Cette entrée la NOMME au registre et y DÉLÈGUE (aucune réécriture, brief § 12 point 8) ; le test la prouve sur sa carte
d'essai et par l'aller-retour caisse (``discounts``). Code seulement : une remise se règle au portail, aucune case de la fiche ne change.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from api.db.bases_clients import remises_moteur as moteur
from api.services.commande.briques.registre import Brique, enregistrer


def brique_off1_par_paliers(achetes: int, offerts: int, unites: Sequence[moteur.Unite], perimetre: dict[str, Any] | None = None, plafond: int | None = None) -> dict[str, Any]:
    """Ce que rend une remise « ``achetes`` achetés, ``offerts`` offerts » sur ``unites`` : ``{"montant", "unites"}`` (le moins cher est offert), ``{}`` quand elle ne s'applique pas."""
    regle = {"famille": "lot_offert", "declencheur": {"achetes": achetes}, "effet": {"offerts": offerts}, "perimetre": perimetre or {}, "limite": {"max_par_achat": plafond} if plafond else {}}
    total = sum(u.prix for u in unites)
    effet = moteur.evaluer(regle, unites, moteur.Contexte(None, total))
    return {"montant": effet.montant, "unites": list(effet.unites)} if effet else {}


enregistrer(Brique(
    "OFF1", "offres", "C", (), brique_off1_par_paliers, change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=lambda carte: carte, carte_d_essai="briques/OFF1",
    phrase="N achetés, M offerts : le code chiffre la remise au centime, le moins cher est offert ; aucune case de la fiche",
))
