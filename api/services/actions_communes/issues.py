"""[.mark] Chantier Partie 1, lot 19 bis (P6) : l'issue de l'appel, posée une fois et jamais écrasée par une issue de moindre rang.

Le code de l'issue est réglable (``reglages.issues``) : la fiche garde donc, à côté du code, le NOM de l'issue (``issue_de_l_appel``) pour comparer. « Commande enregistrée » reste, quoi qu'il arrive
ensuite dans l'appel (un message laissé, une réservation) : seule l'annulation de cette commande la remplace. Aucun mot de métier.
"""

from __future__ import annotations

from typing import Any

CLE_DE_L_ISSUE = "issue_de_l_appel"
ISSUE_QUI_RESTE = "commande_enregistree"
ISSUES_QUI_LA_REMPLACENT = frozenset({"commande_annulee"})


def poser_l_issue_de_l_appel(fiche: Any, issue: str, code: str) -> bool:
    """Pose l'issue (``code``, réglé) sauf si « commande enregistrée » est déjà posée et que ``issue`` n'est pas son annulation. Rend vrai quand elle a été posée."""
    if not isinstance(fiche, dict):
        return False
    if fiche.get(CLE_DE_L_ISSUE) == ISSUE_QUI_RESTE and issue != ISSUE_QUI_RESTE and issue not in ISSUES_QUI_LA_REMPLACENT:
        return False
    fiche["call_disposition"] = code
    fiche[CLE_DE_L_ISSUE] = issue
    return True
