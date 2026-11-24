"""[.mark] Lot 7a, ligne 23 : « après un refus » se lit au journal du dit (la suite de ce qui s'est passé dans le tour, dans l'ordre), plus sur deux drapeaux qu'une lecture remettait à zéro.
Une lecture n'efface pas le refus : c'est le dernier genre noté. La réponse à la lecture (lot 20, n11) reste dite ; un refus APRÈS la lecture repose le rattrapage."""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes import parole as PA
from api.services.actions_communes.du import ce_qui_se_voit

REFUS = {"statut": "PARTIEL", "refus": [{"case": "mode_de_retrait", "raison": "valeur_hors_liste"}], "resultats": []}


def _tour_refuse_puis_lu():
    p, fiche = {"lignes": [{}]}, {PA.CLE_DU_TOUR: 1}
    etat = PA.etat_du_tour(fiche)
    PA.parole_du_tour(REFUS, "Je vérifie.", etat, [], p)
    PA.garder(fiche, etat)
    return p, fiche


def test_le_refus_est_au_journal_et_la_lecture_vient_apres_lui_sans_l_effacer():
    p, fiche = _tour_refuse_puis_lu()
    assert J.apres_un_refus(p, 1)
    PA.noter_la_lecture_rendue(fiche, p)
    assert not J.apres_un_refus(p, 1)
    assert p[CONV.CLE][J.CLE][J.SUITE]["suite"] == [J.REFUS_DE_LA_FICHE, J.LECTURE]  # l'ordre est gardé : refus puis lecture


def test_la_reponse_a_la_lecture_est_dite_et_un_refus_apres_elle_repose_le_rattrapage():
    p, fiche = _tour_refuse_puis_lu()
    PA.noter_la_lecture_rendue(fiche, p)
    reponse = "La Napoli contient des anchois, des câpres et des olives."
    assert PA.phrase_libre_retenue(reponse, PA.etat_du_tour(fiche), objet_en_cours=True, question_en_attente=False, paroles=[], p=p) is None
    PA.parole_du_tour(REFUS, "Je vérifie.", PA.etat_du_tour(fiche), [], p)
    assert J.apres_un_refus(p, 1)


def test_la_suite_repart_a_zero_quand_la_personne_reparle():
    p, _ = _tour_refuse_puis_lu()
    assert not J.apres_un_refus(p, 2)
    J.noter_dans_le_tour(p, J.FAIT, 2)
    assert p[CONV.CLE][J.CLE][J.SUITE]["suite"] == [J.FAIT]


def test_noter_la_suite_ne_change_pas_le_verdict_la_commande_a_t_elle_change():
    """Écrite après ``constater`` : deux fois la même fiche rendent le même ``ce_qui_se_voit`` (l'entrée du tour n'est pas un effet de plus)."""
    p = {"lignes": [{"ref": "a", "quantite": 1}]}
    J.noter_dans_le_tour(p, J.FAIT, 1)
    avant = ce_qui_se_voit(p)
    J.noter_dans_le_tour(p, J.FAIT, 1)  # la même fiche rejouée dans le tour : seule la suite s'allonge, jamais la commande ni la question
    assert {k: v for k, v in ce_qui_se_voit(p).items() if k != J.CLE} == {k: v for k, v in avant.items() if k != J.CLE}
