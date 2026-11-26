"""[.mark] Lot 8, T17 : un prix dit sans virgule (« vingt-quatre euros cinquante ») se lit 24,50 EUR (2450 centimes), comme « 24,50 € ». Un nombre dit juste après l'unité
d'argent compte comme les centimes ; il ne s'additionne plus aux euros (avant : 74). Décision de Pierre (``decisions-du-coordinateur.md:111``) : corrigé dans les deux sens,
un test pour chaque sens, avant les vrais clients. Règle de VALEUR, la même lecture pour « elle l'a dit » et la barrière (``forme.valeurs``)."""

from __future__ import annotations

from api.services.actions_communes import forme
from api.services.actions_communes.barriere_des_chiffres import chiffre_dans_la_phrase, porte_les_chiffres
from api.services.actions_communes.barrieres import valeur_pas_dans_ses_mots


# --------------------------------------------------------------------------- les deux sens de la décision

def test_sens_1_un_prix_bien_dit_est_accepte():
    """Avant : « vingt-quatre euros cinquante » se lisait 74, rejeté face à 24,50 €."""
    assert porte_les_chiffres("vingt-quatre euros cinquante", {"total": "24,50 €"})
    assert porte_les_chiffres("Cela fait vingt-quatre euros cinquante.", {"total": "24,50 €"})
    assert not chiffre_dans_la_phrase("Cela fait vingt-quatre euros cinquante.", faits=[{"total": "24,50 €"}])


def test_sens_2_un_prix_faux_est_refuse():
    """Avant : « vingt, cinquante-quatre euros » se lisait 74 sans la virgule et passait face à 24,50 €."""
    assert not porte_les_chiffres("vingt, cinquante-quatre euros", {"total": "vingt-quatre euros cinquante"})
    assert not porte_les_chiffres("vingt, cinquante-quatre euros", {"total": "24,50 €"})
    assert chiffre_dans_la_phrase("Cela fait vingt, cinquante-quatre euros.", faits=[{"total": "24,50 €"}])


# --------------------------------------------------------------------------- la lecture

def test_la_lecture_des_prix_dits():
    assert forme.valeurs("vingt-quatre euros cinquante") == [("2450", "argent")]
    assert forme.valeurs("24,50 €") == [("2450", "argent")]
    assert forme.valeurs("cent vingt euros cinquante") == [("12050", "argent")]
    assert forme.valeurs("vingt euros trente centimes") == [("2030", "argent")]
    assert forme.valeurs("vingt-quatre euros") == [("24", "argent")]
    assert forme.valeurs("un billet de vingt") == [("20", "argent")]
    assert forme.valeurs("25 en titres") == [("25", "argent")]
    assert forme.valeurs("vingt, cinquante-quatre euros") == [("20", "nombre"), ("54", "argent")]


def test_voisins_inchanges():
    assert porte_les_chiffres("Cela fait vingt-quatre euros.", {"total": "vingt-quatre euros"})
    assert not porte_les_chiffres("Cela fait vingt-quatre euros cinquante.", {"total": "vingt-quatre euros"})
    assert porte_les_chiffres("Cela fait cent vingt euros cinquante.", {"total": "120,50 €"})
    assert porte_les_chiffres("Cela fait 24,50 €.", {"total": "vingt-quatre euros cinquante"})
    assert porte_les_chiffres("Un billet de vingt.", {"rendu": "un billet de vingt euros"})
    assert not chiffre_dans_la_phrase("Je note 25 en titres.", paroles=["vingt-cinq en titres restaurant"])


# --------------------------------------------------------------------------- les autres lecteurs de forme (refus 15)

def test_lecteur_barriere_de_la_parole_elle_l_a_dit_en_argent():
    """``forme.valeur_dite_par_elle`` (case « argent »), lue par la barrière des chiffres : le billet dit est reconnu, un autre non."""
    assert forme.valeur_dite_par_elle(50, "rendu_sur", ["un billet de cinquante euros"])
    assert forme.valeur_dite_par_elle(20, "rendu_sur", ["je paie avec un billet de vingt"])
    assert not forme.valeur_dite_par_elle(50, "rendu_sur", ["un billet de vingt euros"])
    assert not forme.valeur_dite_par_elle(24, "rendu_sur", ["vingt euros cinquante-quatre"])


