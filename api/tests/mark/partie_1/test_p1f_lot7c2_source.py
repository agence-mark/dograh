"""[.mark] Lot 7b-C2, source de la commande (``restauration/source_commande.py``) : le texte de chaque refus est le texte de secours de ses seuls faits.

Pour chaque refus : le texte rendu est inchangé au caractère près (il est écrit ici en clair), et il est égal à ``textes_de_secours_commande.<texte>(faits)`` : les faits du
refus suffisent à le redire. Ce que la personne entend ne change pas."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from api.db.bases_clients import textes_de_secours_commande as TSC
from api.services.restauration.source_commande import resolution_du_jour_et_de_l_heure

PARIS = ZoneInfo("Europe/Paris")
MATIN = datetime(2026, 11, 17, 10, 50, tzinfo=PARIS)
SOIR = datetime(2026, 11, 17, 20, 0, tzinfo=PARIS)


def test_jour_introuvable_dit_pour_quel_jour():
    r = resolution_du_jour_et_de_l_heure("bientôt", None, MATIN)
    assert (r.statut, r.manque, r.suggestion) == ("INTROUVABLE", "jour", "Pour quel jour ?")
    assert r.suggestion == TSC.quel_jour(r.faits)


def test_heure_sans_jour_deja_passee_dit_pour_quel_jour():
    r = resolution_du_jour_et_de_l_heure("dix-neuf heures", "dix-neuf heures", SOIR)
    assert (r.statut, r.manque, r.suggestion) == ("INTROUVABLE", "jour", "Il est déjà plus de dix-neuf heures : pour quel jour ?")
    assert r.faits == {"heure_dite": "dix-neuf heures", "heure_passee_aujourd_hui": True}
    assert r.suggestion == TSC.heure_passee_sans_jour(r.faits)


@pytest.mark.parametrize("texte, heure", [("", "sept heures"), ("demain", "sept heures")])
def test_heure_ambigue_propose_les_deux_heures(texte, heure):
    r = resolution_du_jour_et_de_l_heure(texte, heure, MATIN)
    assert (r.statut, r.manque, r.suggestion) == ("AMBIGU", "heure", "Est-ce sept heures ou dix-neuf heures ?")
    assert r.suggestion == TSC.heure_ambigue(r.faits)


def test_jour_ambigu_propose_les_deux_jours():
    r = resolution_du_jour_et_de_l_heure("le 17", None, MATIN)
    assert (r.statut, r.manque, r.suggestion) == ("AMBIGU", "jour", "Est-ce mardi dix-sept novembre ou jeudi dix-sept décembre ?")
    assert r.suggestion == TSC.jour_ambigu(r.faits)


def test_jour_sans_heure_demande_l_heure_de_ce_jour():
    r = resolution_du_jour_et_de_l_heure("demain", None, MATIN)
    assert (r.statut, r.manque, r.suggestion) == ("INCOMPLETE", "heure", "À quelle heure, mercredi dix-huit novembre ?")
    assert r.suggestion == TSC.quelle_heure_ce_jour(r.faits)


def test_heure_illisible_demande_l_heure_exacte():
    r = resolution_du_jour_et_de_l_heure("demain", "bientôt", MATIN)
    assert (r.statut, r.manque, r.suggestion) == ("INCOMPLETE", "heure", "À quelle heure exactement ?")
    assert r.suggestion == TSC.quelle_heure_exactement(r.faits)


def test_heure_deja_passee_aujourd_hui_porte_son_fait():
    r = resolution_du_jour_et_de_l_heure("aujourd'hui", "neuf heures du matin", MATIN)
    assert (r.statut, r.manque, r.suggestion) == ("ARGUMENT_INVALIDE", "heure", "Cette heure est déjà passée, pour quelle heure ?")
    assert r.faits["heure_passee_aujourd_hui"] is True and r.faits["heure_dite"] == "neuf heures"
    assert r.suggestion == TSC.heure_passee(r.faits)


@pytest.mark.parametrize("jour", ["aujourd'hui", "ce soir", "demain", "après-demain", "mardi", "samedi", "le 17", "le 18", "le 24 novembre", "ce week-end", "dans trois jours"])
def test_une_heure_passee_n_arrive_jamais_un_autre_jour_qu_aujourd_hui(jour):
    """``dates_futures`` ne rend jamais un jour avant aujourd'hui : quand l'heure voulue est passée, c'est aujourd'hui, donc ``heure_passee_aujourd_hui`` est toujours vrai."""
    r = resolution_du_jour_et_de_l_heure(jour, "neuf heures du matin", SOIR)
    if r.statut == "ARGUMENT_INVALIDE":
        assert r.faits["jour"] == SOIR.date().isoformat() and r.faits["heure_passee_aujourd_hui"] is True
