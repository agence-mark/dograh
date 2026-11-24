"""[.mark] Lot 7a, ligne 23 et reprises 1 et 2 de l'audit : la suite du tour (refus, fait, lecture, dans l'ordre) et la phrase jetée vivent dans l'ÉTAT DU TOUR, jamais dans le dossier :
le connecteur service rend un dossier neuf à chaque appel (le refus serait perdu) et ce qui est dans le dossier compte dans ``ce_qui_se_voit`` (une lecture ferait croire
qu'une fiche n'a rien changé). Une lecture n'efface pas le refus : elle vient après lui."""

from __future__ import annotations

import copy

from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes import parole as PA
from api.services.actions_communes.du import ce_qui_se_voit

REFUS = {"statut": "PARTIEL", "refus": [{"case": "mode_de_retrait", "raison": "valeur_hors_liste"}], "resultats": []}


def _tour_refuse(dossier):
    fiche = {PA.CLE_DU_TOUR: 1}
    etat = PA.etat_du_tour(fiche)
    PA.parole_du_tour(REFUS, "Je vérifie.", etat, [], dossier)
    PA.garder(fiche, etat)
    return fiche


def test_service_un_refus_puis_une_phrase_sans_outil_donne_le_rattrapage_meme_avec_un_dossier_neuf():
    """Le service rend un dossier neuf à chaque appel : le refus ne doit pas y être gardé."""
    fiche = _tour_refuse({})
    assert PA.phrase_libre_retenue("Je transmets votre message.", PA.etat_du_tour(fiche), objet_en_cours=False, question_en_attente=False, paroles=[], p={}) == PA.APRES_REFUS


def test_la_lecture_vient_apres_le_refus_sans_l_effacer_et_l_ordre_est_gardé():
    fiche = _tour_refuse({"lignes": [{}]})
    assert PA.apres_un_refus(PA.etat_du_tour(fiche))
    PA.noter_la_lecture_rendue(fiche)
    etat = PA.etat_du_tour(fiche)
    assert not PA.apres_un_refus(etat) and etat.suite == [PA.REFUS_DE_LA_FICHE, PA.LECTURE]


def test_la_reponse_a_la_lecture_est_dite_et_un_refus_apres_elle_repose_le_rattrapage():
    p = {"lignes": [{}]}
    fiche = _tour_refuse(p)
    PA.noter_la_lecture_rendue(fiche)
    reponse = "La Napoli contient des anchois, des câpres et des olives."
    assert PA.phrase_libre_retenue(reponse, PA.etat_du_tour(fiche), objet_en_cours=True, question_en_attente=False, paroles=[], p=p) is None
    etat = PA.etat_du_tour(fiche)
    PA.parole_du_tour(REFUS, "Je vérifie.", etat, [], p)
    assert PA.apres_un_refus(etat)


def test_la_suite_repart_a_zero_quand_la_personne_reparle():
    fiche = _tour_refuse({})
    fiche[PA.CLE_DU_TOUR] = 2
    assert PA.etat_du_tour(fiche).suite == []


def test_une_lecture_pendant_une_fiche_ne_change_pas_ce_qui_se_voit_du_dossier():
    """Cas P3 : la lecture est rendue pendant qu'une fiche tourne ; ``ce_qui_se_voit`` (journal du dossier compris) ne bouge pas, la fiche ne se croit pas « sans effet »."""
    p = {"lignes": [{"ref": "a", "quantite": 2}]}
    J.noter(p, "une_regle", 1)
    fiche = _tour_refuse(p)
    vu = copy.deepcopy(ce_qui_se_voit(p))
    PA.noter_la_lecture_rendue(fiche)
    assert ce_qui_se_voit(p) == vu
    assert "suite_du_tour" not in (p.get("conversation") or {}).get(J.CLE, {}) and "phrase_jetee" not in (p.get("conversation") or {}).get(J.CLE, {})


def test_la_reprise_d_une_lecture_lente_n_efface_pas_ce_que_la_fiche_a_ecrit_entre_temps():
    p = {"lignes": []}
    copie = copy.deepcopy(p)
    avant = copy.deepcopy(J._lu(p))
    J.dire_le_fait(p, "C'est noté.", 1)  # la fiche écrit pendant que la lecture dure
    J.poser(p, "faits_d_allergie", 1, texte="x")
    J.noter(copie, "regle_servie", 1)  # ce que la lecture a écrit sur sa copie
    J.reprendre(p, copie, avant)
    assert J.fait_accompli(p) == "C'est noté." and J.deja_dit(p, "faits_d_allergie") and J.deja_dit(p, "regle_servie")
