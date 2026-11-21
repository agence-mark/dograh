"""Lot 20 (n11, rejoué au clavier) : une fiche refusée (mode « null »), puis une lecture réussie dans le même tour : la phrase qui répond à la lecture
(« La Napoli contient des anchois… ») était retenue comme un rattrapage après refus, puis remplacée par le repli du code. Garde sur l'état : la dernière
chose rendue au modèle est la lecture ; sa réponse est dite (la barrière des chiffres s'applique toujours)."""

from api.services.actions_communes import parole as PA


def _tour_refuse_puis_lu():
    fiche = {PA.CLE_DU_TOUR: 1}
    etat = PA.etat_du_tour(fiche)
    PA.parole_du_tour({"statut": "PARTIEL", "refus": [{"case": "mode_de_retrait", "raison": "valeur_hors_liste"}], "resultats": []}, "Je vérifie.", etat, [])
    PA.garder(fiche, etat)
    return fiche


def test_la_reponse_a_une_lecture_apres_un_refus_est_dite():
    fiche = _tour_refuse_puis_lu()
    assert PA.etat_du_tour(fiche).apres_refus  # le refus de la fiche est bien vu
    PA.noter_la_lecture_rendue(fiche)
    etat = PA.etat_du_tour(fiche)
    assert PA.phrase_libre_retenue("La Napoli contient des anchois, des câpres et des olives.", etat,
                                   objet_en_cours=True, question_en_attente=False, paroles=[]) is None


def test_sans_lecture_le_rattrapage_apres_refus_reste():
    fiche = _tour_refuse_puis_lu()
    etat = PA.etat_du_tour(fiche)
    assert PA.phrase_libre_retenue("Je vérifie pour vous.", etat, objet_en_cours=True, question_en_attente=False, paroles=[]) == PA.APRES_REFUS
