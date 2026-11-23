"""[.mark] Module Restauration, lot 4 : les réglages de l'agent pour la recherche dans une liste (module « Recherche dans une liste »).

Lit les clés du registre des modules (``api/services/modules/registre.py``) dans la configuration d'un appel et en fait les
``Reglages`` du moteur. Une valeur absente ou hors bornes retombe sur le défaut du module : un réglage mal écrit ne casse jamais
un appel (R1 : il se voit au journal). Le module coupé (``recherche_dans_une_liste`` faux) : ``None``, l'outil de recherche n'existe
pas pour cet appel (même règle que les autres modules).
"""

from __future__ import annotations

from loguru import logger

from api.db.bases_clients.recherche_liste_moteur import Reglages
from api.schemas.workflow_configurations import (
    DEFAULT_RECHERCHE_DANS_UNE_LISTE,
    DEFAULT_RECHERCHE_LISTE_SENS,
    DEFAULT_RECHERCHE_LISTE_SEUIL_AMBIGU,
    DEFAULT_RECHERCHE_LISTE_SEUIL_RETENU,
    DEFAULT_RECHERCHE_LISTE_SON,
)

CLE_INTERRUPTEUR = "recherche_dans_une_liste"


def module_allume(run_configs: dict | None) -> bool:
    valeur = (run_configs or {}).get(CLE_INTERRUPTEUR, DEFAULT_RECHERCHE_DANS_UNE_LISTE)
    return bool(valeur) if isinstance(valeur, bool) else DEFAULT_RECHERCHE_DANS_UNE_LISTE


def _nombre(run_configs: dict, cle: str, defaut: float, bas: float, haut: float) -> float:
    valeur = run_configs.get(cle, defaut)
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)) or not bas <= float(valeur) <= haut:
        logger.warning(f"[.mark] Closed-list search: setting {cle}={valeur!r} out of bounds [{bas}, {haut}], default {defaut} used")
        return defaut
    return float(valeur)


def reglages_de_la_recherche(run_configs: dict | None, mots_de_categorie: tuple[str, ...] = ()) -> Reglages | None:
    """Les réglages du moteur pour CET appel ; ``None`` quand le module est coupé."""
    if not module_allume(run_configs):
        return None
    configs = run_configs or {}
    retenu = _nombre(configs, "recherche_liste_seuil_retenu", DEFAULT_RECHERCHE_LISTE_SEUIL_RETENU, 0.6, 1.0)
    ambigu = _nombre(configs, "recherche_liste_seuil_ambigu", DEFAULT_RECHERCHE_LISTE_SEUIL_AMBIGU, 0.5, 0.95)
    if ambigu >= retenu:  # un seuil de proposition au-dessus du seuil de rétention n'a pas de sens : on garde les défauts des deux
        logger.warning("[.mark] Closed-list search: ambiguity threshold not under the pick threshold, defaults used")
        retenu, ambigu = DEFAULT_RECHERCHE_LISTE_SEUIL_RETENU, DEFAULT_RECHERCHE_LISTE_SEUIL_AMBIGU
    son = configs.get("recherche_liste_son", DEFAULT_RECHERCHE_LISTE_SON)
    sens = configs.get("recherche_liste_sens", DEFAULT_RECHERCHE_LISTE_SENS)
    return Reglages(
        seuil_retenu=retenu, seuil_ambigu=ambigu,
        couche_son=son if isinstance(son, bool) else DEFAULT_RECHERCHE_LISTE_SON,
        couche_sens=sens if isinstance(sens, bool) else DEFAULT_RECHERCHE_LISTE_SENS,
        mots_de_categorie=tuple(mots_de_categorie),
    )
