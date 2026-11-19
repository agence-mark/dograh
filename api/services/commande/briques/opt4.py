"""[.mark] Brique OPT4 : le choix dans un choix (inventaire, famille 3).

Une option ouvre un sous-choix (tenders, puis sauce, puis piment) : un groupe rattaché à une option (``parent_option_id``), jusqu'à trois niveaux. Le code descend un
niveau à la fois (``moteur._groupes_a_remplir``) et la question de chaque niveau est posée quand l'option qui l'ouvre est choisie.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer

NIVEAUX_MAX = 3


def brique_opt4_un_niveau_a_la_fois(option: dict[str, Any]) -> list[dict[str, Any]]:
    """Les groupes que ce choix ouvre (vide : l'option n'ouvre rien)."""
    return list(option.get("enfants") or [])


def _sans(carte: dict) -> dict:
    enfants = {g["id"] for g in carte["groupes"] if g.get("parent_option_id")}
    carte["groupes"] = [g for g in carte["groupes"] if g["id"] not in enfants]
    for p in carte["produits"]:
        p["groupes"] = [g for g in p.get("groupes") or [] if g not in enfants]
    return carte


enregistrer(Brique(
    "OPT4", "options", "B", (("groupes", "parent_option_id"),), brique_opt4_un_niveau_a_la_fois,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/OPT4",
    phrase="la question de chaque niveau, quand l'option qui l'ouvre est choisie",
))
