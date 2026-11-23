"""[.mark] Module Restauration, lot 9, étape 4 : « Brancher ma caisse » (OAuth), la fiche de liaison et les ruptures poussées à la caisse.

Vraie authentification (clé d'API), vraies bases de clients, vrai Redis, vraie base de Dograh ; la caisse est un transport ENREGISTRÉ (``reponses_hubrise/``) :
aucun appel réel.

| Test | Ce qu'il prouve |
|---|---|
| fiche | 401 sans clé ; sans liaison : « portail », « aucune » et la fiche du portail ; avec liaison : la fiche HubRise, sans adresse sortante |
| cloisonnement | un établissement d'une autre organisation (ou inconnu) : 404 partout, rien n'est écrit chez l'une ni chez l'autre |
| brancher | 503 sans configuration ; avec : l'adresse d'autorisation de HubRise (liste fermée) ; le ``state`` n'est gardé qu'en empreinte, à durée courte ; 422 hors prise |
| retour | un ``state`` forgé, absent ou rejoué est refusé (400) sans rien écrire ; un refus de la page d'autorisation aussi |
| branchement de bout en bout | jeton rangé au coffre de l'organisation et JAMAIS dans la base du client ; point de vente relié ; carte, ruptures et état importés ; liaison « ok » ; événement ``caisse.liaison`` |
| point de vente pris | un point de vente déjà relié à un autre établissement ou à une autre organisation est refusé |
| mode passif | une adresse de réception refusée par HubRise : l'abonnement passe en mode passif, dit sur la liaison |
| rupture | posée chez nous d'abord, événement ``rupture.changee``, poussée à la caisse en ``PATCH`` ; une caisse en panne : ``poussee_a_la_caisse`` faux, liaison « erreur », la rupture reste ; jeton refusé : « rompue » |
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import redis.asyncio as aioredis

from api.constants import REDIS_URL
from api.db import db_client
from api.db.bases_clients import connexion as schema
from api.db.bases_clients import restauration
from api.db.bases_clients import restauration_liaison as lia
from api.db.bases_clients.horloge import horloge, remplacer
from api.services.restauration.caisse import caisse as service_caisse
from api.services.restauration.appel_et_memoire import flux
from api.services.restauration.caisse.prises import hubrise_liaison as hl
from api.services.restauration.caisse.prises.hubrise_traduction import carte_de_hubrise
from api.tests.mark.equipe_commun import client_http, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import _cle, seconde_base  # noqa: F401
from api.tests.mark.test_restauration_flux import _deux_organisations_avec_des_etablissements

DOSSIER = Path(__file__).parent / "reponses_hubrise"
RACINE = "/api/v1/restauration/etablissements"


def _corps(nom: str):
    return json.loads((DOSSIER / nom).read_text(encoding="utf-8"))["reponse"]["corps"]


def _caisse_enregistree(*, callback: str = "ok", pdv: str = "w8xvp-0", ordres: dict | None = None, etat: str = "07-point-de-vente-deborde.json"):
    """Une caisse qui répond avec les réponses enregistrées (jamais le réseau). ``callback`` : ``ok`` · ``refuse_l_adresse`` · ``panne`` · ``jeton_faux``."""
    demandes: list[httpx.Request] = []

    def repondre(r: httpx.Request) -> httpx.Response:
        demandes.append(r)
        chemin, methode = r.url.path, r.method
        if callback == "jeton_faux" and not chemin.endswith("/oauth2/v1/token"):
            return httpx.Response(401, json=_corps("18-erreur-jeton-faux.json"))
        if chemin.endswith("/oauth2/v1/token"):
            return httpx.Response(200, json={"access_token": "jeton-secret-de-la-caisse", "location_id": pdv, "catalog_id": "3pmq9", "customer_list_id": "w2dd8", "account_id": "w8xvp"})
        if chemin == "/v1/callback":
            corps = json.loads(r.content)
            if callback == "refuse_l_adresse" and corps["url"]:
                return httpx.Response(422, json={"message": "invalid url", "error_type": "unprocessable_entity"})
            return httpx.Response(200, json={})
        if chemin == "/v1/location" and methode == "GET":
            return httpx.Response(200, json=_corps(etat))
        if chemin.startswith("/v1/location/orders/") and methode == "GET":
            ordre = (ordres or {}).get(chemin.rsplit("/", 1)[-1])
            return httpx.Response(200, json=ordre) if ordre is not None else httpx.Response(404, json={"message": "inconnue", "error_type": "not_found"})
        if chemin == "/v1/location/orders" and methode == "GET":
            return httpx.Response(200, json=[o for o in (ordres or {}).values() if o.get("private_ref") == r.url.params.get("private_ref")])
        if chemin == "/v1/catalogs/3pmq9":
            return httpx.Response(200, json=_corps("04-carte-relue.json"))
        if chemin.endswith("/inventory") and methode == "GET":
            return httpx.Response(200, json=_corps("06-inventaire-lu.json"))
        if chemin.endswith("/inventory") and methode == "PATCH":
            return httpx.Response(500, json={}) if callback == "panne" else httpx.Response(200, json=[])
        return httpx.Response(404, json={"message": "inconnu", "error_type": "not_found"})

    transport = httpx.MockTransport(repondre)
    transport.demandes = demandes
    return transport


@pytest.fixture
def application_configuree(monkeypatch):
    monkeypatch.setenv("HUBRISE_CLIENT_ID", "id-de-notre-application")
    monkeypatch.setenv("HUBRISE_CLIENT_SECRET", "secret-de-notre-application")


async def _etat_redis(state: str) -> list[str]:
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        return [c for c in await r.keys(hl.CLE_STATE + "*") if state in c]
    finally:
        await r.aclose()


async def _evenements(org: int, etab: int) -> list[tuple[str, dict]]:
    flux._redis = None
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        return [(c["type"], json.loads(c["donnees"])) for _, c in await r.xrange(flux.cle_du_flux(org, etab))]
    finally:
        await r.aclose()
        flux._redis = None


async def _etablissements_propres(db_session, seconde_base):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    c = await schema.connecter(cas.base_a)
    try:
        await restauration.importer_carte(c, cas.sites_a[0], carte_de_hubrise(_corps("04-carte-relue.json")).carte, "caisse")
    finally:
        await c.close()
    return cas


# --------------------------------------------------------------------------- fiche, cloisonnement


async def test_la_fiche_dit_portail_sans_liaison_puis_la_fiche_de_la_prise(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    async with client_http() as c:
        assert (await c.get(f"{RACINE}/{etab}/caisse")).status_code == 401
        r = await c.get(f"{RACINE}/{etab}/caisse", headers=_cle(cas.cle_a))
        assert r.status_code == 200, r.text
        sans = r.json()
        assert (sans["prise"], sans["etat"], sans["etat_caisse"], sans["point_de_vente"]) == ("portail", "aucune", None, None)
        base = await schema.connecter(cas.base_a)
        try:
            await lia.poser_liaison(base, etab, "hubrise", "w8xvp-0", "erreur", erreur="caisse_injoignable")
            await lia.poser_etat_de_la_caisse(base, etab, {"mode": "deborde", "minutes_en_plus": 15, "reprise": None, "temps_preparation": 20})
        finally:
            await base.close()
        avec = (await c.get(f"{RACINE}/{etab}/caisse", headers=_cle(cas.cle_a))).json()
    assert (avec["prise"], avec["etat"], avec["derniere_erreur"], avec["point_de_vente"]) == ("hubrise", "erreur", "caisse_injoignable", "w8xvp-0")
    assert avec["etat_caisse"]["mode"] == "deborde" and avec["etat_caisse"]["minutes_en_plus"] == 15
    assert avec["capacites"]["notifications"] == "signees" and "imbrication" not in avec["capacites"]["represente"] and "adresses_permises" not in avec["capacites"]


async def test_un_etablissement_d_une_autre_organisation_est_un_404_partout_sans_rien_ecrire(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas = await _etablissements_propres(db_session, seconde_base)
    chez_b = max(cas.sites_a + cas.sites_b) + 1000
    async with client_http() as c:
        for etab in (chez_b, 999_999_999):
            assert (await c.get(f"{RACINE}/{etab}/caisse", headers=_cle(cas.cle_a))).status_code == 404
            assert (await c.post(f"{RACINE}/{etab}/caisse/brancher", json={"prise": "hubrise"}, headers=_cle(cas.cle_a))).status_code == 404
            r = await c.post(f"{RACINE}/{etab}/ruptures", json={"code_caisse": "REINE-S", "disponible": False}, headers=_cle(cas.cle_a))
            assert r.status_code == 404 and str(etab) not in r.text
        # la clé de B sur l'établissement de A (mêmes numéros dans les deux bases, jamais le même objet)
        assert (await c.get(f"{RACINE}/{max(cas.sites_a) + 5000}/caisse", headers=_cle(cas.cle_b))).status_code == 404
    base = await schema.connecter(cas.base_b)
    try:
        assert await base.fetchval("SELECT count(*) FROM mark.resto_rupture") == 0 and await base.fetchval("SELECT count(*) FROM mark.resto_liaison") == 0
    finally:
        await base.close()


# --------------------------------------------------------------------------- brancher, retour


async def test_brancher_rend_l_adresse_de_hubrise_et_garde_le_state_en_empreinte(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    async with client_http() as c:
        for mauvais in ({"prise": "zelty"}, {"prise": "hubrise", "autre": 1}, {}):
            assert (await c.post(f"{RACINE}/{etab}/caisse/brancher", json=mauvais, headers=_cle(cas.cle_a))).status_code == 422
        r = await c.post(f"{RACINE}/{etab}/caisse/brancher", json={"prise": "hubrise"}, headers=_cle(cas.cle_a))
    assert r.status_code == 200, r.text
    adresse = r.json()["adresse_autorisation"]
    assert adresse.startswith("https://manager.hubrise.com/oauth2/v1/authorize?") and "client_id=id-de-notre-application" in adresse
    assert "secret-de-notre-application" not in adresse and "redirect_uri=" in adresse
    state = adresse.split("state=")[1].split("&")[0]
    assert len(state) >= 40
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        assert await redis.get(hl.CLE_STATE + state) is None  # jamais en clair
        cle = hl.CLE_STATE + hl._empreinte(state)
        assert json.loads(await redis.get(cle))["e"] == etab and 0 < await redis.ttl(cle) <= hl.DUREE_DU_STATE_S
    finally:
        await redis.aclose()


async def test_brancher_sans_configuration_est_un_503(db_session, seconde_base, sans_preparation_des_organisations, monkeypatch):  # noqa: F811
    monkeypatch.delenv("HUBRISE_CLIENT_ID", raising=False)
    monkeypatch.delenv("HUBRISE_CLIENT_SECRET", raising=False)
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    async with client_http() as c:
        r = await c.post(f"{RACINE}/{cas.sites_a[0]}/caisse/brancher", json={"prise": "hubrise"}, headers=_cle(cas.cle_a))
    assert r.status_code == 503 and "secret" not in r.text.lower()


async def test_un_state_forge_absent_ou_rejoue_est_refuse_sans_rien_ecrire(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    retour = "/api/v1/restauration/caisse/hubrise/retour"
    async with client_http() as c:
        assert (await c.get(retour)).status_code == 400
        assert (await c.get(retour, params={"code": "x", "state": "x" * 43})).status_code == 400  # forgé
        assert (await c.get(retour, params={"error": "access_denied", "state": "x" * 43})).status_code == 400
    adresse = await hl.commencer_le_branchement(cas.a, etab, cas.admin.id)
    state = adresse.split("state=")[1].split("&")[0]
    await hl._consommer_le_state(state)  # le premier passage consomme
    with pytest.raises(hl.BranchementRefuse):
        await hl._consommer_le_state(state)  # le rejeu est refusé : usage unique
    base = await schema.connecter(cas.base_a)
    try:
        assert await lia.liaison(base, etab) is None
    finally:
        await base.close()


# --------------------------------------------------------------------------- le branchement de bout en bout


async def _brancher(cas, etab, org, base_nom, transport, user):
    adresse = await hl.commencer_le_branchement(org, etab, user)
    state = adresse.split("state=")[1].split("&")[0]
    return state, await hl.terminer_le_branchement("code-d-autorisation", state, transport=transport)


async def test_le_branchement_range_le_jeton_au_coffre_et_importe_tout(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas = await _etablissements_propres(db_session, seconde_base)
    etab = cas.sites_a[0]
    caisse = _caisse_enregistree()
    state, bilan = await _brancher(cas, etab, cas.a, cas.base_a, caisse, cas.admin.id)
    assert bilan["point_de_vente"] == "w8xvp-0" and bilan["passif"] is False
    base = await schema.connecter(cas.base_a)
    try:
        liaison = await lia.liaison(base, etab)
        assert (liaison["prise"], liaison["etat"], liaison["point_de_vente"], liaison["derniere_erreur"]) == ("hubrise", "ok", "w8xvp-0", None)
        reference = await lia.acces(base, etab)
        # le jeton est au coffre de l'organisation A, jamais dans la base du client
        credential = await db_client.get_credential_by_uuid(reference, cas.a)
        assert credential.credential_data["token"] == "jeton-secret-de-la-caisse"
        assert await db_client.get_credential_by_uuid(reference, cas.b) is None
        for table in ("resto_liaison", "resto_liaison_acces", "resto_etat_caisse", "resto_journal"):
            texte = json.dumps([dict(r) for r in await base.fetch(f"SELECT * FROM mark.{table}")], default=str)
            assert "jeton-secret-de-la-caisse" not in texte and "secret-de-notre-application" not in texte, table
        # l'état de la caisse (débordé, +15) et la rupture lue
        etat = await restauration.etat_caisse(base, etab)
        assert (etat["mode"], etat["minutes_en_plus"], etat["source"]) == ("deborde", 15, "caisse")
        codes = {r["code_caisse"] for r in await restauration.ruptures_du_restaurant(base, etab)}
        assert {"TIRA-1", "SUPP-OEUF"} & codes  # l'inventaire enregistré (06) : un produit et une option à zéro
    finally:
        await base.close()
    lie = await db_client.retrouver_le_point_de_vente("hubrise", "w8xvp-0")
    assert lie["organization_id"] == cas.a
    # le jeton est parti dans l'en-tête, jamais dans une adresse ; l'abonnement est signé par notre adresse de réception
    assert all("jeton-secret" not in str(r.url) for r in caisse.demandes)
    abonnement = next(r for r in caisse.demandes if r.url.path == "/v1/callback")
    assert json.loads(abonnement.content)["url"].endswith(hl.CHEMIN_RAPPEL)
    types = [t for t, _ in await _evenements(cas.a, etab)]
    assert "caisse.etat" in types and "caisse.liaison" in types
    # le state est consommé : un rejeu du même retour est refusé
    with pytest.raises(hl.BranchementRefuse):
        await hl.terminer_le_branchement("code-d-autorisation", state, transport=caisse)


async def test_un_point_de_vente_deja_relie_ailleurs_est_refuse(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas = await _etablissements_propres(db_session, seconde_base)
    caisse = _caisse_enregistree(pdv="pdv-unique-" + str(cas.a))
    await _brancher(cas, cas.sites_a[0], cas.a, cas.base_a, caisse, cas.admin.id)
    # un autre établissement de la même organisation, puis une autre organisation : le même point de vente est refusé
    for org, etab in ((cas.a, cas.sites_a[1]), (cas.b, cas.sites_b[0])):
        adresse = await hl.commencer_le_branchement(org, etab, cas.admin.id)
        state = adresse.split("state=")[1].split("&")[0]
        with pytest.raises(hl.BranchementRefuse) as e:
            await hl.terminer_le_branchement("code", state, transport=caisse)
        assert e.value.code == "point_de_vente_deja_pris"
    base = await schema.connecter(cas.base_b)
    try:
        assert await lia.liaison(base, cas.sites_b[0]) is None
    finally:
        await base.close()


async def test_une_adresse_de_reception_refusee_met_la_liaison_en_mode_passif(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas = await _etablissements_propres(db_session, seconde_base)
    etab = cas.sites_a[0]
    caisse = _caisse_enregistree(callback="refuse_l_adresse", pdv="pdv-passif-" + str(cas.a))
    _, bilan = await _brancher(cas, etab, cas.a, cas.base_a, caisse, cas.admin.id)
    assert bilan["passif"] is True
    corps = [json.loads(r.content) for r in caisse.demandes if r.url.path == "/v1/callback"]
    assert corps[0]["url"] and corps[1]["url"] is None  # d'abord notre adresse, puis « passif » (url: null)
    base = await schema.connecter(cas.base_a)
    try:
        assert (await lia.liaison(base, etab))["mode_passif"] is True
    finally:
        await base.close()


# --------------------------------------------------------------------------- les ruptures


async def test_la_route_pose_la_rupture_chez_nous_et_dit_qu_elle_n_est_pas_poussee_sans_caisse(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _etablissements_propres(db_session, seconde_base)
    etab = cas.sites_a[0]
    async with client_http() as c:
        r = await c.post(f"{RACINE}/{etab}/ruptures", json={"code_caisse": "TIRA-1", "disponible": False}, headers=_cle(cas.cle_a))
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True, "poussee_a_la_caisse": False}
        inconnu = await c.post(f"{RACINE}/{etab}/ruptures", json={"code_caisse": "N-EXISTE-PAS", "disponible": False}, headers=_cle(cas.cle_a))
        assert inconnu.status_code == 404
        for mauvais in ({"code_caisse": "", "disponible": False}, {"code_caisse": "X"}, {"code_caisse": "TIRA-1", "disponible": False, "en_trop": 1},
                        {"code_caisse": "TIRA-1", "disponible": False, "fin": (datetime.now(UTC) - timedelta(days=1)).isoformat()}):
            assert (await c.post(f"{RACINE}/{etab}/ruptures", json=mauvais, headers=_cle(cas.cle_a))).status_code in (422,)
    base = await schema.connecter(cas.base_a)
    try:
        assert {r["code_caisse"] for r in await restauration.ruptures_du_restaurant(base, etab)} == {"TIRA-1"}
    finally:
        await base.close()
    assert ("rupture.changee", {"code_caisse": "TIRA-1", "disponible": False}) in await _evenements(cas.a, etab)


async def test_la_rupture_est_poussee_en_patch_et_une_panne_se_voit_sans_perdre_la_rupture(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas = await _etablissements_propres(db_session, seconde_base)
    etab = cas.sites_a[0]
    await _brancher(cas, etab, cas.a, cas.base_a, _caisse_enregistree(pdv="pdv-rupture-" + str(cas.a)), cas.admin.id)
    base = await schema.connecter(cas.base_a)
    try:
        ok = _caisse_enregistree()
        resultat, poussee = await service_caisse.poser_la_rupture(base, cas.a, etab, "TIRA-1", True, None, nom_base=cas.base_a, transport=ok)
        assert resultat.statut == "OK" and poussee is True
        envoi = [r for r in ok.demandes if r.method == "PATCH"][0]
        assert envoi.url.path == "/v1/catalogs/3pmq9/locations/pdv-rupture-%d/inventory" % cas.a and json.loads(envoi.content) == [{"sku_ref": "TIRA-1", "stock": None}]
        # la caisse tombe : posée chez nous, pas poussée, la liaison le dit par un code
        panne = _caisse_enregistree(callback="panne")
        fin = datetime.now(UTC) + timedelta(hours=3)
        resultat, poussee = await service_caisse.poser_la_rupture(base, cas.a, etab, "TIRA-1", False, fin, nom_base=cas.base_a, transport=panne)
        assert resultat.statut == "OK" and poussee is False
        assert {r["code_caisse"] for r in await restauration.ruptures_du_restaurant(base, etab)} >= {"TIRA-1"}
        liaison = await lia.liaison(base, etab)
        assert (liaison["etat"], liaison["derniere_erreur"]) == ("erreur", "caisse_injoignable")
        # jeton refusé : la liaison est rompue
        refuse = _caisse_enregistree(callback="jeton_faux")
        _, poussee = await service_caisse.poser_la_rupture(base, cas.a, etab, "TIRA-1", True, None, nom_base=cas.base_a, transport=refuse)
        assert poussee is False and (await lia.liaison(base, etab))["etat"] == "rompue"
    finally:
        await base.close()
    types = [t for t, _ in await _evenements(cas.a, etab)]
    assert types.count("rupture.changee") >= 3 and "caisse.liaison" in types
