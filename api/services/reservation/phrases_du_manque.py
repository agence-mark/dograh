"""[.mark] Chantier Partie 1, lot 7 (B12, décision 1) : les phrases de ce qui manque à la réservation, une par valeur fermée de « manque ».

Même rôle que ``commande/phrases_du_manque.py``. La valeur fermée est celle de l'état (``etat_pour_le_modele.ce_qui_manque_ensuite``) ; la phrase n'est plus dite par le code (C5 : le modèle est relancé avec la valeur fermée, ``valeur_du_manque``) ; elle reste ici jusqu'à C7. Mot pour mot : celles du banc final
(``banc-b13/appel_b13.py`` ``PHRASE_DU_MANQUE_RESERVATION``). Une valeur portée par une question n'a pas de phrase propre : c'est la question qui la porte.
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from typing import Any

from api.services.reservation import etat_pour_le_modele as E
from api.services.reservation import textes_de_secours as TS

PHRASES_DU_MANQUE: dict[str, str] = {
    "le nombre de personnes": TS.PERSONNES,
    "le jour": TS.JOUR,
    "l'heure": TS.HEURE,
    "le nom": TS.NOM,
    "le numéro de téléphone": TS.TELEPHONE,
    "le nom et le jour de sa réservation d'avant": TS.NOM_ET_JOUR_D_AVANT,
}


def phrase_du_manque(manque: str | None) -> str | None:
    """La phrase de ce qui manque, mot pour mot ; ``None`` : rien ne manque."""
    return PHRASES_DU_MANQUE.get(manque) if manque else None


def valeur_du_manque(etat: dict[str, Any], fiche: dict[str, Any] | None = None) -> str | None:
    """La valeur fermée de ce qui manque ENSUITE pour cette réservation, quand aucune question n'attend (C5 : la relance du modèle la reçoit comme un fait)."""
    if CONV.question_de(etat):
        return None
    manque = E.ce_qui_manque_ensuite(etat, bool(etat.get("numero_affiche")))
    return manque if manque in PHRASES_DU_MANQUE else None
