"""Lot 20 (porte du chantier, appels 455 et 460) : restaurant fermé, panier vide, et l'agent disait « Merci Camille, votre commande est bien enregistrée » :
la fiche (le prénom) n'avait rien refusé, sa phrase était dite seule. La règle « c'est fait » de la vérité des actions (SA-18) s'applique aussi sur
l'étape qui porte la fiche, comparée à l'ÉTAT de la commande : une phrase qui annonce l'enregistrement (ou l'annulation) d'une commande qui ne l'est pas
n'est jamais dite."""

from api.services.actions_communes import parole as PA
from api.services.workflow import parole_de_la_fiche as PF

PANIER_VIDE = {"lignes": [], "mode": None, "enregistree": None, "annulee": False}


def test_l_annonce_d_un_enregistrement_qui_n_a_pas_eu_lieu_est_retenue():
    assert PF.annonce_non_fondee("Merci Camille, votre commande est bien enregistrée. Puis-je faire autre chose ?", PANIER_VIDE)
    assert PF.annonce_non_fondee("C'est annulé.", PANIER_VIDE)


def test_une_annonce_fondee_ou_une_question_passe():
    assert not PF.annonce_non_fondee("Votre commande est enregistrée.", {**PANIER_VIDE, "enregistree": {"numero": "A1"}})
    assert not PF.annonce_non_fondee("Je l'enregistre maintenant ?", PANIER_VIDE)
    assert not PF.annonce_non_fondee("C'est noté pour Camille.", PANIER_VIDE)
    assert not PF.annonce_non_fondee("Votre table est réservée.", {"reservations": []})  # un dossier sans « enregistree » n'est pas jugé ici


def test_la_fiche_qui_annonce_l_enregistrement_a_tort_repasse():
    fiche = {PA.CLE_DU_TOUR: 7, "commande_panier": PANIER_VIDE}
    d = PF.decider_apres_la_fiche(fiche, {"statut": "FAIT", "resultats": []}, {"a_dire": "Merci Camille, votre commande est bien enregistrée.", "prenom": "Camille"})
    assert d.mode == PA.SECOND_PASSAGE and d.motif == PF.ANNONCE_NON_FONDEE
