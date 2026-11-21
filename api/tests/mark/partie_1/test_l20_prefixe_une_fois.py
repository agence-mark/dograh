"""Lot 20 (relecture, conv2) : deux fiches du même tour refusées sur la même zone : « Nous ne livrons pas à Compiègne… » était dit deux fois de suite.
Garde sur l'état du tour : une phrase du code déjà dite dans ce tour ne l'est pas une seconde fois."""

from api.services.actions_communes import parole as PA

HORS_ZONE = "Nous ne livrons pas à Compiègne. Nous livrons Senlis et Chantilly."
REFUS = {"statut": "PARTIEL", "refus": [{"case": "commune", "raison": "hors_zone"}], "resultats": []}


def test_la_phrase_du_code_n_est_dite_qu_une_fois_par_tour():
    etat = PA.EtatDuTour(tour=1)
    premiere = PA.parole_du_tour(REFUS, "C'est noté.", etat, [], textes={"prefixe": HORS_ZONE})
    seconde = PA.parole_du_tour(REFUS, "Je ne peux pas livrer.", etat, [], textes={"prefixe": HORS_ZONE})
    assert premiere.prefixe == HORS_ZONE and seconde.prefixe is None
    assert PA.parole_du_tour(REFUS, "x", PA.EtatDuTour(tour=2), [], textes={"prefixe": HORS_ZONE}).prefixe == HORS_ZONE  # un autre tour : redite
