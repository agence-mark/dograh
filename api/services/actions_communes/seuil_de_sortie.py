"""[.mark] Lot 7b, M6 : le nombre de fois qu'une même chose se redit avant la sortie (proposer un message à l'équipe), réglage du restaurant.

Une seule clé de configuration pour les deux métiers ; chaque métier donne SA valeur d'aujourd'hui quand elle n'est pas réglée (commande 3, réservation 2 pour le choix non
compris et la recherche sans résultat, E28). Le journal de ce qui est dit ne lit aucun réglage : il reçoit le seuil.
"""

from __future__ import annotations

from collections.abc import Mapping

from loguru import logger

CLE_FOIS_AVANT_LA_SORTIE = "commande_fois_avant_la_sortie"
SEUIL_BAS, SEUIL_HAUT = 2, 5


def seuil_de_sortie(configurations: Mapping | None, defaut: int) -> int:
    """Le seuil réglé de l'agent (de 2 à 5) ; non réglé : ``defaut``, la valeur du métier. Une valeur fausse est dite au journal et ne change rien."""
    valeur = (configurations or {}).get(CLE_FOIS_AVANT_LA_SORTIE)
    if valeur is None:
        return defaut
    if isinstance(valeur, int) and not isinstance(valeur, bool) and SEUIL_BAS <= valeur <= SEUIL_HAUT:
        return valeur
    logger.warning(f"[.mark] setting {CLE_FOIS_AVANT_LA_SORTIE}={valeur!r} is not an integer from {SEUIL_BAS} to {SEUIL_HAUT}, default {defaut} used")
    return defaut
