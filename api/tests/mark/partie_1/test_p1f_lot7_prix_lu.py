"""[.mark] Lot 7a, ligne 36 : le prix d'une LECTURE (PRX5) reste dans l'état du tour, jamais dans ``ce_qui_se_voit`` (le verdict « la commande a-t-elle changé ? » ne bouge pas).

C6 n° 11 (décision d'Evan 25/11 9 h 30, § 8 bis : les prix D33 passent au modèle, vérifiés par la barrière) : le prix lu n'est plus dit par le code après la phrase suivante ; c'est
une valeur admise par la barrière des chiffres dans ce tour (``admettre_les_valeurs``), que le modèle dit avec ses mots. Un autre prix est retenu."""

from __future__ import annotations

from api.services.actions_communes import parole as PA
from api.services.actions_communes.barriere_des_chiffres import chiffre_dans_la_phrase
from api.services.actions_communes.du import ce_qui_se_voit

PRIX_LU = {"prix": {"montant": 800, "a_partir_de": False}}


def test_le_prix_lu_passe_la_barriere_et_rien_n_est_ajoute_a_la_phrase():
    fiche, p = {PA.CLE_DU_TOUR: 1}, {"lignes": [{"ref": "a", "quantite": 1}]}
    PA.admettre_les_valeurs(fiche, PRIX_LU)
    etat = PA.etat_du_tour(fiche)
    assert not chiffre_dans_la_phrase("Le tacos coûte huit euros.", faits=etat.faits_du_refus)
    assert chiffre_dans_la_phrase("Le tacos coûte neuf euros.", faits=etat.faits_du_refus)
    d = PA.parole_du_tour({"statut": "FAIT"}, "C'est noté.", etat, [], p)
    assert d.mode == PA.A_DIRE_SEUL and d.a_dire == "C'est noté."  # le code n'ajoute plus le prix


def test_le_prix_lu_ne_tient_que_pour_le_tour():
    fiche = {PA.CLE_DU_TOUR: 1}
    PA.admettre_les_valeurs(fiche, PRIX_LU)
    fiche[PA.CLE_DU_TOUR] = 2  # la personne reparle
    assert chiffre_dans_la_phrase("Le tacos coûte huit euros.", faits=PA.etat_du_tour(fiche).faits_du_refus)


def test_poser_le_prix_lu_ne_change_pas_le_verdict_la_commande_a_t_elle_change():
    fiche, p = {PA.CLE_DU_TOUR: 1}, {"lignes": [{"ref": "a", "quantite": 1}]}
    avant = ce_qui_se_voit(p)
    PA.admettre_les_valeurs(fiche, PRIX_LU)
    assert ce_qui_se_voit(p) == avant
