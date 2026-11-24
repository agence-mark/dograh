"""[.mark] Lot 7b, M6 : le nombre de fois avant la sortie (« je peux laisser un message à l'équipe ») est un réglage du restaurant, ``commande_fois_avant_la_sortie``.

Sans réglage : la commande garde 3, la réservation garde 2 pour le choix non compris et la recherche sans résultat (E28), 3 pour la boucle. Réglé : le même nombre partout.
"""

from __future__ import annotations

from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes.seuil_de_sortie import CLE_FOIS_AVANT_LA_SORTIE, seuil_de_sortie
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation
from api.tests.mark.test_restauration_reservation import SAMEDI_20H, salle  # noqa: F401


def test_le_reglage_se_lit_avec_le_defaut_du_metier_et_ignore_ce_qui_est_faux():
    assert seuil_de_sortie({}, 3) == 3 and seuil_de_sortie(None, 2) == 2
    assert seuil_de_sortie({CLE_FOIS_AVANT_LA_SORTIE: None}, 2) == 2  # champ non réglé : la valeur du métier
    assert seuil_de_sortie({CLE_FOIS_AVANT_LA_SORTIE: 4}, 2) == 4
    for faux in (1, 9, "3", True, 2.5):
        assert seuil_de_sortie({CLE_FOIS_AVANT_LA_SORTIE: faux}, 3) == 3, faux


def test_le_journal_lit_le_seuil_qu_on_lui_donne_et_garde_trois_par_defaut():
    dossier: dict = {}
    assert [J.fait_redit(dossier, "x", t) for t in (1, 2, 3)] == [J.PREMIERE, J.ISSUE, J.SORTIE]
    dossier = {}
    assert [J.fait_redit(dossier, "x", t, seuil=2) for t in (1, 2)] == [J.PREMIERE, J.SORTIE]
    dossier = {}
    assert [J.boucle(dossier, ["a"], True, seuil=2) for _ in range(2)] == [False, True]
    dossier = {}
    assert [J.boucle(dossier, ["a"], True) for _ in range(3)] == [False, False, True]


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


async def _choix_non_compris_deux_fois(salle, monkeypatch, configurations):  # noqa: F811
    from api.db.bases_clients.restauration_reservation import creer_reservation
    from api.tests.mark.partie_1.porte_essai_reservation import TEL

    for numero, debut, personnes in (("a", SAMEDI_20H, 2), ("b", SAMEDI_20H.replace(day=15, hour=19), 3)):
        await creer_reservation(salle.c, salle.a, {"debut": debut, "couverts": personnes, "prenom": "Alice", "telephone": TEL, "appel_id": f"avant-{numero}"})
    essai = EssaiReservation(salle, monkeypatch)
    essai.ctx.configurations = configurations
    r = await essai.tour("annuler ma réservation", retrouver_une_reservation_enregistree={})
    retours = []
    for _ in range(3):
        r = await essai.tour("euh bleu", reponse={"question_id": (r.get("question") or {}).get("id", ""), "sens": "autre", "valeurs": ["bleu"]})
        retours.append(r)
        if "question" not in r:
            break
    return retours


async def test_reservation_sans_reglage_le_choix_non_compris_s_arrete_au_second(salle, monkeypatch):  # noqa: F811
    retours = await _choix_non_compris_deux_fois(salle, monkeypatch, {})
    assert len(retours) == 2 and retours[-1]["raison"] == "choix_non_compris_deux_fois", retours


async def test_reservation_reglee_a_trois_pose_une_question_de_plus(salle, monkeypatch):  # noqa: F811
    retours = await _choix_non_compris_deux_fois(salle, monkeypatch, {CLE_FOIS_AVANT_LA_SORTIE: 3})
    assert len(retours) == 3 and retours[-1]["raison"] == "choix_non_compris_deux_fois", retours
