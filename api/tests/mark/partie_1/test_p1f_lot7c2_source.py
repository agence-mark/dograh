"""[.mark] Lot 7b-C2, source de la commande (``restauration/source_commande.py``) : chaque refus ne porte que ses faits.

C7 B9 : le catalogue de secours est supprimé ; chaque texte d'avant devient les faits qu'il lisait (ou tous les faits, quand il était fixe) : les faits du refus suffisent à
le redire. Ce que la personne entend ne change pas (le modèle le dit avec ses mots)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from api.services.restauration.source_commande import resolution_du_jour_et_de_l_heure

PARIS = ZoneInfo("Europe/Paris")
MATIN = datetime(2026, 11, 17, 10, 50, tzinfo=PARIS)
SOIR = datetime(2026, 11, 17, 20, 0, tzinfo=PARIS)


def test_jour_introuvable_dit_pour_quel_jour():
    r = resolution_du_jour_et_de_l_heure("bientôt", None, MATIN)
    assert (r.statut, r.manque, r.suggestion) == ("INTROUVABLE", "jour", "")
    assert dict(r.faits) == {}


def test_heure_sans_jour_deja_passee_dit_pour_quel_jour():
    r = resolution_du_jour_et_de_l_heure("dix-neuf heures", "dix-neuf heures", SOIR)
    assert (r.statut, r.manque, r.suggestion) == ("INTROUVABLE", "jour", "")
    assert r.faits == {"heure_dite": "dix-neuf heures", "heure_passee_aujourd_hui": True}
    assert r.faits.get('heure_dite') == 'dix-neuf heures'


@pytest.mark.parametrize("texte, heure", [("", "sept heures"), ("demain", "sept heures")])
def test_heure_ambigue_propose_les_deux_heures(texte, heure):
    r = resolution_du_jour_et_de_l_heure(texte, heure, MATIN)
    assert (r.statut, r.manque, r.suggestion) == ("AMBIGU", "heure", "")  # C7 B3 : le modèle pose la question (Evan 25/11 8 h 45) ; les faits la refont
    assert r.faits.get('candidats_heure') == ['sept heures', 'dix-neuf heures']


def test_jour_ambigu_propose_les_deux_jours():
    r = resolution_du_jour_et_de_l_heure("le 17", None, MATIN)
    assert (r.statut, r.manque, r.suggestion) == ("AMBIGU", "jour", "")  # C7 B3 : le modèle pose la question (Evan 25/11 8 h 45) ; les faits la refont
    assert r.faits.get('candidats') == [{'jour': '2026-11-17', 'jour_dit': 'mardi dix-sept novembre'}, {'jour': '2026-12-17', 'jour_dit': 'jeudi dix-sept décembre'}]


def test_jour_sans_heure_demande_l_heure_de_ce_jour():
    r = resolution_du_jour_et_de_l_heure("demain", None, MATIN)
    assert (r.statut, r.manque, r.suggestion) == ("INCOMPLETE", "heure", "")
    assert r.faits.get('jour_dit') == 'mercredi dix-huit novembre'


def test_heure_illisible_demande_l_heure_exacte():
    r = resolution_du_jour_et_de_l_heure("demain", "bientôt", MATIN)
    assert (r.statut, r.manque, r.suggestion) == ("INCOMPLETE", "heure", "")
    assert {k: r.faits.get(k) for k in ('jour', 'jour_dit')} == {'jour': '2026-11-18', 'jour_dit': 'mercredi dix-huit novembre'}


def test_heure_deja_passee_aujourd_hui_porte_son_fait():
    r = resolution_du_jour_et_de_l_heure("aujourd'hui", "neuf heures du matin", MATIN)
    assert (r.statut, r.manque, r.suggestion) == ("ARGUMENT_INVALIDE", "heure", "")
    assert r.faits["heure_passee_aujourd_hui"] is True and r.faits["heure_dite"] == "neuf heures"
    assert {k: r.faits.get(k) for k in ('jour', 'jour_dit', 'heure_voulue', 'heure_dite', 'heure_passee_aujourd_hui')} == {'jour': '2026-11-17', 'jour_dit': 'mardi dix-sept novembre', 'heure_voulue': '2026-11-17T09:00:00+01:00', 'heure_dite': 'neuf heures', 'heure_passee_aujourd_hui': True}


@pytest.mark.parametrize("jour", ["aujourd'hui", "ce soir", "demain", "après-demain", "mardi", "samedi", "le 17", "le 18", "le 24 novembre", "ce week-end", "dans trois jours"])
def test_une_heure_passee_n_arrive_jamais_un_autre_jour_qu_aujourd_hui(jour):
    """``dates_futures`` ne rend jamais un jour avant aujourd'hui : quand l'heure voulue est passée, c'est aujourd'hui, donc ``heure_passee_aujourd_hui`` est toujours vrai."""
    r = resolution_du_jour_et_de_l_heure(jour, "neuf heures du matin", SOIR)
    if r.statut == "ARGUMENT_INVALIDE":
        assert r.faits["jour"] == SOIR.date().isoformat() and r.faits["heure_passee_aujourd_hui"] is True
