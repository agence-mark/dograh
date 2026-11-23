"""[.mark] Brique RET6 : la moitié-moitié (inventaire, famille 4 ; jamais vue sur les 44 cartes).

Deux demi-produits : un groupe de rôle ``moities`` à deux choix exactement, dont chaque moitié se nomme comme le produit de la carte (les noms courants et les synonymes du produit,
C13). La règle de prix (la plus chère, la moyenne, la somme) est celle de l'ÉTABLISSEMENT (``resto_reglage.moities_prix``) : la somme des prix des choix vaut le supplément que la règle
donne (``repartir_les_moities``). Code seulement, aucune case nouvelle (D66).
"""

from __future__ import annotations

from api.services.commande.briques.registre import Brique, enregistrer


def brique_ret6_deux_moities(prix: list[int], regle: str) -> list[int]:
    """Le prix porté par chaque moitié selon la règle de l'établissement ; une règle inconnue vaut « la plus chère »."""
    from api.db.bases_clients.restauration_commande import REGLES_MOITIES, repartir_les_moities  # à l'appel : la couche d'accès importe les briques
    return repartir_les_moities(prix, regle if regle in REGLES_MOITIES else "plus_chere")


enregistrer(Brique(
    "RET6", "ajouts", "B", (("groupes", "role"),), brique_ret6_deux_moities,
    change_la_fiche_du_modele=False, vue_sur_carte=False, sans_la_brique=lambda carte: carte, carte_d_essai="briques/RET6",
    phrase="rien de nouveau pour le modèle : les moitiés se prennent par les noms courants, au prix de la règle de l'établissement",
))
