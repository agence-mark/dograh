"""[.mark] SA-47, lot 2 (essai au clavier du 17/11, appel 2593, Casa Italia) : l'heure dite sans jour, et le numéro qui s'affiche.

- M109 : « pour dix-neuf heures » sans jour : ``resoudre_une_date(texte="dix-neuf heures", heure="dix-neuf heures")`` rendait INTROUVABLE « Pour
  quel jour ? ». Une heure dite sans jour vaut aujourd'hui si elle est encore à venir au fuseau du lieu ; passée, c'est une question, jamais un choix.
  « Zéro faux sûr » gardé : « sept heures » sans moment reste ambigu.
- M110 : le numéro s'affichait, mais le modèle demandait « votre numéro » et disait « Je n'ai pas votre numéro ». Chaque retour de la commande et
  de la réservation porte le fait ``numero_s_affiche`` (un booléen, jamais le numéro) quand un numéro s'affiche ; absent sinon.

| Test | Ce qu'il prouve |
|---|---|
| à venir | « dix-neuf heures » (heure, texte, ou les deux) à 10 h 50 : aujourd'hui 19 h, sans question |
| passée | à 20 h : une question sur le jour, rien de retenu |
| ambiguë | « sept heures » sans moment : la question sur l'heure, jamais un choix |
| rien de lisible | ni jour ni heure, une durée, une date écrite : « Pour quel jour ? » comme avant |
| jour dit | « demain », « ce soir » : inchangés |
| numéro affiché | commande et réservation : le fait est là quand le numéro s'affiche, absent sinon, jamais le numéro en clair |
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from api.db.bases_clients import textes_de_secours_commande as TSC
from api.services.commande.resultat import CLE_NUMERO_S_AFFICHE
from api.services.restauration.source_commande import resolution_du_jour_et_de_l_heure
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_reservation import salle  # noqa: F401

PARIS = ZoneInfo("Europe/Paris")
MATIN = datetime(2026, 11, 17, 10, 50, tzinfo=PARIS)
SOIR = datetime(2026, 11, 17, 20, 0, tzinfo=PARIS)


@pytest.mark.parametrize(
    "texte, heure",
    [("dix-neuf heures", "dix-neuf heures"), ("", "dix-neuf heures"), ("dix-neuf heures", None), ("pour 19h", None), ("", "19 h")],
)
def test_m109_une_heure_a_venir_sans_jour_vaut_aujourd_hui(texte, heure):
    r = resolution_du_jour_et_de_l_heure(texte, heure, MATIN)
    assert r.statut == "RETENU", r
    assert r.faits["heure_voulue"] == "2026-11-17T19:00:00+01:00" and r.faits["jour_dit"] == "mardi dix-sept novembre"


def test_m109_une_heure_deja_passee_sans_jour_est_une_question():
    """C7 B12 (T9, rouge depuis 9cd42f70, C7a) : le texte « Il est déjà plus de dix-neuf heures : pour quel jour ? » est sorti du retour (décision d'Evan 25/11 8 h 45, le modèle
    parle) ; la question reste (manque ``jour``) et ce qu'elle disait est dans les faits, d'où le texte d'avant se refait (« pas juste une suppression »)."""
    r = resolution_du_jour_et_de_l_heure("dix-neuf heures", "dix-neuf heures", SOIR)
    assert r.statut != "RETENU" and r.manque == "jour" and r.suggestion == "" and "heure_voulue" not in r.faits
    assert r.faits["heure_dite"] == "dix-neuf heures" and r.faits["heure_passee_aujourd_hui"] is True
    assert TSC.heure_passee_sans_jour(r.faits) == "Il est déjà plus de dix-neuf heures : pour quel jour ?"


def test_m109_sept_heures_sans_moment_reste_ambigu():
    r = resolution_du_jour_et_de_l_heure("sept heures", "sept heures", MATIN)
    assert r.statut == "AMBIGU" and r.manque == "heure" and "heure_voulue" not in r.faits
    assert r.faits["candidats_heure"] == ["sept heures", "dix-neuf heures"]


@pytest.mark.parametrize("texte, heure", [("", None), ("bientôt", None), ("dans deux heures", None), ("2026-11-17T19:00:00", None)])
def test_m109_sans_heure_du_jour_lisible_la_question_du_jour_reste(texte, heure):
    r = resolution_du_jour_et_de_l_heure(texte, heure, MATIN)
    # C7 B12 (T9, rouge depuis 9cd42f70, C7a) : « Pour quel jour ? » est dit par le modèle d'après le manque (décision d'Evan 25/11 8 h 45), plus par le retour
    assert (r.statut, r.suggestion, r.manque) == ("INTROUVABLE", "", "jour")


def test_m109_un_jour_dit_ne_change_pas():
    assert resolution_du_jour_et_de_l_heure("demain", "dix-neuf heures", MATIN).faits["heure_voulue"] == "2026-11-18T19:00:00+01:00"
    assert resolution_du_jour_et_de_l_heure("ce soir", "dix-neuf heures", MATIN).faits["heure_voulue"] == "2026-11-17T19:00:00+01:00"
    assert resolution_du_jour_et_de_l_heure("demain", None, MATIN).manque == "heure"


# --------------------------------------------------------------------------- #
# M110 : le fait « un numéro s'affiche »
# --------------------------------------------------------------------------- #


async def test_m110_commande_le_fait_est_la_quand_le_numero_s_affiche_et_absent_sinon(commerce, monkeypatch):  # noqa: F811
    """Lot 4 (D49) : même scénario par la fiche (montage de la porte) : le fait ``numero_s_affiche`` est dans les faits de la fiche, jamais le numéro."""
    from api.tests.mark.partie_1.porte_essai import Essai

    e = Essai(commerce, monkeypatch, appelant="+33612345678")
    r = await e.tour("à emporter", mode_de_retrait="emporter")
    assert r["faits"][CLE_NUMERO_S_AFFICHE] is True
    assert "0612345678" not in str(r) and "+33612345678" not in str(r)
    sans = Essai(commerce, monkeypatch, appelant="+33612345678")
    sans.ctx.appel = {}
    r = await sans.tour("à emporter", mode_de_retrait="emporter")
    assert CLE_NUMERO_S_AFFICHE not in r["faits"]


async def test_m110_reservation_le_fait_est_la_quand_le_numero_s_affiche_et_absent_sinon(salle, monkeypatch):
    """Lot 7 (D49) : même scénario par la fiche de réservation (montage de la porte)."""
    from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation

    e = EssaiReservation(salle, monkeypatch)
    r = await e.tour("pour deux personnes", personnes=2)
    assert r["faits"][CLE_NUMERO_S_AFFICHE] is True and "12345678" not in str(r)
    sans = EssaiReservation(salle, monkeypatch, appelant=None)
    r = await sans.tour("pour deux personnes", personnes=2)
    assert CLE_NUMERO_S_AFFICHE not in r["faits"]
