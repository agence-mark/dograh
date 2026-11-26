"""[.mark] Clôture de la Partie 1, correctifs du contrôle long (23/11), agent « commande », lot 3 : les familles RC1, RC9, M9, RC6, RC7 et les restes de RC4 et RC10.

Chaque cas est une suite que le test des combinaisons a vue rouge (état, gestes), rejouée par le MÊME juge (``combinaisons.jouer``, règles RC1 à RC15 inchangées) :
elle doit rendre zéro faute. Aucune règle n'est assouplie ; un cas est ajouté par défaut trouvé, jamais retiré.

T12 (26/11) : trois cas de RC4 (la même fiche rejouée dans le tour sur une commande enregistrée) attendaient que le code redise le fait accompli après
« C'est noté. » (``table_de_parole._rien_change`` : « RC4 : le fait accompli, que le code redit (§ 2 du plan, jusqu'à C6) »). La reprise R1 de C6
(``1d50af71`` ; décisions d'Evan 25/11 8 h 45 et 9 h 30, P3 ; coordinateur 26/11 2 h 05) l'a retiré : le code ne dit jamais le fait accompli, le modèle
parle, une seule relance par tour. Ils ne sont pas retirés : ``test_la_fiche_qui_ne_change_rien_relance_une_fois_puis_le_modele_parle`` les rejoue au
comportement décidé, toutes les autres règles à zéro faute.
"""

from __future__ import annotations

import pytest

from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes.du import RIEN_CHANGE
from api.tests.mark.partie_1 import combinaisons as C

CAS = {
    # RC1 : « annulez ma commande » (ou un détour) + un changement sur une commande enregistrée : une seule question dans le tour
    "rc1_annuler_et_ajouter": ("E16", ("G1+G22",)),
    "rc1_annuler_et_adresse": ("E16", ("G16+G22",)),
    "rc1_annuler_et_heure": ("E16", ("G18+G22",)),
    "rc1_annuler_et_heure_e18": ("E18", ("G18+G22",)),
    "rc1_annuler_et_mode_e18": ("E18", ("G16+G22",)),
    "rc1_doute_ouvert_puis_changement": ("E16", ("G4", "G8")),
    # RC4 : reste, vider + ajouter sur une commande enregistrée
    "rc4_ajouter_et_vider_enregistree": ("E16", ("G6+G12",)),
    "rc4_fiche_rejouee_deux_fois_e10": ("E10", ("G31", "G31")),
    "rc1_vider_puis_ajouter_e18": ("E18", ("G12", "G1")),
    # RC9 : la même question reposée garde son numéro
    "rc9_hesitation_redite_avec_non": ("E6", ("G4+G24",)),
    # M9 : aucune valeur nulle là où le retour donne un prix
    "m9_retirer_et_oui_en_livraison": ("E10", ("G7+G23",)),
    "m9_remplacer_et_oui_en_livraison": ("E10", ("G11+G23",)),
    # RC6 : trois fois la même chose sans sortie
    "rc6_annulee_trois_fois": ("E17", ("G18", "G32", "G4", "G12")),
    "rc6_relecture_trois_fois": ("E14", ("G18", "G26", "G24")),
    "rc6_taille_trois_fois": ("E5", ("G16", "G15", "G34")),
    "rc6_doute_trois_fois": ("E10", ("G4", "G16", "G23")),
    "rc6_numero_trois_fois": ("E14", ("G30", "G3", "G25")),
    # RC7 : « pardon ? » après une commande finie
    "rc7_pardon_apres_annulation": ("E11", ("G13+G7", "G21", "G24", "G35")),
    "rc7_pardon_apres_annulation_2": ("E12", ("G11+G13", "G12", "G2+G28", "G8", "G28", "G35")),
    # Restes des 2 000 suites tirées (graine 20261122), réduits par le test lui-même
    "tirees_rc9_taille_autre_ligne": ("E5", ("G2", "G9")),
    "tirees_rc6_doute_taille_doute": ("E10", ("G4", "G9", "G18")),
    "tirees_rc6_relecture_fiche_mal_formee": ("E15", ("G9+G20", "G34", "G34")),
    "tirees_rc4_vider_enregistree_puis_oui_et_ajout": ("E18", ("G12", "G2+G23")),
    "tirees_rc2_rc8_vider_ajouter_enregistree_puis_retirer": ("E18", ("G12+G2", "G7")),
    "tirees_rc2_rc8_oui_nouvelle_commande": ("E7", ("G14+G21", "G33", "G1+G23")),
    "tirees_rc2_rc8_oui_nouvelle_commande_e17": ("E17", ("G2", "G5+G23")),
    "tirees_rc2_adresse_horszone_oui": ("E17", ("G19", "G23+G17")),
    # RC10 : relecture marquée faite sans être dite (changement d'heure après l'accord, un article en doute ouvert)
    "rc10_heure_apres_accord_avec_un_doute": ("E13", ("G4", "G18")),
}


