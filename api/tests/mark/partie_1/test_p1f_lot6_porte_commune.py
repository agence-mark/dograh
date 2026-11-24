"""[.mark] Lot 6 (G2) : la commande et la réservation passent par la même porte pour l'issue de l'appel : un seul mécanisme, pas deux copies."""

from __future__ import annotations

from api.services.actions_communes import issues as ISSUES
from api.services.commande import porte as commande
from api.services.reservation import porte as reservation


def test_les_deux_metiers_posent_l_issue_par_le_meme_mecanisme():
    assert commande.poser_l_issue is reservation.poser_l_issue is ISSUES.poser_l_issue
    assert commande.code_de_l_issue is reservation.code_de_l_issue is ISSUES.code_de_l_issue


def test_la_meme_fiche_sans_issue_se_ferme_par_le_meme_code():
    fiche = {"commande_issues_reglees": {"commande_abandonnee": "Abandon"}, "reservation_issues_reglees": {"reservation_abandonnee": "Abandon"}}
    assert ISSUES.issue_de_fin_d_appel(fiche, "commande_issues_reglees", "commande_abandonnee", lambda f: True) == "Abandon"
    assert ISSUES.issue_de_fin_d_appel({**fiche, "call_disposition": "x"}, "commande_issues_reglees", "commande_abandonnee", lambda f: True) is None
    assert ISSUES.issue_de_fin_d_appel("pas une fiche", "k", "i", lambda f: True) is None
