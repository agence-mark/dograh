"""[.mark] Lot 7b, M6 : le nombre de fois qu'une même chose se redit avant la sortie (proposer un message à l'équipe), réglage du restaurant.

UNE clé de configuration par métier (``commande_fois_avant_la_sortie``, ``reservation_fois_avant_la_sortie``) ; la valeur par défaut de chacune vit dans le schéma
(``schemas/workflow_configurations.py``, lue par le formulaire) et ``seuil_de_sortie`` la reçoit de l'appelant : aucune constante cachée ici. Le journal de ce qui est dit ne lit
aucun réglage : il reçoit le seuil.
"""

from __future__ import annotations

from collections.abc import Mapping

from loguru import logger

CLE_FOIS_AVANT_LA_SORTIE = "commande_fois_avant_la_sortie"
CLE_RESERVATION = "reservation_fois_avant_la_sortie"
SEUIL_BAS, SEUIL_HAUT = 2, 5


def seuil_de_sortie(configurations: Mapping | None, cle: str, defaut: int) -> int:
    """Le seuil réglé de l'agent sous ``cle`` (de 2 à 5) ; non réglé : ``defaut``, la valeur du schéma pour cette clé. Une valeur fausse est dite au journal et ne change rien."""
    valeur = (configurations or {}).get(cle)
    if valeur is None:
        return defaut
    if isinstance(valeur, int) and not isinstance(valeur, bool) and SEUIL_BAS <= valeur <= SEUIL_HAUT:
        return valeur
    logger.warning(f"[.mark] setting {cle}={valeur!r} is not an integer from {SEUIL_BAS} to {SEUIL_HAUT}, default {defaut} used")
    return defaut
