"""[.mark] Brique PRX4 : le prix par mode (inventaire, famille 6 ; aucune carte lue, modèles HubRise et Uber Eats).

Le même article se vend à un autre prix selon le mode (``prix_par_mode`` : ``{"<mode>": centimes}``) : la déclinaison (déjà lu avant le lot 12) et l'option (neuf). Le prix se
recalcule au chiffrage, quand le mode est connu : celui du mode s'il existe, sinon le prix de base. Code seulement, aucune case nouvelle.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_prx4_prix_au_mode(objet: dict[str, Any], mode: str | None, prix_de_base: int) -> int:
    """Le prix d'une déclinaison ou d'une option dans ``mode`` : ``prix_par_mode[mode]`` quand la donnée le dit, sinon ``prix_de_base``."""
    par_mode = objet.get("prix_par_mode") or {}
    return int(par_mode[mode]) if mode in par_mode else prix_de_base


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        for d in p["declinaisons"]:
            d["prix_par_mode"] = None
    for g in carte["groupes"]:
        for o in g["options"]:
            o["prix_par_mode"] = None
    return carte


enregistrer(Brique(
    "PRX4", "prix_et_conditions", "C", (("declinaisons", "prix_par_mode"), ("options", "prix_par_mode")), brique_prx4_prix_au_mode,
    change_la_fiche_du_modele=False, vue_sur_carte=False, sans_la_brique=_sans, carte_d_essai="briques/PRX4",
    phrase="le prix change selon le mode, au chiffrage ; aucune case nouvelle",
))
