"""[.mark] Chantier Partie 1, lot 1 : les types communs (Adresse, MomentVoulu, ConsigneLivreur et Habitude, Note) et leur branchement.

Les quatre phrases de Pierre (complément du 18/11, point 3) sont jouées au fuseau Europe/Paris, le mercredi 18 novembre 2026 à midi, posé par
l'horloge des tests (``horloge.remplacer`` par le montage du banc A), sur la vraie chaîne : ``moteur.heure_du_lieu`` → la source → la résolution.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from api.services.actions_communes.types import Adresse, ConsigneLivreur, Habitude, MomentVoulu, Note
from api.services.commande import moteur
from api.services.restauration.prises.hubrise_traduction import TraductionImpossible, commande_vers_hubrise
from api.tests.mark.banc_a.commun import appel_de, base_essai, base_prete, faire_monde  # noqa: F401

PARIS = ZoneInfo("Europe/Paris")
MERCREDI_MIDI = datetime(2026, 11, 18, 12, 0, tzinfo=PARIS)
SENLIS_INSEE = "60612"


# --------------------------------------------------------------------------- les types


def test_adresse_aller_retour_json():
    a = Adresse(voie="12 rue de la République", code_postal="60300", commune="Senlis", insee=SENLIS_INSEE, texte_dit="12 rue de la République, Senlis")
    relue = Adresse.depuis_json(json.loads(json.dumps(a.vers_json())))
    assert relue == a
    with pytest.raises(ValueError):
        Adresse(voie="12 rue", code_postal=None, commune="", insee=None, texte_dit="12 rue")


def test_moment_sans_fuseau_refuse():
    with pytest.raises(ValueError):
        MomentVoulu(debut="2026-11-26T20:00:00", texte_dit="jeudi vingt-six à vingt heures")
    with pytest.raises(ValueError):
        MomentVoulu.depuis_un_instant(datetime(2026, 11, 26, 20, 0), "jeudi vingt-six")
    with pytest.raises(ValueError):
        MomentVoulu(debut=None, texte_dit="tout de suite")  # ni instant, ni « dès que possible »
    m = MomentVoulu(debut="2026-11-26T20:00:00+01:00", texte_dit="jeudi vingt-six à vingt heures")
    assert MomentVoulu.depuis_json(json.loads(json.dumps(m.vers_json()))) == m
    assert MomentVoulu(debut=None, texte_dit="dès que possible", des_que_possible=True).instant() is None


def test_consigne_et_habitude_distinctes():
    c = ConsigneLivreur(texte="code 1234, deuxième étage", source="modele")
    h = Habitude(texte="toujours sans oignons", source="modele")
    assert type(c) is not type(h) and c.USAGE == "commande" and h.USAGE == "fiche_client"
    assert c != ConsigneLivreur(texte="toujours sans oignons", source="modele")
    with pytest.raises(ValueError):
        ConsigneLivreur.depuis_json(h.vers_json())  # une habitude ne se relit jamais en consigne
    assert ConsigneLivreur.depuis_json(c.vers_json()) == c


def test_note_porte_sa_source():
    n = Note(texte="allergie aux arachides", source="greffier", portee="commande")
    assert Note.depuis_json(n.vers_json()) == n and n.source == "greffier"
    with pytest.raises(ValueError):
        Note(texte="bien cuite", source="inconnue", portee="ligne")
    with pytest.raises(ValueError):
        Note(texte="bien cuite", source="modele", portee="panier")


# --------------------------------------------------------------------------- l'adresse structurée, du moteur à la caisse


async def _adresse_retenue(a, texte: str) -> dict:
    a.p["mode"] = "livraison"
    r = await moteur.verifier_adresse(a.source, a.p, moteur.Reglages(), texte)
    assert r.statut == "RETENU", (r.statut, r.faits, r.suggestion)
    return a.p["adresse"]


async def test_verifier_adresse_garde_la_commune(appel_de):
    a = await appel_de("casa-italia")
    adresse = await _adresse_retenue(a, "12 rue de la République, Senlis")
    assert isinstance(adresse, dict), f"l'adresse est gardée en texte : {adresse!r}"
    assert Adresse.depuis_json(adresse) == Adresse(
        voie="12 rue de la République", code_postal="60300", commune="Senlis", insee=SENLIS_INSEE, texte_dit="12 rue de la République, Senlis"
    )


async def test_caisse_recoit_rue_code_postal_ville(appel_de):
    a = await appel_de("casa-italia")
    adresse = await _adresse_retenue(a, "12 rue de la République, Senlis")
    commande = {"mode": "livraison", "numero": "c-1", "client": {"telephone": "+33600000000"}, "adresse": json.loads(json.dumps(adresse)), "lignes": []}
    client = commande_vers_hubrise(commande)["customer"]
    assert (client.get("address_1"), client.get("postal_code"), client.get("city")) == ("12 rue de la République", "60300", "Senlis"), client


def test_traducteur_sans_branche_texte():
    with pytest.raises(TraductionImpossible):
        commande_vers_hubrise({"mode": "livraison", "numero": "c-1", "client": {}, "adresse": "C'est au 12 rue de la République", "lignes": []})


# --------------------------------------------------------------------------- les quatre phrases de Pierre (MomentVoulu)


async def _moment(a, texte: str):
    r = await moteur.heure_du_lieu(a.source, texte, {})
    assert r is not None
    return r


@pytest.mark.parametrize("faire_monde", [MERCREDI_MIDI], indirect=True)
async def test_pierre_jeudi_vingt_six(appel_de):
    a = await appel_de("casa-italia")
    r = await _moment(a, "jeudi vingt-six à vingt heures")
    assert r.statut == "RETENU", (r.statut, r.faits)
    m = MomentVoulu.depuis_json(r.faits["moment_voulu"])
    assert m.instant() == datetime(2026, 11, 26, 20, 0, tzinfo=PARIS) and m.texte_dit == "jeudi vingt-six à vingt heures"


@pytest.mark.parametrize("faire_monde", [MERCREDI_MIDI], indirect=True)
async def test_pierre_vendredi_treize(appel_de):
    a = await appel_de("casa-italia")
    r = await _moment(a, "vendredi 13 à vingt heures")
    jours = {c.get("jour") for c in r.faits.get("candidats") or []}
    assert "2026-11-20" not in jours, r.faits
    if r.statut == "RETENU":
        voulu = MomentVoulu.depuis_json(r.faits["moment_voulu"]).instant()
        assert voulu.day == 13 and voulu.weekday() == 4, voulu  # le prochain vendredi 13, jamais vendredi 20
    else:
        assert r.statut == "AMBIGU" and r.faits.get("candidats"), (r.statut, r.faits)  # une question, jamais un choix


@pytest.mark.parametrize("faire_monde", [MERCREDI_MIDI], indirect=True)
async def test_pierre_trois_heures_apres_midi(appel_de):
    a = await appel_de("casa-italia")
    r = await _moment(a, "aujourd'hui à trois heures de l'après-midi")
    assert r.statut == "RETENU", (r.statut, r.faits, r.suggestion)
    assert MomentVoulu.depuis_json(r.faits["moment_voulu"]).instant() == datetime(2026, 11, 18, 15, 0, tzinfo=PARIS)


@pytest.mark.parametrize("faire_monde", [MERCREDI_MIDI], indirect=True)
async def test_pierre_ce_week_end_vingt_heures(appel_de):
    a = await appel_de("casa-italia")
    r = await _moment(a, "ce week-end à 20 h")
    assert r.statut == "AMBIGU", (r.statut, r.faits)
    assert {c["jour"] for c in r.faits["candidats"]} == {date(2026, 11, 21).isoformat(), date(2026, 11, 22).isoformat()}, r.faits
