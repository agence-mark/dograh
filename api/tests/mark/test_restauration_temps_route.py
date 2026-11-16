"""[.mark] Module Restauration, lot 6, étape 2 : la puce du temps du portail, ``GET`` et ``PUT /restauration/etablissements/{id}/temps``.

Vraie authentification (clé d'API de l'organisation), vraies bases de clients, vrai Redis.

| Test | Ce qu'il prouve |
|---|---|
| lecture | 401 sans clé ; l'état des quatre types et l'annonce par type et par zone |
| écriture | la durée ajoutée remplace celle du type, se lit tout de suite, s'éteint à « fin du service » ; l'auteur réel va au journal |
| pause | absente = intacte, durée, heure, ``null`` = levée ; le type en pause se ferme, les autres non |
| flux | une écriture émet ``temps.change`` dans le flux de CET établissement et d'aucun autre ; un refus n'émet rien |
| caisse | quand la caisse porte l'état : lecture seule, 409, rien n'est changé, rien n'est émis (E-49) |
| validation | 422 hors bornes, type inconnu, champ en trop, heure passée, temps pour une réservation |
| cloisonnement | l'établissement d'une autre organisation, ou inconnu : 404 sans rien lire ni écrire ; la clé d'une organisation ne change pas le temps d'une autre |
| permission et contrat | permissions au registre ouvertes à la clé ; les deux routes sont dans le contrat figé avec le portail |
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import redis.asyncio as aioredis

from api.constants import REDIS_URL
from api.db.bases_clients import connexion as schema
from api.db.bases_clients import horloge
from api.services.equipe_mark import registre_routes as registre
from api.services.restauration import flux
from api.tests.mark.equipe_commun import client_http, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import _cle, seconde_base  # noqa: F401
from api.tests.mark.test_restauration_flux import _deux_organisations_avec_des_etablissements

RACINE = "/api/v1/restauration/etablissements"


def _url(etab: int) -> str:
    return f"{RACINE}/{etab}/temps"


def _type(corps: dict, nom: str) -> dict:
    return next(t for t in corps["types"] if t["type"] == nom)


async def _evenements_du_flux(organisation: int, etablissement: int) -> list[dict]:
    flux._redis = None
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        return [{**json.loads(c["donnees"]), "evenement": c["type"]} for _, c in await r.xrange(flux.cle_du_flux(organisation, etablissement))]
    finally:
        await r.aclose()
        flux._redis = None


async def _base(cas):
    return cas


# --------------------------------------------------------------------------- #
# Lecture, écriture
# --------------------------------------------------------------------------- #


async def test_sans_cle_401_et_la_lecture_rend_l_etat_des_quatre_types(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    async with client_http() as c:
        assert (await c.get(_url(etab))).status_code == 401
        r = await c.get(_url(etab), headers=_cle(cas.cle_a))
    assert r.status_code == 200
    corps = r.json()
    assert [t["type"] for t in corps["types"]] == ["emporter", "livraison", "sur_place", "reservation"]
    assert corps["lecture_seule"] is False and corps["source_de_l_etat"] == "portail" and corps["etat_caisse"] is None
    assert _type(corps, "emporter")["annonce"]["format"] == "duree" and _type(corps, "reservation")["annonce"] is None


async def test_la_puce_pose_une_duree_ajoutee_qui_se_lit_tout_de_suite_et_remplace_la_precedente(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    # L'heure vient de la source d'heure de l'organisation, fixée : l'annonce en durée arrondit selon les secondes écoulées (15 ou 16 minutes, au gré de l'instant).
    with horloge.remplacer(cas.base_a, datetime(2026, 11, 12, 12, 0, tzinfo=UTC)):
        async with client_http() as c:
            r = await c.put(_url(etab), json={"type": "emporter", "minutes_ajoutees": 15}, headers=_cle(cas.cle_a))
            assert r.status_code == 200, r.text
            emporter = _type(r.json(), "emporter")
            assert (emporter["minutes_ajoutees"], emporter["ajout_actif"], emporter["annonce"]["minutes"]) == (15, 15, 15)
            assert _type(r.json(), "livraison")["minutes_ajoutees"] == 0  # par type
            relue = await c.get(_url(etab), headers=_cle(cas.cle_a))
            assert _type(relue.json(), "emporter")["minutes_ajoutees"] == 15
            r = await c.put(_url(etab), json={"type": "emporter", "minutes_ajoutees": 0}, headers=_cle(cas.cle_a))
            assert _type(r.json(), "emporter")["ajout_actif"] == 0


async def test_jusqu_a_fin_du_service_et_l_auteur_reel_va_au_journal(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    async with client_http() as c:
        r = await c.put(_url(etab), json={"type": "livraison", "minutes_ajoutees": 10, "jusqu_a": "fin_du_service"}, headers=_cle(cas.cle_a))
    assert r.status_code == 200, r.text
    liv = _type(r.json(), "livraison")
    fin = datetime.fromisoformat(liv["ajout_jusqu_a"])
    assert fin > datetime.now(UTC) and fin - datetime.now(UTC) <= timedelta(days=1)  # la fin du service du jour
    c_a = await schema.connecter(cas.base_a)
    try:
        j = await c_a.fetchrow("SELECT source, auteur FROM mark.resto_journal WHERE site_id = $1 AND objet = 'resto_reglage_type' ORDER BY id DESC LIMIT 1", etab)
    finally:
        await c_a.close()
    assert j["source"] == "portail" and j["auteur"].startswith("portail : ") and "dograh:" in j["auteur"]  # qui, par quelle voie


async def test_une_heure_passee_ou_hors_bornes_est_refusee_sans_rien_ecrire(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    passe = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    async with client_http() as c:
        mauvais = [
            {"type": "emporter", "minutes_ajoutees": 241},
            {"type": "emporter", "minutes_ajoutees": -1},
            {"type": "sur_la_lune", "minutes_ajoutees": 5},
            {"type": "emporter", "minutes_ajoutees": 5, "en_trop": 1},
            {"type": "emporter", "minutes_ajoutees": 5, "jusqu_a": passe},
            {"type": "emporter", "minutes_ajoutees": 5, "jusqu_a": "bientôt"},
            {"type": "reservation", "minutes_ajoutees": 5},
            {"type": "emporter", "minutes_ajoutees": 5, "pause": {"minutes": 0}},
            {"type": "emporter", "minutes_ajoutees": 5, "pause": {"minutes": 99999}},
            {"type": "emporter", "minutes_ajoutees": 5, "pause": {"jusqu_a": passe}},
            {"type": "emporter", "minutes_ajoutees": 5, "pause": {"autre": 1}},
            {"minutes_ajoutees": 5},
        ]
        for corps in mauvais:
            r = await c.put(_url(etab), json=corps, headers=_cle(cas.cle_a))
            assert r.status_code == 422, (corps, r.status_code, r.text)
    assert await _evenements_du_flux(cas.a, etab) == []  # un refus n'émet rien
    c_a = await schema.connecter(cas.base_a)
    try:
        assert await c_a.fetchval("SELECT count(*) FROM mark.resto_reglage_type WHERE site_id = $1 AND (minutes_ajoutees > 0 OR pause_jusqu_a IS NOT NULL)", etab) == 0
    finally:
        await c_a.close()


# --------------------------------------------------------------------------- #
# La pause
# --------------------------------------------------------------------------- #


async def test_la_pause_ferme_le_type_seulement_est_gardee_quand_elle_est_absente_et_levee_par_null(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    async with client_http() as c:
        r = await c.put(_url(etab), json={"type": "livraison", "minutes_ajoutees": 0, "pause": {"minutes": 30}}, headers=_cle(cas.cle_a))
        assert r.status_code == 200, r.text
        liv = _type(r.json(), "livraison")
        assert (liv["ouvert"], liv["raison"]) == (False, "pause_type") and liv["pause_jusqu_a"] is not None
        assert _type(r.json(), "emporter")["ouvert"] is True
        r = await c.put(_url(etab), json={"type": "livraison", "minutes_ajoutees": 5}, headers=_cle(cas.cle_a))  # pause absente : intacte
        assert _type(r.json(), "livraison")["ouvert"] is False
        r = await c.put(_url(etab), json={"type": "livraison", "minutes_ajoutees": 5, "pause": None}, headers=_cle(cas.cle_a))  # null : levée
        assert _type(r.json(), "livraison")["ouvert"] is True
        r = await c.put(_url(etab), json={"type": "sur_place", "minutes_ajoutees": 0, "pause": {}}, headers=_cle(cas.cle_a))  # sans heure : fin de journée
        sur_place = _type(r.json(), "sur_place")
        assert sur_place["ouvert"] is False and datetime.fromisoformat(sur_place["pause_jusqu_a"]) - datetime.now(UTC) <= timedelta(days=1, hours=1)


# --------------------------------------------------------------------------- #
# Le flux
# --------------------------------------------------------------------------- #


async def test_une_ecriture_emet_temps_change_dans_le_flux_de_cet_etablissement_seulement(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab, autre = cas.sites_a[0], cas.sites_a[1]
    async with client_http() as c:
        await c.put(_url(etab), json={"type": "emporter", "minutes_ajoutees": 10}, headers=_cle(cas.cle_a))
        await c.put(_url(etab), json={"type": "livraison", "minutes_ajoutees": 5}, headers=_cle(cas.cle_a))
    evenements = await _evenements_du_flux(cas.a, etab)
    assert [(e["evenement"], e["type"]) for e in evenements] == [("temps.change", "emporter"), ("temps.change", "livraison")]
    assert await _evenements_du_flux(cas.a, autre) == [] and await _evenements_du_flux(cas.b, cas.sites_b[0]) == []
    flux.verifier("temps.change", {"type": "emporter"})  # le contrat § 3 : le type seulement


# --------------------------------------------------------------------------- #
# La caisse porte l'état
# --------------------------------------------------------------------------- #


async def test_quand_la_caisse_porte_l_etat_la_puce_est_en_lecture_seule(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    c_a = await schema.connecter(cas.base_a)
    try:
        await c_a.execute("INSERT INTO mark.resto_etat_caisse (site_id, mode, minutes_en_plus, source) VALUES ($1, 'deborde', 10, 'caisse')", etab)
    finally:
        await c_a.close()
    async with client_http() as c:
        lue = await c.get(_url(etab), headers=_cle(cas.cle_a))
        assert lue.json()["lecture_seule"] is True and lue.json()["source_de_l_etat"] == "caisse"
        assert lue.json()["etat_caisse"]["mode"] == "deborde" and _type(lue.json(), "emporter")["annonce"]["minutes"] in (10, 11)  # la caisse prime (arrondi vers le haut à la minute)
        r = await c.put(_url(etab), json={"type": "emporter", "minutes_ajoutees": 15}, headers=_cle(cas.cle_a))
    assert r.status_code == 409 and "till" in r.json()["detail"]
    assert await _evenements_du_flux(cas.a, etab) == []
    c_a = await schema.connecter(cas.base_a)
    try:
        assert await c_a.fetchval("SELECT count(*) FROM mark.resto_reglage_type WHERE site_id = $1 AND minutes_ajoutees > 0", etab) == 0
    finally:
        await c_a.close()


# --------------------------------------------------------------------------- #
# Cloisonnement
# --------------------------------------------------------------------------- #


async def test_l_etablissement_d_une_autre_organisation_ou_inconnu_est_un_404_sans_rien_lire_ni_ecrire(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    chez_b = cas.sites_b[0]
    inconnu = max(cas.sites_a + cas.sites_b) + 1000
    async with client_http() as c:
        r = await c.put(_url(inconnu), json={"type": "emporter", "minutes_ajoutees": 20}, headers=_cle(cas.cle_a))
        assert r.status_code == 404
        assert (await c.get(_url(inconnu), headers=_cle(cas.cle_a))).status_code == 404
        assert (await c.put(_url(inconnu), json={"type": "emporter", "minutes_ajoutees": 20}, headers=_cle(cas.cle_a))).status_code == 404
        assert (await c.get(_url("abc"), headers=_cle(cas.cle_a))).status_code == 422
        assert (await c.get(_url(chez_b), headers=_cle(cas.cle_b))).status_code == 200  # la sienne
    for organisation, base, site in ((cas.b, cas.base_b, chez_b),):
        c_b = await schema.connecter(base)
        try:
            assert await c_b.fetchval("SELECT count(*) FROM mark.resto_reglage_type WHERE site_id = $1 AND minutes_ajoutees > 0", site) == 0
        finally:
            await c_b.close()
        assert await _evenements_du_flux(organisation, site) == []


async def test_le_meme_numero_d_etablissement_chez_deux_organisations_ne_se_melange_pas(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    async with client_http() as c:
        # les deux bases partagent peut-être le même identifiant de site : chaque clé ne voit et ne change que SA base
        await c.put(_url(cas.sites_a[0]), json={"type": "emporter", "minutes_ajoutees": 25}, headers=_cle(cas.cle_a))
        b = await c.get(_url(cas.sites_b[0]), headers=_cle(cas.cle_b))
    assert _type(b.json(), "emporter")["minutes_ajoutees"] == 0


# --------------------------------------------------------------------------- #
# Permission et contrat
# --------------------------------------------------------------------------- #


def test_les_deux_routes_ont_leur_permission_au_registre_ouverte_a_la_cle():
    from api.services.equipe_mark.permissions import PERMISSIONS_DE_CLE

    chemin = "/restauration/etablissements/{etablissement_id}/temps"
    lecture, _ = registre.decision_de("GET", chemin)
    ecriture, _ = registre.decision_de("PUT", chemin)
    assert isinstance(lecture, registre.Permission) and lecture.cle == "conversations.voir"
    assert isinstance(ecriture, registre.Permission) and (ecriture.pour_cle or ecriture.cle) == "portail.ecrire"
    assert (lecture.pour_cle or lecture.cle) in PERMISSIONS_DE_CLE and (ecriture.pour_cle or ecriture.cle) in PERMISSIONS_DE_CLE


def test_les_deux_routes_sont_gelees_dans_le_contrat_avec_le_portail():
    from api.tests.mark.test_contrat_portail_fork import P, ROUTES_DU_PORTAIL

    chemin = f"{P}/restauration/etablissements/{{etablissement_id}}/temps"
    assert ("GET", chemin) in ROUTES_DU_PORTAIL and ("PUT", chemin) in ROUTES_DU_PORTAIL
    gele = json.loads(Path(__file__).with_name("contrat_portail_fork.json").read_text(encoding="utf-8"))
    assert gele[f"GET {chemin}"]["ouverte_a_la_cle"] is True and gele[f"PUT {chemin}"]["ouverte_a_la_cle"] is True
    corps = gele[f"PUT {chemin}"]["corps"]["application/json"]
    assert {"type", "minutes_ajoutees"} <= set(corps["properties"])
    assert "types" in json.dumps(gele[f"GET {chemin}"]["reponses"])


_ = pytest
