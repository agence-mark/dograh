"""[.mark] Chantier Partie 1, lot 4 (M13 ; B12, décision 1), puis lot 7b-C7 B9 : la valeur fermée de ce qui manque à la commande.

La valeur fermée (``Manque``) est celle de l'état (``etat_pour_le_modele.ce_qui_manque_ensuite``, vocabulaire de B8). Le modèle la reçoit comme un fait et pose la question avec
ses mots (C5 : ``valeur_du_manque`` ; décision d'Evan 25/11 8 h 45) ; les phrases d'avant sont supprimées en B9. Une valeur portée par une question (la variante, l'accord sur
le récapitulatif) ne se donne jamais seule : c'est la question qui la porte.
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from typing import Any

from enum import StrEnum


class Manque(StrEnum):
    """Ce qui manque à une commande : une liste fermée. La valeur est le mot que l'état montre au modèle ; la décision lit le membre, jamais ces mots."""

    MODE = "le mode de retrait"  # suivi de ses choix entre parenthèses dans l'état : « le mode de retrait (à emporter ou en livraison) »
    ADRESSE_ET_COMMUNE = "l'adresse de livraison (numéro, rue et commune)"
    COMMUNE = "la commune de livraison"
    VOIE = "l'adresse (numéro et rue)"
    ARTICLES = "les articles"
    VARIANTE = "une variante à choisir"
    AUTRE_CHOSE = "d'autres articles, ou qu'elle dise qu'elle a tout dit"
    ACCORD = "son accord sur le récapitulatif"
    PAIEMENT = "le moyen de paiement"
    TELEPHONE = "le numéro de téléphone"
    PRENOM = "le prénom"
    CONSIGNE_LIVREUR = "une consigne pour le livreur"


# Liste fermée : ce qui manque et qu'une question du module porte (la variante, l'accord sur le récapitulatif) ; la relance ne le reçoit jamais seul.
PORTEES_PAR_UNE_QUESTION = frozenset({Manque.VARIANTE, Manque.ACCORD})


def valeur_du_manque(p: dict[str, Any]) -> str | None:
    """La valeur fermée de ce qui manque ENSUITE pour ce panier, quand aucune question n'attend (C5 : la relance du modèle la reçoit comme un fait). Choisie dans une liste
    fermée, jamais selon qu'une phrase existe (lot 7b-C7) : ni une valeur portée par une question (``PORTEES_PAR_UNE_QUESTION``), ni le mode sans mode ouvert."""
    from api.services.commande import etat_pour_le_modele as E

    if CONV.question_de(p):
        return None
    manque, modes = E.ce_qui_manque(p, p.get(E.CLE_CONNU) or {})
    if manque is None or manque in PORTEES_PAR_UNE_QUESTION or (manque is Manque.MODE and not modes):
        return None
    return str(manque.value)
