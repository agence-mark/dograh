"""[.mark] Brique QTE3 : la quantité par option (inventaire, famille 7 ; aucune carte lue, HubRise ``quantity`` par option, ``multiMax`` d'un modèle de commande).

« Deux algériennes » : une option se prend plusieurs fois, jusqu'au maximum par option du groupe (``max_par_option``). La règle existe déjà dans le chiffrage d'une ligne
(``_choix`` : ``MAXIMUM_ATTEINT``) et l'envoi écrit déjà la quantité de chaque option ; cette brique la NOMME au registre sans la réécrire (§ 12 point 8 du brief) et le test la prouve.
Code seulement, aucune case nouvelle.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_qte3_compter_par_option(groupe: dict[str, Any], pris_de_l_option: int) -> bool:
    """Vrai quand ``pris_de_l_option`` (le total pris de cette option) tient dans le maximum par option du groupe."""
    return pris_de_l_option <= int(groupe.get("max_par_option") or 1)


enregistrer(Brique(
    "QTE3", "quantite_et_unite", "C", (("groupes", "max_par_option"),), brique_qte3_compter_par_option,
    change_la_fiche_du_modele=False, vue_sur_carte=False, sans_la_brique=lambda carte: carte, carte_d_essai="briques/QTE3",
    phrase="une option se prend jusqu'au maximum par option du groupe ; aucune case nouvelle",
))
