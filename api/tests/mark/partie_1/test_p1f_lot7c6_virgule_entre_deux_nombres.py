"""[.mark] Lot 7b-C6, défaut de la virgule (compte rendu de la réservation, risque 1) : deux nombres séparés par une virgule sont deux valeurs. « Pour quatre, vingt heures »
se lisait 80 (la virgule effacée collait « quatre » et « vingt ») : la barrière refusait une bonne relecture de la réservation et relançait le modèle pour rien. Règle de VALEUR, la même
lecture pour « elle l'a dit » et la barrière (``forme.valeurs``) ; les nombres dits d'un seul tenant (« quatre-vingts », « vingt et un ») ne bougent pas."""

from __future__ import annotations

from api.services.actions_communes import forme
from api.services.actions_communes.barriere_des_chiffres import porte_les_chiffres


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
