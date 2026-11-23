"""[.mark] Plan final Partie 1, lot 1 : l'inventaire des rustines. Le compte ne monte jamais (``outils/base_inventaire.json``).

Compte, par fichier : les drapeaux de la liste fermée, les erreurs avalées sans journal, les noms privés importés d'un autre paquet, la lecture de
mots dans le moteur, les fonctions de plus de 80 lignes. Un compte qui monte, une fonction longue nouvelle ou qui grossit : rouge. Les mécanismes
des lots 2 à 9 font baisser ces comptes ; le coordinateur fige la base plus bas (``garde_de_lot.py --figer``), jamais plus haut.
"""

from __future__ import annotations

from api.outils import inventaire_rustines as I

BASE = I.charger(I.RACINE_API / "outils" / "base_inventaire.json")
PERIMETRE = I.charger(I.RACINE_API / "outils" / "perimetre_partie_1.json")


def test_aucun_compte_de_rustine_ne_monte():
    ecarts = I.comparer(I.inventaire(), BASE, PERIMETRE)
    assert not ecarts, "\n".join(ecarts)


def test_le_perimetre_nomme_des_fichiers_et_des_fonctions_qui_existent():
    fonctions = {}
    for chemin in PERIMETRE["fonctions"]:
        assert (I.RACINE_API / chemin).exists(), chemin
        fonctions[chemin] = set(I.fonctions_du_fichier((I.RACINE_API / chemin).read_text(encoding="utf-8")))
    absentes = [f"{c}::{f}" for c, noms in PERIMETRE["fonctions"].items() for f in noms if f not in fonctions[c]]
    assert not absentes, absentes[:20]


def test_les_deux_grandes_fonctions_ne_grossissent_pas_et_visent_leur_longueur_d_avant():
    """R2 : ``run_pipeline`` et le tour au clavier reviennent à leur longueur d'avant la Partie 1 (lot 8) ; d'ici là, ils ne grossissent pas."""
    for cle, ligne in PERIMETRE["longueurs_d_avant"].items():
        longueurs = I.fonctions_du_fichier((I.RACINE_API / ligne["fichier"]).read_text(encoding="utf-8"))
        assert longueurs[ligne["fonction"]] <= ligne["a_la_base"], f"{cle} grossit : {longueurs[ligne['fonction']]} > {ligne['a_la_base']}"
        assert ligne["avant"] and ligne["avant"] < ligne["a_la_base"], cle
