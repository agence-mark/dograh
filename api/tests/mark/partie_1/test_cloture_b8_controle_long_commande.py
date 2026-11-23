"""[.mark] Clôture de la Partie 1, correctifs du contrôle long (23/11), agent « commande », lot 3 : les familles RC1, RC9, M9, RC6, RC7 et les restes de RC4 et RC10.

Chaque cas est une suite que le test des combinaisons a vue rouge (état, gestes), rejouée par le MÊME juge (``combinaisons.jouer``, règles RC1 à RC15 inchangées) :
elle doit rendre zéro faute. Aucune règle n'est assouplie ; un cas est ajouté par défaut trouvé, jamais retiré.
"""

from __future__ import annotations

import pytest

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
    "rc4_fiche_rejouee_deux_fois_e16": ("E16", ("G31", "G31")),
    "rc4_fiche_rejouee_deux_fois_e10": ("E10", ("G31", "G31")),
    "rc4_mode_puis_fiche_rejouee_e18": ("E18", ("G15", "G31")),
    "rc4_fiche_vide_puis_rejouee_e18": ("E18", ("G30", "G31")),
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