def test_lecteur_heure_et_nombre_de_personnes():
    assert forme.valeur_dite_par_elle(4, "nombre", ["pour quatre personnes"])
    assert forme.valeur_dite_par_elle(20, "nombre", ["vers vingt heures trente"])
    assert forme.valeurs("vingt heures trente") == [("20", "nombre"), ("30", "nombre")]
    assert porte_les_chiffres("Pour quatre personnes, vingt heures trente.", {"personnes": "4", "heure": "vingt heures trente"})
    assert not porte_les_chiffres("Pour quatre personnes, vingt heures.", {"personnes": "4", "heure": "vingt heures trente"})


def test_lecteur_numero_de_telephone_de_la_commande():
    """``commande/porte.py`` (retrouver une commande) : un numéro dit en paires est reconnu, un autre non."""
    assert forme.valeur_dite_par_elle("0612345678", "telephone", ["zéro six, douze, trente-quatre, cinquante-six, soixante-dix-huit"])
    assert not forme.valeur_dite_par_elle("0612345679", "telephone", ["zéro six, douze, trente-quatre, cinquante-six, soixante-dix-huit"])


def test_lecteur_poids_de_la_commande():
    """``produit_au_poids`` lit par ``forme.lire_un_nombre`` : intact."""
    from api.services.commande.briques.produit_au_poids import lire_poids

    assert forme.lire_un_nombre(["trois", "cents"]) == 300
    assert forme.lire_un_nombre(["vingt", "quatre"]) == 24
    assert lire_poids("trois cents grammes") == 300
    assert lire_poids("un kilo deux cents") == 1200


def test_lecteur_connecteurs_valeur_pas_dans_ses_mots():
    """``barrieres.valeur_pas_dans_ses_mots`` (airtable, google_sheets, via ``connectors/execution.py``) : une valeur libre dite passe, inventée est refusée."""
    assert valeur_pas_dans_ses_mots({"rendu_sur": 50}, ["un billet de cinquante euros"]) is None
    assert valeur_pas_dans_ses_mots({"telephone": "0612345678"}, ["zéro six douze trente-quatre cinquante-six soixante-dix-huit"]) is None
    assert valeur_pas_dans_ses_mots({"rendu_sur": 50}, ["un billet de vingt euros"])["raison"] == "valeur_pas_dans_ses_mots"


def test_voisin_un_seul_chiffre_apres_la_virgule_devant_un_euro_est_les_dixiemes():
    """« 24,5 € » est 24,50 € ; « 24,05 € » reste 24,05 ; hors argent rien ne change (« 1,5 kg »)."""
    assert forme.valeurs("24,5 €") == [("2450", "argent")]
    assert forme.valeurs("24,05 €") == [("2405", "argent")]
    # INCHANGÉ, FAUX : « 1,5 kg » devrait se lire 1,5 ; cette lecture (105) est celle d'avant T17, au registre T22, pas une attente voulue
    assert forme.valeurs("1,5 kg") == [("105", "nombre")]
    assert porte_les_chiffres("Cela fait vingt-quatre euros cinquante.", {"total": "24,5 €"})


# --------------------------------------------------------------------------- reprise R1 : toutes les virgules des centimes, et seulement elles

def test_deux_prix_dits_avec_virgule_ne_se_lisent_pas_comme_un_seul():
    """« douze, cinquante » puis « dix, cinquante » : chaque virgule suivie d'un nombre et d'une unité d'argent est celle de ses centimes ; la phrase donne 12,50 € et 10,50 €, pas 12,50 € puis 60 (sens 1 recréé)."""
    assert not chiffre_dans_la_phrase("La Regina est à douze, cinquante euros et la Margherita à dix, cinquante euros.", faits=[{"prix": [1250, 1050]}])
    assert chiffre_dans_la_phrase("La Regina est à douze, cinquante euros et la Margherita à dix, soixante euros.", faits=[{"prix": [1250, 1050]}])


def test_un_point_entre_deux_nombres_les_separe_toujours():
    """Le point de fin de phrase ne colle pas deux nombres : « quatre. Vingt-quatre, cinquante euros » = 4 puis 24,50 € (jamais 8450)."""
    assert not chiffre_dans_la_phrase("Vous êtes quatre. Vingt-quatre, cinquante euros.", faits=[{"personnes": 4, "total": 2450}])
