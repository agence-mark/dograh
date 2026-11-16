"""[.mark] SA-18, lot C (C14) : « samedi soir » ne rend que des créneaux du soir, et le nombre de personnes n'est jamais deviné.

Aux essais du 17/11, « soir » rendait des créneaux de midi, et le modèle inventait « une personne ». Source simulée : aucune base.
"""

from datetime import datetime, timedelta, timezone

import pytest

from api.services.commande.resultat import Resultat
from api.services.integrations.connectors import catalogue
from api.services.reservation import moteur

PARIS = timezone(timedelta(hours=1))
SAMEDI = datetime(2026, 11, 21, tzinfo=PARIS)


class Salle:
    """Une source simulée : des créneaux à 12 h, 13 h, 19 h et 20 h."""

    def __init__(self, heures=(12, 13, 19, 20)):
        self.heures = heures

    async def resoudre_une_date(self, texte, heure):
        return Resultat("INCOMPLETE", {"jour": SAMEDI.date().isoformat(), "jour_dit": "samedi"}, "À quelle heure ?", "heure")

    async def disponibilites(self, jour, effectif):
        return Resultat("OK", {"creneaux": [{"debut": SAMEDI.replace(hour=h)} for h in self.heures]})


async def _creneaux(jour, heure=None, heures=(12, 13, 19, 20)):
    r = await moteur.disponibilites(Salle(heures), {}, jour, 4, heure)
    assert r.statut == "OK", r
    return [f"{c['debut'].hour:02d}" for c in r.faits["creneaux"]], r


async def test_le_soir_ne_rend_que_des_creneaux_du_soir():
    heures, r = await _creneaux("samedi soir")
    assert heures == ["19", "20"] and r.faits["complet"] is False


async def test_le_midi_ne_rend_que_des_creneaux_du_midi():
    heures, _ = await _creneaux("samedi midi")
    assert heures == ["12", "13"]


async def test_sans_partie_de_la_journee_comme_avant():
    heures, _ = await _creneaux("samedi")
    assert heures == ["12", "13", "19", "20"][:4] and len(heures) == 4


async def test_un_soir_complet_le_dit_sans_rendre_ceux_du_midi():
    heures, r = await _creneaux("samedi soir", heures=(12, 13))
    assert heures == [] and r.faits["complet"] is True and r.faits["partie"] == "soir" and "soir" in r.suggestion


@pytest.mark.parametrize("action", ["disponibilites", "reserver"])
def test_le_nombre_de_personnes_n_est_jamais_devine(action):
    _, a = catalogue.trouver("reservation", action)
    p = next(p for p in a.parametres if p.nom == "personnes")
    assert "Never guess" in p.description and p.obligatoire is False
