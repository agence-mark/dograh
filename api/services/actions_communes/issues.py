"""[.mark] Chantier Partie 1, lot 19 bis (P6) : l'issue de l'appel, posée une fois et jamais écrasée par une issue de moindre rang.

Le code de l'issue est réglable (``reglages.issues``) : la fiche garde donc, à côté du code, le NOM de l'issue (``issue_de_l_appel``) pour comparer. « Commande enregistrée » reste, quoi qu'il arrive
ensuite dans l'appel (un message laissé, une réservation) : seule l'annulation de cette commande la remplace. Aucun mot de métier.
"""

from __future__ import annotations

from typing import Any, Callable

from loguru import logger

REGLAGE_DES_ISSUES = "issues"
_PANNES_ATTENDUES = (AttributeError, KeyError, TypeError, ValueError)  # une fiche ou un réglage mal formé : l'issue ne se pose pas, l'appel continue

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


def code_de_l_issue(reglages: Any, issue: str) -> str:
    """Le code réglé sur l'outil pour cette issue (``reglages.issues``), sinon le nom de l'issue elle-même. Le même pour tous les métiers."""
    reglees = (reglages or {}).get(REGLAGE_DES_ISSUES) if isinstance(reglages, dict) else None
    code = reglees.get(issue) if isinstance(reglees, dict) else None
    return code.strip() if isinstance(code, str) and code.strip() else issue


def poser_l_issue(ctx: Any, issue: str) -> None:
    """L'issue de l'appel, posée dans la fiche de l'appel (P6 : « commande enregistrée » n'est jamais écrasée). ⛔ Ne lève jamais."""
    try:
        poser_l_issue_de_l_appel(getattr(ctx, "fiche", None), issue, code_de_l_issue(getattr(ctx, "reglages", None), issue))
    except _PANNES_ATTENDUES:
        logger.exception("[.mark] l'issue de l'appel n'a pas pu être posée")


def issue_de_fin_d_appel(fiche_de_l_appel: Any, cle_des_codes: str, issue_d_abandon: str, commencee: Callable[[Any], bool]) -> str | None:
    """L'appel finit avec un dossier commencé (``commencee`` le dit, sur la fiche de l'appel) et aucune issue posée : l'issue d'abandon, avec son code réglé.
    ``None`` sinon. ⛔ Ne lève jamais."""
    try:
        if not isinstance(fiche_de_l_appel, dict) or fiche_de_l_appel.get("call_disposition") or not commencee(fiche_de_l_appel):
            return None
        return code_de_l_issue({REGLAGE_DES_ISSUES: fiche_de_l_appel.get(cle_des_codes)}, issue_d_abandon)
    except _PANNES_ATTENDUES:
        return None
