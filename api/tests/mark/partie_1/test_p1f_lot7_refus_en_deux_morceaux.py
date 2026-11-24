"""[.mark] Lot 7a, ligne 69 : un refus range sa consigne en deux morceaux (« rien n'est changé » + le reste), le refus partiel reconstruit son texte depuis le reste, plus de
``removeprefix`` sur le texte. Le texte que le modèle lit ne change pas d'un caractère ; le refus que le modèle voit n'a aucune clé de plus."""

from __future__ import annotations

import json

from api.services.actions_communes import barrieres as B


def test_le_refus_garde_sa_consigne_entiere_et_aucune_cle_de_plus():
    r = B.refus("valeur_hors_liste", ["taille"], choix=["petite", "grande"])
    assert r["a_faire"] == "rien n'est changé : refais la fiche sans taille"
    assert set(r) == {"raison", "cases", "a_faire", "choix"}
    assert json.loads(json.dumps(r)) == dict(r)
    pour = B.refus("recapitulatif_pas_accepte", ["a", "b"], reste="a, b : elles se prennent après son accord", pour=True)
    assert pour["a_faire"] == "rien n'est changé pour a, b : elles se prennent après son accord"
    assert set(pour) == {"raison", "cases", "a_faire"}


def test_refus_partiel_texte_identique_au_caractere_pres():
    defaut = B.refus("valeur_hors_liste", ["taille"], choix=["x"])
    assert B.a_faire_du_refus_partiel(defaut, ["ajouter"]) == "taille refusé : refais la fiche sans taille ; le reste de la fiche est déjà fait (ajouter)"
    pour = B.refus("recapitulatif_pas_accepte", ["adresse"], reste="adresse : elles se prennent après son accord", pour=True)
    assert B.a_faire_du_refus_partiel(pour, ["ajouter"]) == "adresse refusé : adresse : elles se prennent après son accord ; le reste de la fiche est déjà fait (ajouter)"
    libre = B.refus("case_sans_objet", ["x"], a_faire="pas ouvert maintenant, rien n'en est pris")
    assert B.a_faire_du_refus_partiel(libre, ["ajouter"]) == "x refusé : pas ouvert maintenant, rien n'en est pris ; le reste de la fiche est déjà fait (ajouter)"


def test_refus_entier_ou_rien_d_autre_d_execute_garde_son_texte():
    r = B.refus("valeur_hors_liste", ["taille"])
    assert B.a_faire_du_refus_partiel(r, []) == "rien n'est changé : refais la fiche sans taille"
    assert B.a_faire_du_refus_partiel(B.refus("format_illisible", ["*"], reste="la fiche est un objet avec ses cases"), ["ajouter"]) \
        == "rien n'est changé : la fiche est un objet avec ses cases"


def test_une_consigne_ecrite_a_la_main_sans_le_debut_ne_perd_rien():
    sans_debut = {"raison": "x", "cases": ["c"], "a_faire": "refais autrement"}
    assert B.a_faire_du_refus_partiel(sans_debut, ["ajouter"]) == "c refusé : refais autrement ; le reste de la fiche est déjà fait (ajouter)"
