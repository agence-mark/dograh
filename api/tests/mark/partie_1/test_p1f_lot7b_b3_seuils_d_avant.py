"""[.mark] Lot 7b-B, second passage : aux réglages par défaut, chaque compteur de sortie se comporte comme à ``e36536d89``.

Commande : la boucle et le refus redit sortent à 3. Réservation : la boucle sort à 3 ; le choix non compris et la recherche sans résultat sortent à 2.
Deux seuils différents = deux clés, chacune avec sa valeur par défaut dans le schéma (lue par le formulaire).
"""

from __future__ import annotations

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults as W
from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes.seuil_de_sortie import CLE_FOIS_AVANT_LA_SORTIE, CLE_RESERVATION, CLE_RESERVATION_BOUCLE
from api.tests.mark import test_restauration_reservation as _RESA
from api.tests.mark.partie_1.porte_essai_reservation import choix_non_compris, la_meme_question_n_fois

salle = _RESA.salle


def test_le_schema_porte_une_valeur_par_defaut_pour_chaque_seuil_comme_avant():
    assert W.model_fields[CLE_FOIS_AVANT_LA_SORTIE].default == 3  # boucle et refus redit de la commande
    assert W.model_fields[CLE_RESERVATION_BOUCLE].default == 3  # boucle de la réservation
    assert W.model_fields[CLE_RESERVATION].default == 2  # choix non compris et recherche sans résultat de la réservation
    assert len({CLE_FOIS_AVANT_LA_SORTIE, CLE_RESERVATION_BOUCLE, CLE_RESERVATION}) == 3


async def test_la_boucle_de_la_reservation_sort_a_trois_sans_reglage(salle, monkeypatch):
    """« Pour combien de personnes ? » / « Je sais pas encore » / « Je vais voir » : avant, une troisième fois ; la sortie vient à la troisième."""
    assert await la_meme_question_n_fois(salle, monkeypatch, {}, 3) == [False, False, True]


async def test_la_boucle_de_la_reservation_a_sa_propre_cle(salle, monkeypatch):
    assert await la_meme_question_n_fois(salle, monkeypatch, {CLE_RESERVATION: 5}, 3) == [False, False, True]  # la clé du choix ne la règle pas
    assert await la_meme_question_n_fois(salle, monkeypatch, {CLE_RESERVATION_BOUCLE: 2}, 2) == [False, True]


async def test_le_choix_et_la_recherche_de_la_reservation_sortent_toujours_a_deux(salle, monkeypatch):
    retours = await choix_non_compris(salle, monkeypatch, {})
    assert len(retours) == 2 and retours[-1]["raison"] == "choix_non_compris_deux_fois", retours


def test_la_commande_sort_a_trois_pour_le_refus_redit_et_la_boucle():
    d: dict = {}
    assert [J.fait_redit(d, "x", t, 3) for t in (1, 2, 3)] == [J.PREMIERE, J.ISSUE, J.SORTIE]
    d = {}
    assert [J.boucle(d, ["a"], True, 3) for _ in range(3)] == [False, False, True]
