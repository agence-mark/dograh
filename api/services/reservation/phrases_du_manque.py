"""[.mark] Chantier Partie 1, lot 7 (B12, décision 1) : les phrases de ce qui manque à la réservation, une par valeur fermée de « manque ».

Même rôle que ``commande/phrases_du_manque.py``. La valeur fermée est celle de l'état (``etat_pour_le_modele.ce_qui_manque_ensuite``) ; la phrase est proposée
par le code dans ``texte_a_dire`` et le code ne la dit lui-même que dans le repli de la couche de parole (lot 6). Mot pour mot : celles du banc final
(``banc-b13/appel_b13.py`` ``PHRASE_DU_MANQUE_RESERVATION``). Une valeur portée par une question n'a pas de phrase propre : c'est la question qui la porte.
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from typing import Any

from api.services.reservation import etat_pour_le_modele as E

PHRASES_DU_MANQUE: dict[str, str] = {
    "le nombre de personnes": "Pour combien de personnes ?",
    "le jour": "Pour quel jour ?",
    "l'heure": "À quelle heure ?",
    "le nom": "À quel nom ?",
    "le numéro de téléphone": "Quel est votre numéro de téléphone ?",
    "le nom et le jour de sa réservation d'avant": "À quel nom et pour quel jour était votre réservation ?",
}


def phrase_du_manque(manque: str | None) -> str | None:
    """La phrase de ce qui manque, mot pour mot ; ``None`` : rien ne manque."""
    return PHRASES_DU_MANQUE.get(manque) if manque else None


def texte_a_dire(etat: dict[str, Any], fiche: dict[str, Any] | None = None) -> str | None:
    """La phrase de ce qui manque ENSUITE pour cette réservation, quand aucune question n'attend : ce que le retour propose dans ``texte_a_dire``."""
    if CONV.question_de(etat):
        return None
    return phrase_du_manque(E.ce_qui_manque_ensuite(etat, bool(etat.get("numero_affiche"))))
