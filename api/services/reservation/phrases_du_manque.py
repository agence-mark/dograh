"""[.mark] Chantier Partie 1, lot 7 (B12, décision 1), puis lot 7b-C7 B9 : la valeur fermée de ce qui manque à la réservation.

Même rôle que ``commande/phrases_du_manque.py``. La valeur fermée est celle de l'état (``etat_pour_le_modele.ce_qui_manque_ensuite``) ; le modèle la reçoit comme un fait et pose
la question avec ses mots (C5 : ``valeur_du_manque`` ; décision d'Evan 25/11 8 h 45) ; les phrases d'avant sont supprimées en B9.
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from typing import Any

from api.services.reservation import etat_pour_le_modele as E

# Liste fermée : les valeurs de ce qui manque que l'état rend (``ce_qui_manque_ensuite``), que la relance du modèle reçoit ; lues dans le module d'état, jamais recopiées.
VALEURS_DU_MANQUE = frozenset(E.MANQUES)


def valeur_du_manque(etat: dict[str, Any], fiche: dict[str, Any] | None = None) -> str | None:
    """La valeur fermée de ce qui manque ENSUITE pour cette réservation, quand aucune question n'attend (C5 : la relance du modèle la reçoit comme un fait) : lue dans la liste
    fermée ``VALEURS_DU_MANQUE``, jamais selon qu'une phrase existe (lot 7b-C7)."""
    if CONV.question_de(etat):
        return None
    manque = E.ce_qui_manque_ensuite(etat, bool(etat.get("numero_affiche")))
    return manque if manque in VALEURS_DU_MANQUE else None
