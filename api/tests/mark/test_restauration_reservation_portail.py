"""[.mark] Module Restauration, lot 8, étape 4 : les routes de réservation faites par le restaurant depuis le portail.

Vraies routes, vraie authentification (clé d'API de l'organisation), vraie base du client, vrai Redis.

| Test | Ce qu'il prouve |
|---|---|
| créer | 201, table attribuée, source ``portail`` au journal, ``reservation.creee`` émis |
| complet | 409 ``COMPLET`` avec les créneaux libres les plus proches ; rien d'écrit, rien d'émis ; la proposition est réservable |
| règles | une règle refusée = 422 avec sa raison fermée (jamais un texte de la couche) ; rien d'écrit |
| modifier | ses propres tables comptent comme libres ; ``reservation.changee`` ; rien à changer : 422 ; complet : 409, rien ne change |
| annuler | 200 puis 409 ``DEJA_FAIT`` (rien d'émis la seconde fois) ; une passée est figée (409) |
| cloisonnement | la clé d'une autre organisation, un autre établissement de la même, un établissement inconnu, une réservation d'un autre établissement : 404 ; rien ne bouge |
| entrées | sans clé 401 ; champ en trop, nombre nul, heure sans fuseau, numéro invalide : 422 |
| permission | ``portail.ecrire`` pour une clé au registre ; les trois routes sont gelées dans le contrat avec le portail |
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import horloge
from api.services.equipe_mark import registre_routes as registre
from api.services.restauration import flux
from api.tests.mark.equipe_commun import client_http, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import _cle, seconde_base  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark.test_restauration_flux import (  # noqa: F401
    _deux_organisations_avec_des_etablissements,
    _depuis_le_debut,
    _evenements,
    organisations,
)

PARIS = ZoneInfo("Europe/Paris")
SAMEDI_20H = datetime(2026, 11, 14, 20, 0, tzinfo=PARIS)
RACINE = "/api/v1/restauration/etablissements"


@pytest.fixture(autouse=True)
def flux_court(monkeypatch):
    monkeypatch.setattr(flux, "BLOCAGE_LECTURE_MS", 150)
    monkeypatch.setattr(flux, "NB_BATTEMENTS_MAX", 1)


async def _installer_la_salle(base: str, etablissement: int) -> None:
    c = await schema.connecter(base)
    try:
        s = await c.fetchval("INSERT INTO mark.resto_salle (site_id, nom) VALUES ($1, 'Salle') RETURNING id", etablissement)
        for nom, mini, maxi in (("T1", 1, 2), ("T2", 1, 2), ("T3", 2, 4), ("T4", 4, 6)):
            await c.execute("INSERT INTO mark.resto_table (site_id, salle_id, nom, couverts_min, couverts_max) VALUES ($1, $2, $3, $4, $5)", etablissement, s, nom, mini, maxi)
        await c.execute("INSERT INTO mark.resto_service (site_id, nom, jours, debut, fin, pas_minutes) VALUES ($1, 'Soir', '{1,2,3,4,5,6,7}', '19:00', '22:00', 15)", etablissement)
        await c.execute("INSERT INTO mark.resto_duree_groupe (site_id, couverts_min, couverts_max, duree_minutes) VALUES ($1, 1, 10, 90)", etablissement)
        await c.execute("INSERT INTO mark.resto_regle_reservation (site_id, delai_minimal, jours_a_l_avance, couverts_max_groupe) VALUES ($1, 60, 30, 6)", etablissement)
    finally:
        await c.close()


async def _monde(db_session, seconde_base):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    await _installer_la_salle(cas.base_a, cas.sites_a[0])
    return cas


def _corps(**plus) -> dict:
    return {"debut": SAMEDI_20H.isoformat(), "couverts": 2, "prenom": "Alice", "telephone": "+33612345678", **plus}


async def _evenements_de(organisation: int, etablissement: int) -> list[tuple[str, dict]]:
    texte = "".join([m async for m in flux.ecouter(organisation, [etablissement], role="equipe", reprise=_depuis_le_debut(etablissement), nb_battements_max=1)])
    return [(e["event"], e["data"]["donnees"]) for e in _evenements(texte) if e["event"].startswith("reservation.")]


async def _lignes(base: str, sql: str, *args):
    c = await schema.connecter(base)
    try:
        return await c.fetch(sql, *args)
    finally:
        await c.close()


async def test_creer_attribue_une_table_journalise_le_portail_et_emet(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _monde(db_session, seconde_base)
    etab = cas.sites_a[0]
    with horloge.remplacer(cas.base_a, JEUDI_MIDI):
        async with client_http() as c:
            r = await c.post(f"{RACINE}/{etab}/reservations", json=_corps(), headers=_cle(cas.cle_a))
    assert r.status_code == 201, r.text
    corps = r.json()
    assert (corps["couverts"], corps["prenom"], corps["statut"], corps["tables"], corps["duree_minutes"]) == (2, "Alice", "confirmee", ["T1"], 90)
    lignes = await _lignes(cas.base_a, "SELECT cree_par FROM mark.resto_reservation")
    assert [l["cree_par"] for l in lignes] == ["portail"]
    journal = await _lignes(cas.base_a, "SELECT source FROM mark.resto_journal WHERE objet = 'resto_reservation' AND operation = 'insert'")
    assert [j["source"] for j in journal] == ["portail"]
    assert await _evenements_de(cas.a, etab) == [("reservation.creee", {"reservation_id": corps["numero"]})]


async def test_complet_rend_409_avec_les_creneaux_les_plus_proches_et_rien_n_est_ecrit(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _monde(db_session, seconde_base)
    etab = cas.sites_a[0]
    with horloge.remplacer(cas.base_a, JEUDI_MIDI):
        async with client_http() as c:
            for n, tel in ((2, "+33600000001"), (2, "+33600000002"), (4, "+33600000003"), (6, "+33600000004")):
                assert (await c.post(f"{RACINE}/{etab}/reservations", json=_corps(couverts=n, telephone=tel), headers=_cle(cas.cle_a))).status_code == 201
            plein = await c.post(f"{RACINE}/{etab}/reservations", json=_corps(telephone="+33600000009"), headers=_cle(cas.cle_a))
            assert plein.status_code == 409 and plein.json()["detail"]["code"] == "COMPLET"
            propositions = plein.json()["detail"]["propositions"]
            assert 1 <= len(propositions) <= 3
            # la proposition est réellement réservable
            ok = await c.post(f"{RACINE}/{etab}/reservations", json=_corps(debut=propositions[0]["debut"], telephone="+33600000010"), headers=_cle(cas.cle_a))
            assert ok.status_code == 201
    assert len(await _lignes(cas.base_a, "SELECT 1 FROM mark.resto_reservation")) == 5
    assert len(await _evenements_de(cas.a, etab)) == 5   # les quatre premières + la proposition : le complet n'émet rien


async def test_une_regle_refusee_rend_422_avec_sa_raison_fermee(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _monde(db_session, seconde_base)
    etab = cas.sites_a[0]
    cas_de_regles = {
        "passe": datetime(2026, 11, 12, 11, 0, tzinfo=PARIS),
        "trop_tot": datetime(2026, 11, 12, 12, 30, tzinfo=PARIS),
        "trop_loin": datetime(2026, 12, 25, 20, 0, tzinfo=PARIS),
        "hors_service": datetime(2026, 11, 14, 15, 0, tzinfo=PARIS),
    }
    with horloge.remplacer(cas.base_a, JEUDI_MIDI):
        async with client_http() as c:
            for raison, debut in cas_de_regles.items():
                r = await c.post(f"{RACINE}/{etab}/reservations", json=_corps(debut=debut.isoformat()), headers=_cle(cas.cle_a))
                assert (r.status_code, r.json()["detail"]) == (422, {"code": raison}), (raison, r.text)
            groupe = await c.post(f"{RACINE}/{etab}/reservations", json=_corps(couverts=7), headers=_cle(cas.cle_a))
    assert (groupe.status_code, groupe.json()["detail"]) == (422, {"code": "groupe_trop_grand"})
    assert await _lignes(cas.base_a, "SELECT 1 FROM mark.resto_reservation") == [] and await _evenements_de(cas.a, etab) == []


async def test_modifier_ses_tables_comptent_comme_libres_puis_complet_ne_change_rien(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _monde(db_session, seconde_base)
    etab = cas.sites_a[0]
    with horloge.remplacer(cas.base_a, JEUDI_MIDI):
        async with client_http() as c:
            n = (await c.post(f"{RACINE}/{etab}/reservations", json=_corps(couverts=6), headers=_cle(cas.cle_a))).json()["numero"]
            url = f"{RACINE}/{etab}/reservations/{n}"
            glisse = await c.patch(url, json={"debut": (SAMEDI_20H + timedelta(minutes=30)).isoformat()}, headers=_cle(cas.cle_a))
            assert glisse.status_code == 200 and glisse.json()["tables"] == ["T4"] and glisse.json()["debut"].startswith("2026-11-14T19:30")   # 20 h 30 à Paris = 19 h 30 UTC
            autre = await c.post(f"{RACINE}/{etab}/reservations", json=_corps(couverts=6, debut=(SAMEDI_20H - timedelta(hours=1)).isoformat(), telephone="+33600000005"), headers=_cle(cas.cle_a))
            assert autre.status_code == 201
            pris = await c.patch(url, json={"debut": (SAMEDI_20H - timedelta(minutes=30)).isoformat()}, headers=_cle(cas.cle_a))
            assert pris.status_code == 409 and pris.json()["detail"]["code"] == "COMPLET"
            vide = await c.patch(url, json={}, headers=_cle(cas.cle_a))
            nom = await c.patch(url, json={"prenom": "Alicia", "note": "fenêtre"}, headers=_cle(cas.cle_a))
    assert vide.status_code == 422 and nom.status_code == 200 and (nom.json()["prenom"], nom.json()["note"]) == ("Alicia", "fenêtre")
    debut = await _lignes(cas.base_a, "SELECT debut FROM mark.resto_reservation WHERE numero = $1", uuid.UUID(n))
    assert debut[0]["debut"] == SAMEDI_20H + timedelta(minutes=30)       # le refus n'a rien changé
    evenements = await _evenements_de(cas.a, etab)
    assert [e for e, _ in evenements].count("reservation.changee") == 2 and [e for e, _ in evenements].count("reservation.creee") == 2


async def test_annuler_une_fois_puis_deja_fait_une_passee_est_figee(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _monde(db_session, seconde_base)
    etab = cas.sites_a[0]
    with horloge.remplacer(cas.base_a, JEUDI_MIDI):
        async with client_http() as c:
            n = (await c.post(f"{RACINE}/{etab}/reservations", json=_corps(), headers=_cle(cas.cle_a))).json()["numero"]
            premier = await c.post(f"{RACINE}/{etab}/reservations/{n}/annuler", headers=_cle(cas.cle_a))
            second = await c.post(f"{RACINE}/{etab}/reservations/{n}/annuler", headers=_cle(cas.cle_a))
            modif = await c.patch(f"{RACINE}/{etab}/reservations/{n}", json={"couverts": 3}, headers=_cle(cas.cle_a))
    assert premier.status_code == 200 and premier.json()["statut"] == "annulee"
    assert (second.status_code, second.json()["detail"]["code"]) == (409, "DEJA_FAIT")
    assert (modif.status_code, modif.json()["detail"]) == (409, {"code": "plus_modifiable"})
    assert [e for e, _ in await _evenements_de(cas.a, etab)] == ["reservation.creee", "reservation.changee"]       # le second geste n'émet rien
    with horloge.remplacer(cas.base_a, JEUDI_MIDI):
        async with client_http() as c:
            n2 = (await c.post(f"{RACINE}/{etab}/reservations", json=_corps(telephone="+33600000007"), headers=_cle(cas.cle_a))).json()["numero"]
    with horloge.remplacer(cas.base_a, SAMEDI_20H + timedelta(minutes=10)):
        async with client_http() as c:
            figee = await c.post(f"{RACINE}/{etab}/reservations/{n2}/annuler", headers=_cle(cas.cle_a))
            figee_modif = await c.patch(f"{RACINE}/{etab}/reservations/{n2}", json={"couverts": 3}, headers=_cle(cas.cle_a))
    assert [(r.status_code, r.json()["detail"]) for r in (figee, figee_modif)] == [(409, {"code": "passee"})] * 2


async def test_cloisonnement_organisation_etablissement_et_reservation(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _monde(db_session, seconde_base)
    un, deux = cas.sites_a
    with horloge.remplacer(cas.base_a, JEUDI_MIDI):
        async with client_http() as c:
            n = (await c.post(f"{RACINE}/{un}/reservations", json=_corps(), headers=_cle(cas.cle_a))).json()["numero"]
            inconnu = max(cas.sites_a + cas.sites_b) + 1000
            essais = [
                await c.patch(f"{RACINE}/{un}/reservations/{n}", json={"couverts": 3}, headers=_cle(cas.cle_b)),                 # une autre organisation
                await c.post(f"{RACINE}/{un}/reservations/{n}/annuler", headers=_cle(cas.cle_b)),
                await c.post(f"{RACINE}/{max(cas.sites_a + cas.sites_b) + 1000}/reservations", json=_corps(), headers=_cle(cas.cle_b)),   # un identifiant que B ne connaît pas
                await c.patch(f"{RACINE}/{deux}/reservations/{n}", json={"couverts": 3}, headers=_cle(cas.cle_a)),               # le mauvais établissement
                await c.post(f"{RACINE}/{deux}/reservations/{n}/annuler", headers=_cle(cas.cle_a)),
                await c.post(f"{RACINE}/{inconnu}/reservations", json=_corps(), headers=_cle(cas.cle_a)),                       # un établissement inconnu
                await c.post(f"{RACINE}/{un}/reservations/{uuid.uuid4()}/annuler", headers=_cle(cas.cle_a)),                    # une réservation inconnue
            ]
    assert [r.status_code for r in essais] == [404] * 7
    ligne = await _lignes(cas.base_a, "SELECT couverts, statut FROM mark.resto_reservation")
    assert [(l["couverts"], l["statut"]) for l in ligne] == [(2, "confirmee")]
    assert await _evenements_de(cas.b, cas.sites_b[0]) == [] and len(await _evenements_de(cas.a, un)) == 1


async def test_les_entrees_sont_validees(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _monde(db_session, seconde_base)
    etab = cas.sites_a[0]
    url = f"{RACINE}/{etab}/reservations"
    async with client_http() as c:
        sans_cle = await c.post(url, json=_corps())
        mauvais = [
            await c.post(url, json=corps, headers=_cle(cas.cle_a))
            for corps in (
                {**_corps(), "table": "T1"},                 # champ en trop
                _corps(couverts=0), _corps(prenom=""), _corps(telephone="06"),
                _corps(debut="2026-11-14T20:00:00"),         # sans fuseau
                {"couverts": 2},
            )
        ]
        pas_un_numero = await c.patch(f"{url}/abc", json={"couverts": 3}, headers=_cle(cas.cle_a))
        etab_zero = await c.post(f"{RACINE}/0/reservations", json=_corps(), headers=_cle(cas.cle_a))
    assert sans_cle.status_code == 401
    assert [r.status_code for r in mauvais] == [422] * 6 and pas_un_numero.status_code == 422 and etab_zero.status_code == 422
    assert await _lignes(cas.base_a, "SELECT 1 FROM mark.resto_reservation") == []


# --------------------------------------------------------------------------- permission et contrat

LES_TROIS = [
    ("POST", "/restauration/etablissements/{etablissement_id}/reservations"),
    ("PATCH", "/restauration/etablissements/{etablissement_id}/reservations/{reservation_id}"),
    ("POST", "/restauration/etablissements/{etablissement_id}/reservations/{reservation_id}/annuler"),
]


def test_les_routes_ont_leur_permission_au_registre_ouverte_a_la_cle():
    from api.services.equipe_mark.permissions import PERMISSIONS_DE_CLE

    for methode, chemin in LES_TROIS:
        decision, _ = registre.decision_de(methode, chemin)
        assert isinstance(decision, registre.Permission) and decision.cle == "agents.modifier" and decision.pour_cle == "portail.ecrire", chemin
        assert decision.pour_cle in PERMISSIONS_DE_CLE


def test_les_routes_sont_gelees_dans_le_contrat_avec_le_portail():
    from api.tests.mark.test_contrat_portail_fork import P, ROUTES_DU_PORTAIL

    gele = json.loads((Path(__file__).with_name("contrat_portail_fork.json")).read_text(encoding="utf-8"))
    for methode, chemin in LES_TROIS:
        assert (methode, P + chemin) in ROUTES_DU_PORTAIL
        forme = gele[f"{methode} {P}{chemin}"]
        assert forme["ouverte_a_la_cle"] is True and forme["permission"] == "agents.modifier" and forme["permission_de_cle"] == "portail.ecrire"
    creation = gele[f"POST {P}{LES_TROIS[0][1]}"]
    assert set(creation["corps"]["application/json"]["properties"]) == {"debut", "couverts", "prenom", "telephone", "note"}
    assert "201" in creation["reponses"]
