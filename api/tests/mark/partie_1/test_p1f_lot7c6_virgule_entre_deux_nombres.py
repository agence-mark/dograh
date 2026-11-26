"""[.mark] Lot 7b-C6, défaut de la virgule (compte rendu de la réservation, risque 1) : deux nombres séparés par une virgule sont deux valeurs. « Pour quatre, vingt heures »
se lisait 80 (la virgule effacée collait « quatre » et « vingt ») : la barrière refusait une bonne relecture de la réservation et relançait le modèle pour rien. Règle de VALEUR, la même
lecture pour « elle l'a dit » et la barrière (``forme.valeurs``) ; les nombres dits d'un seul tenant (« quatre-vingts », « vingt et un ») ne bougent pas."""

from __future__ import annotations

from api.services.actions_communes import forme
from api.services.actions_communes.barriere_des_chiffres import chiffre_dans_la_phrase, porte_les_chiffres


def test_une_virgule_separe_deux_nombres():
    assert forme.valeurs("Samedi pour quatre, vingt heures.") == [("4", "nombre"), ("20", "nombre")]


def test_un_point_separe_aussi_deux_phrases():
    assert forme.valeurs("On sera quatre. Vingt heures, c'est bien ?") == [("4", "nombre"), ("20", "nombre")]


def test_la_barriere_accepte_la_relecture_qui_dit_les_personnes_puis_l_heure_apres_une_virgule():
    assert porte_les_chiffres("Pour quatre, vingt heures samedi, au nom de Paul.", {"personnes": "4", "heure": "vingt heures"})


def test_les_nombres_dits_d_un_seul_tenant_ne_bougent_pas():
    assert forme.valeurs("quatre-vingts") == [("80", "nombre")]
    assert forme.valeurs("quatre vingt dix") == [("90", "nombre")]
    assert forme.valeurs("vingt et un") == [("21", "nombre")]
    assert forme.valeurs("12,50 €") == [("1250", "argent")]
    assert porte_les_chiffres("Pour quatre-vingts, vingt heures.", {"personnes": "80", "heure": "vingt heures"})


# Reprise R3 de l'audit réservation-prix : la virgule n'ouvre pas de trou dans la barrière. Deux nombres que seule une virgule sépare restent « collés » pour la règle P1
# (« douze, cinquante » est un prix ou une heure dite à la française, retenu comme « douze cinquante ») ; et une valeur dite avec ou sans virgule est la même valeur (lecture
# d'avant la virgule admise aussi), pour ne pas relancer le modèle pour rien.
# Avant : modèle « La Regina est à douze, cinquante. » part au client (un prix sans « euros » inventé). Après : retenue, le modèle repasse.

def test_deux_nombres_que_seule_une_virgule_separe_sont_retenus_comme_un_prix_ou_une_heure():
    for phrase in ("La Regina est à douze, cinquante.", "Ce sera prêt à dix-neuf, trente.", "Ça fera vingt-quatre, cinquante."):
        assert chiffre_dans_la_phrase(phrase), phrase


def test_voisin_la_relecture_de_la_reservation_avec_sa_virgule_passe_toujours():
    faits = {"personnes": "4", "heure": "vingt heures"}
    phrase = "Pour quatre, vingt heures samedi, au nom de Paul."
    assert porte_les_chiffres(phrase, faits) and not chiffre_dans_la_phrase(phrase, faits=[faits])


def test_voisins_inchanges():
    for phrase in ("12,50 €", "2,30 €", "1,5 kg", "trois cents grammes, cinq euros quarante", "dix-neuf heures trente", "19h30"):
        assert chiffre_dans_la_phrase(phrase), phrase
    assert not chiffre_dans_la_phrase("quatre-vingts")
    assert not chiffre_dans_la_phrase("Trois cents grammes, cinq euros quarante.", faits=[{"prix_au_poids": [{"grammes": 300, "prix": 540}]}])


def test_le_numero_dit_sans_virgules_est_le_numero_du_fait_avec_virgules():
    fait = {"numero": "zéro six, dix, vingt, trente, quarante"}
    phrase = "Je note le zéro six dix vingt trente quarante, c'est bon ?"
    assert not chiffre_dans_la_phrase(phrase, faits=[fait]) and porte_les_chiffres(phrase, fait)


def test_un_montant_dit_avec_une_virgule_est_le_montant_du_fait():
    assert not chiffre_dans_la_phrase("Ça fait vingt-quatre, cinquante euros.", faits=[{"total": 2450}])
    assert chiffre_dans_la_phrase("Ça fait vingt-quatre, cinquante euros.", faits=[{"total": 2460}])
