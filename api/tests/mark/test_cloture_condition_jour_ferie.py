"""[.mark] Clôture, lot C : la condition « jour férié » d'une porte (calendrier français calculé, aucune liste écrite à la main).

| Test | Ce qu'il prouve |
|---|---|
| calendrier | les onze jours fériés de 2026 et 2027 (Pâques, Ascension et Pentecôte calculés) sont vrais, les jours voisins faux |
| vrai / faux | « est vrai » et « est faux » se répondent ; une comparaison qui n'a pas de sens pour ce champ est fausse (dans le doute : fausse) |
| lecture | la règle est lue par ``lecture_de`` (jamais « illisible »), sans valeur à saisir |
| jour de Paris | le jour est celui de Paris, pas celui de l'horloge du serveur |
"""

from __future__ import annotations

from datetime import datetime

import pytest

from api.services.pipecat.etat_ouverture import PARIS
from api.services.workflow import conditions_de_porte as cp
from api.tests.mark.test_sa11_conditions_de_porte import _moteur, regle

FERIES_2026 = [(1, 1), (4, 6), (5, 1), (5, 8), (5, 14), (5, 25), (7, 14), (8, 15), (11, 1), (11, 11), (12, 25)]
FERIES_2027 = [(1, 1), (3, 29), (5, 1), (5, 8), (5, 6), (5, 17), (7, 14), (8, 15), (11, 1), (11, 11), (12, 25)]


def _vrai(jour: datetime, comparaison="est_vrai", monkeypatch=None):
    monkeypatch.setattr(cp, "_maintenant", lambda: jour)
    return cp.regle_vraie(_moteur(), None, regle("heure", "jour_ferie", comparaison))


@pytest.mark.parametrize("annee, jours", [(2026, FERIES_2026), (2027, FERIES_2027)])
def test_les_jours_feries_de_l_annee_sont_vrais_et_les_voisins_faux(annee, jours, monkeypatch):
    for mois, jour in jours:
        instant = datetime(annee, mois, jour, 10, 0, tzinfo=PARIS)
        assert _vrai(instant, "est_vrai", monkeypatch) is True, (annee, mois, jour)
        assert _vrai(instant, "est_faux", monkeypatch) is False, (annee, mois, jour)
    # des jours ordinaires, dont le vendredi saint (férié seulement en Alsace-Moselle) et la veille de Noël
    for mois, jour in [(1, 2), (4, 3), (12, 24), (6, 15)]:
        instant = datetime(annee, mois, jour, 10, 0, tzinfo=PARIS)
        assert _vrai(instant, "est_vrai", monkeypatch) is False, (annee, mois, jour)
        assert _vrai(instant, "est_faux", monkeypatch) is True, (annee, mois, jour)


def test_une_comparaison_sans_sens_pour_ce_champ_est_fausse(monkeypatch):
    monkeypatch.setattr(cp, "_maintenant", lambda: datetime(2026, 12, 25, 10, 0, tzinfo=PARIS))
    for comparaison in ("est", "n_est_pas", "avant", "apres"):
        assert cp.regle_vraie(_moteur(), None, regle("heure", "jour_ferie", comparaison, "oui")) is False
    # et « est vrai » sur l'heure ou le jour de la semaine n'a pas de sens non plus
    assert cp.regle_vraie(_moteur(), None, regle("heure", "heure", "est_vrai")) is False
    assert cp.regle_vraie(_moteur(), None, regle("heure", "jour", "est_vrai", "jeudi")) is False


def test_la_regle_est_lue_sans_valeur():
    condition = {"regles": [{"source": "heure", "champ": "jour_ferie", "comparaison": "est_vrai", "valeur": ""}]}
    lue = cp.lecture_de(condition)
    assert lue["type"] == "regles" and not lue.get("illisible") and len(lue["regles"]) == 1
    assert "jour_ferie" in cp.CHAMPS_HEURE


def test_le_jour_est_celui_de_paris(monkeypatch):
    # 31/12/2026 23:30 à Paris : pas férié ; 25/12 00:10 à Paris : férié, même si l'horloge du serveur (UTC) dit encore le 24.
    assert _vrai(datetime(2026, 12, 25, 0, 10, tzinfo=PARIS), "est_vrai", monkeypatch) is True
    assert _vrai(datetime(2026, 12, 31, 23, 30, tzinfo=PARIS), "est_vrai", monkeypatch) is False