@pytest.mark.parametrize("nom", list(CAS))
async def test_le_juge_ne_voit_plus_la_faute(faire_monde, monkeypatch, nom):
    etat, suite = CAS[nom]
    monde = await faire_monde("casa-italia")
    res = await C.jouer(monde, monkeypatch, etat, suite)
    assert res.atteint, f"{etat} non atteint"
    assert not res.fautes, "\n".join(f"[{g}] {r} : {d}" for g, r, d in res.fautes)


# T12 : la commande est enregistrée, rien n'est dû ; le modèle joue deux fois dans le tour une fiche qui ne change rien
CAS_APRES_LA_RELANCE = {
    "rc4_fiche_rejouee_deux_fois_e16": ("E16", ("G31", "G31")),
    "rc4_mode_puis_fiche_rejouee_e18": ("E18", ("G15", "G31")),
    "rc4_fiche_vide_puis_rejouee_e18": ("E18", ("G30", "G31")),
}
# la faute que RC4 voit sur la phrase du modèle dite après la relance du tour : le code n'a plus rien à y ajouter (reprise R1 de C6)
ANNONCE_APRES_LA_RELANCE = ("RC4", "rien n'a changé et la phrase du modèle (« C'est noté. », écrite avant l'exécution) est dite seule")


@pytest.mark.parametrize("nom", list(CAS_APRES_LA_RELANCE))
async def test_la_fiche_qui_ne_change_rien_relance_une_fois_puis_le_modele_parle(faire_monde, monkeypatch, nom):
    """Client « D'accord. » (commande enregistrée) ; la fiche du modèle ne change rien : sa phrase n'est pas dite, il repasse (la relance du tour) ; il rejoue
    la même fiche : sa phrase part seule, le code n'y ajoute rien (ni fait accompli, ni phrase composée). Décisions d'Evan 25/11 8 h 45 (le modèle parle,
    une relance par tour) et 9 h 30 (P3 ; au code seulement total, numéro, rendu, M108) ; reprise R1 de C6 (coordinateur 26/11 2 h 05).
    Avant R1 : « C'est noté. » suivi du fait accompli redit par le code ; après : « C'est noté. », la phrase du modèle. Toutes les autres règles : zéro faute."""
    etat, suite = CAS_APRES_LA_RELANCE[nom]
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette(etat), f"{etat} non atteint"
    vues, fautes = [], []
    for pas in suite:
        o = await partie.geste(pas)
        assert o is not None, f"{pas} sans objet dans {etat}"
        vues.append(o)
        fautes += [(pas, regle, detail) for regle, detail in C.juger(partie, o)]
    premiere, seconde = vues
    assert C.lignes_de(premiere.avant) == C.lignes_de(seconde.apres), "la fiche a changé le panier"
    assert premiere.avant.get("enregistree") == seconde.apres.get("enregistree"), "la fiche a changé la commande enregistrée"
    assert (premiere.decision.mode, premiere.decision.motif) == (PAROLE.SECOND_PASSAGE, RIEN_CHANGE), premiere.decision  # jamais dite : la relance du tour
    assert seconde.decision.mode == PAROLE.A_DIRE_SEUL and seconde.decision.a_dire == C.ANNONCE, seconde.decision  # la phrase du modèle, seule
    assert not seconde.dit_par_le_code and not (seconde.textes or {}).get("fait_accompli"), seconde.textes  # le code ne dit rien, aucun fait accompli
    assert [f for f in fautes if f != (suite[-1], *ANNONCE_APRES_LA_RELANCE)] == [], "\n".join(f"[{g}] {r} : {d}" for g, r, d in fautes)
