"""[.mark] Plan final Partie 1, lot 9 (n° 92) : ``resoudre_l_heure`` refuse elle-même une durée (par sa forme) ; ``_heure_seule`` ne lit plus les mots.

Scénario : la personne dit « dans deux heures » : ce n est pas une heure du jour, la question du jour reste posée ; « dans trois jours à 20 h » ou « le 24 décembre 2026 à 20 h » gardent leur heure.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from api.db.bases_clients import dates_futures as DF
from api.services.restauration import source_commande as SC

LOCAL = datetime(2026, 11, 12, 12, 0, tzinfo=ZoneInfo("Europe/Paris"))


@pytest.mark.parametrize("dit", ["dans deux heures", "dans 2 heures", "dans une heure et demie", "dans 20 minutes", "dans une demi-heure", "dans 2h", "dans 1h30", "dans 45mn", "dans 45min", "dans 2 h 30"])
def test_une_duree_n_est_jamais_une_heure_du_jour(dit):
    assert DF.resoudre_l_heure(dit).statut == DF.INTROUVABLE


@pytest.mark.parametrize("dit,attendu", [("19 h 30", time(19, 30)), ("dix-neuf heures", time(19, 0)), ("midi et demi", time(12, 30)), ("huit heures du soir", time(20, 0))])
def test_une_heure_du_jour_reste_lue(dit, attendu):
    assert DF.resoudre_l_heure(dit).heure == attendu


def test_sans_jour_une_duree_laisse_la_question_du_jour():
    r = SC.resolution_du_jour_et_de_l_heure("dans deux heures", None, LOCAL)
    assert r.statut == "INTROUVABLE" and r.manque == "jour"
    r = SC.resolution_du_jour_et_de_l_heure(None, "dans deux heures", LOCAL)
    assert r.statut == "INTROUVABLE" and r.manque == "jour"


# Un jour déjà dit : « dans » ou une année écrite dans la phrase ne sont pas une durée, l'heure dite est lue sans question de trop.
MARDI_17_H = datetime(2026, 11, 24, 17, 0, tzinfo=ZoneInfo("Europe/Paris"))


@pytest.mark.parametrize(
    "dit,jour,heure",
    [
        ("dans trois jours à 20 h", "2026-11-27", time(20, 0)),
        ("demain dans la soirée vers 20 h", "2026-11-25", time(20, 0)),
        ("le 24 décembre 2026 à 20 h", "2026-12-24", time(20, 0)),
    ],
)
def test_un_jour_dit_avec_dans_ou_une_annee_garde_son_heure(dit, jour, heure):
    r = SC.resolution_du_jour_et_de_l_heure(dit, dit, MARDI_17_H)
    assert r.statut == "RETENU", r
    assert r.faits["jour"] == jour
    assert DF.resoudre_l_heure(dit).heure == heure


@pytest.mark.parametrize("dit", ["dans 20 minutes", "dans deux heures", "dans une heure et demie", "dans 3 heures"])
def test_une_duree_n_est_pas_une_heure_meme_avec_le_jour_dit(dit):
    assert DF.resoudre_l_heure(dit).statut == DF.INTROUVABLE
    assert SC.resolution_du_jour_et_de_l_heure(f"demain {dit}", dit, MARDI_17_H).statut != "RETENU"


@pytest.mark.parametrize("dit,attendu", [("à 20h", time(20, 0)), ("pour 19h30", time(19, 30)), ("demain à 20h", time(20, 0))])
def test_une_heure_collee_sans_dans_reste_lue(dit, attendu):
    assert DF.resoudre_l_heure(dit).heure == attendu
    assert SC.resolution_du_jour_et_de_l_heure(dit, dit, MARDI_17_H).statut == "RETENU"
