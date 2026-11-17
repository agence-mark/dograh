"""[.mark] M99 et M100 (essais au clavier du 17/11, appel 2587) : le module des dates, commun à la commande et à la réservation.

- M99 : « midi et demi » était lu 12 h 00 (les minutes après « midi » ou « minuit » étaient perdues).
- M100 : « mardi dix-sept novembre », dit un mardi 17, était jugé ambigu entre le 17 et le 24 : les mentions d'une même date (le jour de la semaine
  ET le quantième) s'additionnaient au lieu de se recouper. La date que l'agent relit (``jour_dit``) doit toujours se relire sans question.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from api.db.bases_clients.dates_futures import AMBIGU, RETENU, jour_dit, resoudre_l_heure, resoudre_une_date

PARIS = ZoneInfo("Europe/Paris")
MARDI_17 = datetime(2026, 11, 17, 10, 50, tzinfo=PARIS)


@pytest.mark.parametrize(
    "dit, attendu",
    [
        ("midi et demi", time(12, 30)),
        ("midi et demie", time(12, 30)),
        ("midi trente", time(12, 30)),
        ("midi et quart", time(12, 15)),
        ("midi moins le quart", time(11, 45)),
        ("midi quinze", time(12, 15)),
        ("minuit et demi", time(0, 30)),
        ("midi", time(12, 0)),
        ("ce midi", time(12, 0)),
    ],
)
def test_m99_les_minutes_apres_midi_et_minuit_sont_gardees(dit, attendu):
    r = resoudre_l_heure(dit)
    assert r.statut == RETENU and r.heure == attendu


@pytest.mark.parametrize("dit", ["mardi dix-sept novembre", "mardi 17 novembre", "mardi le 17", "aujourd'hui mardi", "ce midi, mardi"])
def test_m100_le_jour_de_la_semaine_et_le_quantieme_se_recoupent(dit):
    r = resoudre_une_date(dit, MARDI_17)
    assert r.statut == RETENU and r.jour == date(2026, 11, 17)


def test_m100_la_date_relue_par_l_agent_se_relit_toujours_sans_question():
    for ecart in range(0, 35):
        jour = MARDI_17.date() + timedelta(days=ecart)
        r = resoudre_une_date(jour_dit(jour), MARDI_17)
        assert r.statut == RETENU and r.jour == jour, jour_dit(jour)


def test_m100_un_vrai_doute_reste_une_question():
    assert resoudre_une_date("mardi", MARDI_17).statut == AMBIGU  # le jour même : aujourd'hui ou dans huit jours
    assert resoudre_une_date("mercredi le 17", MARDI_17).statut == AMBIGU  # contradiction : on ne choisit pas
