"""[.mark] Mécanisme commun : les réglages de la commande, lus dans la configuration de l'agent (registre des modules, module « Commande »).

Une valeur absente ou d'un mauvais type retombe sur le défaut du module : un réglage mal écrit ne casse jamais un appel. Le module coupé
(``commande_sur_catalogue`` faux) : ``None``, aucun outil de commande n'existe pour cet appel (même règle que les autres modules).
"""

from __future__ import annotations

from collections.abc import Mapping

from loguru import logger

from api.schemas.workflow_configurations import (
    DEFAULT_COMMANDE_MENTIONS_DE_REMISE,
    DEFAULT_COMMANDE_MOITIES_PRIX,
    DEFAULT_COMMANDE_NOTES_LIBRES,
    DEFAULT_COMMANDE_ORDRE_IMPOSE,
    DEFAULT_COMMANDE_RELECTURE_DEUX_TEMPS,
    DEFAULT_COMMANDE_SUR_CATALOGUE,
    DEFAULT_COMMANDE_VENTE_EN_PLUS,
)
from api.services.commande.moteur import Reglages

CLE_INTERRUPTEUR = "commande_sur_catalogue"
REGLES_MOITIES = ("plus_chere", "moyenne", "somme")


def _booleen(configs: Mapping, cle: str, defaut: bool) -> bool:
    valeur = configs.get(cle, defaut)
    if isinstance(valeur, bool):
        return valeur
    logger.warning(f"[.mark] Order module: setting {cle}={valeur!r} is not a boolean, default {defaut} used")
    return defaut


def _entier(configs: Mapping, cle: str, defaut: int, bas: int, haut: int) -> int:
    valeur = configs.get(cle, defaut)
    if isinstance(valeur, int) and not isinstance(valeur, bool) and bas <= valeur <= haut:
        return valeur
    logger.warning(f"[.mark] Order module: setting {cle}={valeur!r} is not an integer from {bas} to {haut}, default {defaut} used")
    return defaut


def module_allume(configurations: Mapping | None) -> bool:
    """Sans configuration posée (essai isolé, montage à la main) : allumé, comme avant les modules. Posée : l'interrupteur de l'agent."""
    if configurations is None:
        return True
    return _booleen(configurations, CLE_INTERRUPTEUR, DEFAULT_COMMANDE_SUR_CATALOGUE)


def reglages_de_la_commande(configurations: Mapping | None) -> Reglages | None:
    """Les réglages pour CET appel ; ``None`` quand le module est coupé."""
    if not module_allume(configurations):
        return None
    configs = configurations or {}
    regle = configs.get("commande_moities_prix", DEFAULT_COMMANDE_MOITIES_PRIX)
    if regle not in REGLES_MOITIES:
        logger.warning(f"[.mark] Order module: half-and-half price rule {regle!r} unknown, default used")
        regle = DEFAULT_COMMANDE_MOITIES_PRIX
    return Reglages(
        ordre_impose=_booleen(configs, "commande_ordre_impose", DEFAULT_COMMANDE_ORDRE_IMPOSE),
        relecture_en_deux_temps=_booleen(configs, "commande_relecture_deux_temps", DEFAULT_COMMANDE_RELECTURE_DEUX_TEMPS),
        vente_en_plus=_booleen(configs, "commande_vente_en_plus", DEFAULT_COMMANDE_VENTE_EN_PLUS),
        notes_libres=_booleen(configs, "commande_notes_libres", DEFAULT_COMMANDE_NOTES_LIBRES),
        regle_moities=regle,
        mentions_de_remise=_entier(configs, "commande_mentions_de_remise", DEFAULT_COMMANDE_MENTIONS_DE_REMISE, 0, 5),
    )
