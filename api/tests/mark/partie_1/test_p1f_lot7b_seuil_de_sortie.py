"""[.mark] Lot 7b, M6 : le nombre de fois avant la sortie (« je peux laisser un message à l'équipe ») est un réglage du restaurant, ``commande_fois_avant_la_sortie``.

Sans réglage : la commande garde 3, la réservation garde 2 pour le choix non compris et la recherche sans résultat (E28), 3 pour la boucle. Réglé : le même nombre partout.
"""

from __future__ import annotations

from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes.seuil_de_sortie import CLE_FOIS_AVANT_LA_SORTIE, CLE_RESERVATION, seuil_de_sortie
from api.tests.mark.partie_1.porte_essai_reservation import choix_non_compris
from api.tests.mark import test_restauration_reservation as _RESA

salle = _RESA.salle  # la fixture de la salle, reprise sans import inutile


def test_le_schema_expose_une_valeur_par_defaut_par_metier():
    """Reprise 3 de l'audit : une clé par métier, sa valeur par défaut dans le schéma (le formulaire la lit là), aucune constante cachée dans le code."""
    from api.schemas.workflow_configurations import WorkflowConfigurationDefaults as W

    assert W.model_fields[CLE_FOIS_AVANT_LA_SORTIE].default == 3
    assert W.model_fields[CLE_RESERVATION].default == 2
    assert CLE_FOIS_AVANT_LA_SORTIE != CLE_RESERVATION


def test_le_reglage_se_lit_par_metier_avec_le_defaut_du_schema_et_ignore_ce_qui_est_faux():
    assert seuil_de_sortie({}, CLE_FOIS_AVANT_LA_SORTIE, 3) == 3 and seuil_de_sortie(None, CLE_RESERVATION, 2) == 2
    assert seuil_de_sortie({CLE_RESERVATION: None}, CLE_RESERVATION, 2) == 2  # champ non réglé : la valeur par défaut du schéma
    assert seuil_de_sortie({CLE_RESERVATION: 4}, CLE_RESERVATION, 2) == 4
    assert seuil_de_sortie({CLE_FOIS_AVANT_LA_SORTIE: 4}, CLE_RESERVATION, 2) == 2  # mettre la commande à 4 ne change pas la réservation
    assert seuil_de_sortie({CLE_RESERVATION: 4}, CLE_FOIS_AVANT_LA_SORTIE, 3) == 3  # et inversement
    for faux in (1, 9, "3", True, 2.5):
        assert seuil_de_sortie({CLE_FOIS_AVANT_LA_SORTIE: faux}, CLE_FOIS_AVANT_LA_SORTIE, 3) == 3, faux


def test_le_journal_lit_le_seuil_qu_on_lui_donne():
    dossier: dict = {}
    assert [J.fait_redit(dossier, "x", t, 3) for t in (1, 2, 3)] == [J.PREMIERE, J.ISSUE, J.SORTIE]
    dossier = {}
    assert [J.fait_redit(dossier, "x", t, seuil=2) for t in (1, 2)] == [J.PREMIERE, J.SORTIE]
    dossier = {}
    assert [J.boucle(dossier, ["a"], True, seuil=2) for _ in range(2)] == [False, True]
    dossier = {}
    assert [J.boucle(dossier, ["a"], True, 3) for _ in range(3)] == [False, False, True]


async def test_commande_au_seuil_regle_a_deux_la_sortie_vient_au_second_refus(essai_de):
    """Client « un zzzquoi » deux fois de suite : sans réglage, l'issue au 2e refus ; réglé à 2, la sortie (message à l'équipe) dès le 2e."""
    e = await essai_de()
    e.ctx.configurations = {CLE_FOIS_AVANT_LA_SORTIE: 2}
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("un zzzquoi", ajouter=[{"article": "zzzquoi", "quantite": 1}])
    r2 = await e.tour("un zzzquoi encore", ajouter=[{"article": "zzzquoi", "quantite": 1}])
    assert J.A_FAIRE_SORTIE in r2["a_faire"], r2["a_faire"]


async def test_commande_sans_reglage_garde_l_issue_au_second_refus(essai_de):
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("un zzzquoi", ajouter=[{"article": "zzzquoi", "quantite": 1}])
    r2 = await e.tour("un zzzquoi encore", ajouter=[{"article": "zzzquoi", "quantite": 1}])
    assert J.A_FAIRE_ISSUE in r2["a_faire"] and J.A_FAIRE_SORTIE not in r2["a_faire"], r2["a_faire"]


async def test_reservation_sans_reglage_le_choix_non_compris_s_arrete_au_second(salle, monkeypatch):
    retours = await choix_non_compris(salle, monkeypatch, {})
    assert len(retours) == 2 and retours[-1]["raison"] == "choix_non_compris_deux_fois", retours


async def test_reservation_reglee_a_trois_pose_une_question_de_plus(salle, monkeypatch):
    retours = await choix_non_compris(salle, monkeypatch, {CLE_RESERVATION: 3})
    assert len(retours) == 3 and retours[-1]["raison"] == "choix_non_compris_deux_fois", retours


async def test_reservation_ne_lit_pas_la_cle_de_la_commande(salle, monkeypatch):
    """Mettre la commande à 4 ne change rien à la réservation : le choix non compris s'arrête toujours au second."""
    retours = await choix_non_compris(salle, monkeypatch, {CLE_FOIS_AVANT_LA_SORTIE: 4})
    assert len(retours) == 2 and retours[-1]["raison"] == "choix_non_compris_deux_fois", retours
