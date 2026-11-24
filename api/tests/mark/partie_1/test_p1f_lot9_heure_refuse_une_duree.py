"""[.mark] Plan final Partie 1, lot 9 (n° 92) : ``resoudre_l_heure`` refuse elle-même une durée ou une date écrite ; ``_heure_seule`` ne lit plus les mots.

Scénario : la personne dit « dans deux heures » ou « 2026-11-17 à 19 h » : ce n'est pas une heure du jour, la question du jour reste posée.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from api.db.bases_clients import dates_futures as DF
from api.services.restauration import source_commande as SC

LOCAL = datetime(2026, 11, 12, 12, 0, tzinfo=ZoneInfo("Europe/Paris"))


@pytest.mark.parametrize("dit", ["dans deux heures", "dans 2 heures", "dans une heure et demie", "2026-11-17 à 19 h", "le 17 novembre 2026 à 20 h"])
def test_une_duree_ou_une_date_ecrite_n_est_jamais_une_heure_du_jour(dit):
    assert DF.resoudre_l_heure(dit).statut == DF.INTROUVABLE


@pytest.mark.parametrize("dit,attendu", [("19 h 30", time(19, 30)), ("dix-neuf heures", time(19, 0)), ("midi et demi", time(12, 30)), ("huit heures du soir", time(20, 0))])
def test_une_heure_du_jour_reste_lue(dit, attendu):
    assert DF.resoudre_l_heure(dit).heure == attendu


def test_sans_jour_une_duree_laisse_la_question_du_jour():
    r = SC.resolution_du_jour_et_de_l_heure("dans deux heures", None, LOCAL)
    assert r.statut == "INTROUVABLE" and r.manque == "jour"
    r = SC.resolution_du_jour_et_de_l_heure(None, "dans deux heures", LOCAL)
    assert r.statut == "INTROUVABLE" and r.manque == "jour"
