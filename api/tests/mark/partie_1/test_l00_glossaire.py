"""[.mark] Chantier Partie 1, lot 0 : le glossaire et le contrôle des noms (L00-07, L00-19).

Étalons enregistrés (sans requête) depuis le banc B12 : ``donnees/noms_actuel.json`` (le contrat de production, captures 2678 et 2657,
greffier de production) doit être ROUGE ; ``donnees/noms_b12_300*.json`` (la version finale de B12, cartes 300 et 300b) doit être VERT.
"""

import json
from pathlib import Path

import pytest

from api.tests.mark.partie_1 import glossaire as GL
from api.tests.mark.partie_1.controle_noms import controler, inventaire_du_fork

ICI = Path(__file__).parent / "donnees"


def _vus(nom):
    return [tuple(v) for v in json.loads((ICI / f"{nom}.json").read_text(encoding="utf-8"))["vus"]]


def test_controle_rouge_sur_l_actuel():
    r1, r2, r3 = controler(_vus("noms_actuel"))
    assert r2, "le contrat actuel porte des doubles sens connus : le contrôle doit les trouver (R7)"
    assert any(x.startswith("type_de_commande") for x in r2), r2  # outil et champ du greffier à la fois
    assert len(r2) == 18 and r3, (len(r2), r2)  # constat du 19/11 sur l'export du fork : 18 doubles sens, des paires proches


@pytest.mark.parametrize("carte", ["300", "300b"])
def test_controle_vert_sur_le_propose(carte):
    assert controler(_vus(f"noms_b12_{carte}")) == ([], [], []), "l'étalon de B12 doit rester vert"


@pytest.mark.garde_noms
def test_noms_du_fork():
    """Le schéma réel du fork (commande et service, dans chaque état type de la version finale) respecte les trois règles : rouge jusqu'à la
    fin du lot 2 (registre, § 2)."""
    r1, r2, r3 = controler(inventaire_du_fork(("commande", "service")))
    assert (r1, r2, r3) == ([], [], []), f"manquent : {r1[:8]} ; deux sens : {r2[:5]} ; proches : {r3[:5]}"


@pytest.mark.garde_noms
def test_noms_de_la_reservation():
    """La réservation garde ses outils de production jusqu'au lot 7 (D18 : rien de ce qui marche n'est chamboulé avant son lot) : ses trois paires
    proches (« reservation ») restent rouges jusque-là ; le lot 7 la rend verte avec sa fiche."""
    r1, r2, r3 = controler(inventaire_du_fork(("reservation",)))
    assert (r1, r2, r3) == ([], [], []), f"manquent : {r1[:8]} ; deux sens : {r2[:5]} ; proches : {r3[:5]}"


def test_controle_par_etat_rouge_si_deux_annulations_visibles():
    """R7 : l'inventaire par état voit une paire proche dès qu'un état montre les deux annulations d'un même objet."""
    vus = [("cerveau commande", "x", "case", "annuler_la_commande", "fiche"), ("cerveau commande", "x", "case", "annuler_une_commande_enregistree", "fiche")]
    assert controler(vus)[2]
    vus = [("cerveau commande", "x", "case", "annuler_la_commande", "fiche"), ("cerveau commande", "y", "case", "annuler_une_commande_enregistree", "fiche")]
    assert controler(vus)[2] == []


def test_meme_mot_meme_sens_declare():
    # déclaré (D54) : « prenom » case de la fiche et champ du greffier, dans le même état
    assert "prenom" in GL.PARTAGES
    vus = [("cerveau commande", "x", "case", "prenom", "fiche"), ("cerveau commande", "x", "champ_greffier", "prenom", "")]
    assert controler(vus)[1] == []
    # non déclaré, ajouté exprès : refusé
    faux = dict(GL.GLOSSAIRE)
    faux["mot_partage_non_declare"] = (frozenset({"case"}), "Une case.")
    vus = [("cerveau commande", "x", "case", "mot_partage_non_declare", "fiche"),
           ("cerveau commande", "x", "champ_greffier", "mot_partage_non_declare", "")]
    assert controler(vus, faux)[1], "un mot partagé non déclaré doit être refusé"
    # un champ du greffier qui porte le nom d'un outil : toujours refusé
    vus = [("cerveau commande", "x", "outil", "fiche", ""), ("cerveau commande", "x", "champ_greffier", "fiche", "")]
    assert controler(vus)[1]
