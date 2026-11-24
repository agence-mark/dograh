"""[.mark] Lot 7a, ligne 36 : le prix d'une LECTURE (PRX5) reste dans l'état du tour (verdict du relecteur : la fiche mâchée était fausse, ``Du.prix_apres`` ne le porte pas),
dit une seule fois après la phrase suivante ; il n'entre jamais dans ``ce_qui_se_voit`` (le verdict « la commande a-t-elle changé ? » ne bouge pas)."""

from __future__ import annotations

from api.services.actions_communes import parole as PA
from api.services.actions_communes.du import ce_qui_se_voit


def test_le_prix_lu_suit_la_phrase_dite_puis_n_est_plus_du():
    fiche, p = {PA.CLE_DU_TOUR: 1}, {"lignes": [{"ref": "a", "quantite": 1}]}
    PA.poser_le_suffixe_lu(fiche, "Le tacos coûte 8 euros.")
    etat = PA.etat_du_tour(fiche)
    d = PA.parole_du_tour({"statut": "FAIT"}, "C'est noté.", etat, [], p)
    assert d.mode == PA.A_DIRE_SEUL and d.a_dire.endswith("Le tacos coûte 8 euros.")
    PA.garder(fiche, etat)
    assert PA.etat_du_tour(fiche).suffixe_lu is None


def test_le_prix_lu_tient_jusqu_au_repli_quand_la_phrase_est_retenue():
    fiche = {PA.CLE_DU_TOUR: 1}
    PA.poser_le_suffixe_lu(fiche, "Le tacos coûte 8 euros.")
    etat = PA.etat_du_tour(fiche)
    assert PA.avec_le_suffixe("Voilà.", etat) == "Voilà. Le tacos coûte 8 euros."
    assert etat.suffixe is None and etat.suffixe_lu is None


def test_poser_le_prix_lu_ne_change_pas_le_verdict_la_commande_a_t_elle_change():
    fiche, p = {PA.CLE_DU_TOUR: 1}, {"lignes": [{"ref": "a", "quantite": 1}]}
    avant = ce_qui_se_voit(p)
    PA.poser_le_suffixe_lu(fiche, "Le tacos coûte 8 euros.")
    assert ce_qui_se_voit(p) == avant
