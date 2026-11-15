"""[.mark] Module Restauration, lot 9, étape 5 : la réception des messages signés de HubRise et leur traitement.

Vraie authentification (aucune : la route est sans session, gardée par la signature), vraies bases de clients, vrai Redis ; la caisse est un transport ENREGISTRÉ.

| Test | Ce qu'il prouve |
|---|---|
| signature | HMAC-SHA256 du corps BRUT ; fausse, absente, d'un autre corps ou d'un autre secret : refusée (éprouvé sur un cas rouge connu) |
| route | signature fausse : 401 et rien en file ; bonne : 200 et UN travail par message ; trop gros : 413 ; limite de débit : 429 ; sans configuration : 503 ; corps illisible : accusé sans travail |
| statut | « accepted » de la caisse fait avancer NOTRE commande par le chemin fermé (source « caisse », événement émis, ``ref_fournisseur`` écrit) ; refusée : ``refusee`` |
| rejeu | le même message traité deux fois : un seul effet, un seul événement ; un message en retard ne fait jamais reculer une commande |
| cloisonnement | le message d'un établissement (ou d'une autre organisation) n'écrit jamais chez un autre ; un point de vente inconnu est ignoré |
| échec | une caisse muette : le message n'est pas perdu (oublié, repris), la liaison le dit par un code ; rétablie, la reprise le traite |
| carte, ruptures, état | les trois messages relisent la caisse et versent dans le classeur ; ``caisse.etat`` émis seulement si l'état change |
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import httpx
import pytest
import redis.asyncio as aioredis

from api.constants import REDIS_URL
from api.db.bases_clients import connexion as schema
from api.db.bases_clients import restauration
from api.db.bases_clients import restauration_liaison as lia
from api.routes import restauration_caisse as routes_caisse
from api.services.restauration.prises import hubrise_reception as hr
from api.tests.mark.equipe_commun import client_http, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import seconde_base  # noqa: F401
from api.tests.mark.test_restauration_caisse_routes import (  # noqa: F401
    _brancher,
    _caisse_enregistree,
    _corps,
    _etablissements_propres,
    _evenements,
    application_configuree,
)

SECRET = "secret-de-notre-application"
RAPPEL = "/api/v1/restauration/caisse/hubrise/rappel"


def _signer(corps: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()


def _message(id_: str, **plus) -> dict:
    return {"id": id_, "resource_type": "order", "event_type": "update", "location_id": "w8xvp-0", "order_id": "8qknnxn", **plus}


# --------------------------------------------------------------------------- la signature et la route


def test_la_signature_est_celle_du_corps_brut_avec_le_secret_de_l_application():
    corps = b'{"id":"m1","resource_type":"order"}'
    assert hr.signature_valide(corps, _signer(corps), SECRET)
    assert hr.signature_valide(corps, _signer(corps).upper(), SECRET)
    for mauvaise in (None, "", "abc", _signer(corps + b" "), _signer(corps, "autre-secret"), "é" * 64):
        assert not hr.signature_valide(corps, mauvaise, SECRET), mauvaise
    assert not hr.signature_valide(corps + b" ", _signer(corps), SECRET)  # le corps a changé : la signature ne couvre plus


async def test_la_route_refuse_une_fausse_signature_et_met_un_travail_par_message_en_file(monkeypatch, application_configuree):  # noqa: F811
    mises = []

    async def enqueue(nom, message, **options):
        mises.append((nom, message["id"], options["_job_id"]))

    import api.tasks.arq as arq

    monkeypatch.setattr(arq, "enqueue_job", enqueue)
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    for cle in await redis.keys("mark:resto:hubrise:debit:*"):
        await redis.delete(cle)
    await redis.aclose()
    corps = json.dumps(_message("m-route-1")).encode()
    async with client_http() as c:
        for entetes in ({}, {"X-HubRise-Hmac-SHA256": "0" * 64}, {"X-HubRise-Hmac-SHA256": _signer(corps, "autre")}):
            assert (await c.post(RAPPEL, content=corps, headers=entetes)).status_code == 401
        assert mises == []  # rien en file pour un message non signé
        ok = await c.post(RAPPEL, content=corps, headers={"X-HubRise-Hmac-SHA256": _signer(corps)})
        assert ok.status_code == 200 and ok.json() == {"ok": True}
        await c.post(RAPPEL, content=corps, headers={"X-HubRise-Hmac-SHA256": _signer(corps)})  # HubRise renvoie : même identifiant de travail
        illisible = b"pas du json"
        r = await c.post(RAPPEL, content=illisible, headers={"X-HubRise-Hmac-SHA256": _signer(illisible)})
        assert r.status_code == 200 and r.json()["ignore"] is True
        gros = b"x" * (hr.TAILLE_MAX_OCTETS + 1)
        assert (await c.post(RAPPEL, content=gros, headers={"X-HubRise-Hmac-SHA256": _signer(gros)})).status_code == 413
    assert [m[1] for m in mises] == ["m-route-1", "m-route-1"] and {m[2] for m in mises} == {"hubrise-m-route-1"} and mises[0][0] == hr.NOM_TACHE


async def test_la_limite_de_debit_et_l_absence_de_configuration(monkeypatch, application_configuree):  # noqa: F811
    async def enqueue(*a, **k):
        return None

    import api.tasks.arq as arq

    monkeypatch.setattr(arq, "enqueue_job", enqueue)
    monkeypatch.setattr(routes_caisse, "LIMITE_PAR_MINUTE", 2)
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    for cle in await redis.keys("mark:resto:hubrise:debit:*"):
        await redis.delete(cle)
    await redis.aclose()
    async with client_http() as c:
        codes = []
        for i in range(4):
            corps = json.dumps(_message(f"m-debit-{i}", location_id="pdv-debit")).encode()
            codes.append((await c.post(RAPPEL, content=corps, headers={"X-HubRise-Hmac-SHA256": _signer(corps)})).status_code)
        assert codes == [200, 200, 429, 429]
    monkeypatch.delenv("HUBRISE_CLIENT_SECRET")
    async with client_http() as c:
        assert (await c.post(RAPPEL, content=b"{}", headers={"X-HubRise-Hmac-SHA256": "0" * 64})).status_code == 503


# --------------------------------------------------------------------------- le traitement


async def _commande_envoyee(base: str, etab: int, ref: str | None = None, statut: str = "envoyee", numero: str | None = None) -> str:
    numero = numero or str(uuid.uuid4())
    c = await schema.connecter(base)
    try:
        await c.execute(
            "INSERT INTO mark.resto_commande (numero, numero_court, site_id, mode, total, statut, ref_fournisseur) VALUES ($1, 'C1', $2, 'emporter', 1900, $3, $4)",
            uuid.UUID(numero), etab, statut, ref,
        )
    finally:
        await c.close()
    return numero


async def _statut(base: str, numero: str) -> str:
    c = await schema.connecter(base)
    try:
        return await c.fetchval("SELECT statut FROM mark.resto_commande WHERE numero = $1", uuid.UUID(numero))
    finally:
        await c.close()


def _ordre(fichier: str, **plus) -> dict:
    return {**_corps(fichier), **plus}


async def _etablissement_branche(db_session, seconde_base, pdv: str):  # noqa: F811
    cas = await _etablissements_propres(db_session, seconde_base)
    etab = cas.sites_a[0]
    await _brancher(cas, etab, cas.a, cas.base_a, _caisse_enregistree(pdv=pdv), cas.admin.id)
    return cas, etab


async def test_un_statut_de_la_caisse_fait_avancer_notre_commande_une_seule_fois(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    pdv = "pdv-statut-" + uuid.uuid4().hex[:6]
    cas, etab = await _etablissement_branche(db_session, seconde_base, pdv)
    numero = await _commande_envoyee(cas.base_a, etab)
    caisse = _caisse_enregistree(pdv=pdv, ordres={"8qknnxn": _ordre("21-commande-acceptee.json", private_ref=numero)})
    message = _message("m-statut-1", location_id=pdv)
    assert (await hr.traiter_le_message(None, message, transport=caisse))["effet"] == "statut"
    assert await _statut(cas.base_a, numero) == "acceptee"
    base = await schema.connecter(cas.base_a)
    try:
        assert (await lia.etat_de_la_commande(base, etab, numero))["ref_fournisseur"] == "8qknnxn"
        journal = await base.fetchrow("SELECT source FROM mark.resto_journal WHERE objet = 'resto_commande' AND ligne_id = $1 ORDER BY id DESC LIMIT 1", numero)
        assert journal["source"] == "caisse"
    finally:
        await base.close()
    evenements = [d for t, d in await _evenements(cas.a, etab) if t == "commande.statut"]
    assert evenements == [{"numero": numero, "de": "envoyee", "vers": "acceptee", "source": "caisse"}]
    # le même message rejoué : un seul effet, un seul événement, la caisse n'est pas relue
    nb = len(caisse.demandes)
    assert (await hr.traiter_le_message(None, message, transport=caisse))["statut"] == "deja_vu"
    assert len(caisse.demandes) == nb and len([1 for t, _ in await _evenements(cas.a, etab) if t == "commande.statut"]) == 1


async def test_un_message_en_retard_ne_fait_pas_reculer_et_un_refus_est_pris(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    pdv = "pdv-retard-" + uuid.uuid4().hex[:6]
    cas, etab = await _etablissement_branche(db_session, seconde_base, pdv)
    prete = await _commande_envoyee(cas.base_a, etab, ref="8qknnxn", statut="prete")
    caisse = _caisse_enregistree(pdv=pdv, ordres={"8qknnxn": _ordre("21-commande-acceptee.json", private_ref=prete)})
    assert (await hr.traiter_le_message(None, _message("m-retard-1", location_id=pdv), transport=caisse))["effet"] == "inchange"
    assert await _statut(cas.base_a, prete) == "prete"  # « accepted » arrivé après « prête » : jamais en arrière
    refusee = await _commande_envoyee(cas.base_a, etab, ref="refus-1")
    caisse = _caisse_enregistree(pdv=pdv, ordres={"refus-1": _ordre("22-commande-refusee.json", id="refus-1", private_ref=refusee)})
    await hr.traiter_le_message(None, _message("m-refus-1", location_id=pdv, order_id="refus-1"), transport=caisse)
    assert await _statut(cas.base_a, refusee) == "refusee"


async def test_un_message_n_ecrit_jamais_chez_un_autre_etablissement_ni_une_autre_organisation(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    pdv_a, pdv_b = "pdv-a-" + uuid.uuid4().hex[:6], "pdv-b-" + uuid.uuid4().hex[:6]
    cas = await _etablissements_propres(db_session, seconde_base)
    await _brancher(cas, cas.sites_a[0], cas.a, cas.base_a, _caisse_enregistree(pdv=pdv_a), cas.admin.id)
    await _brancher(cas, cas.sites_b[0], cas.b, cas.base_b, _caisse_enregistree(pdv=pdv_b), cas.admin.id)
    numero_de_a = await _commande_envoyee(cas.base_a, cas.sites_a[0])
    voisine = await _commande_envoyee(cas.base_a, cas.sites_a[1])  # l'AUTRE établissement de la même organisation
    # le point de vente de B nomme (par erreur ou par malice) la commande de A, et la caisse de B la dit « acceptée »
    caisse_b = _caisse_enregistree(pdv=pdv_b, ordres={"8qknnxn": _ordre("21-commande-acceptee.json", private_ref=numero_de_a)})
    await hr.traiter_le_message(None, _message("m-croise-1", location_id=pdv_b), transport=caisse_b)
    assert await _statut(cas.base_a, numero_de_a) == "envoyee"
    # le point de vente de A nomme la commande de l'établissement voisin : rien non plus
    caisse_a = _caisse_enregistree(pdv=pdv_a, ordres={"8qknnxn": _ordre("21-commande-acceptee.json", private_ref=voisine)})
    assert (await hr.traiter_le_message(None, _message("m-croise-2", location_id=pdv_a), transport=caisse_a))["effet"] == "commande_de_la_caisse"
    assert await _statut(cas.base_a, voisine) == "envoyee"
    # un point de vente inconnu : ignoré, jamais traité
    inconnu = _caisse_enregistree()
    assert (await hr.traiter_le_message(None, _message("m-inconnu", location_id="pdv-inconnu"), transport=inconnu))["statut"] == "point_de_vente_inconnu"
    assert inconnu.demandes == []


async def test_une_caisse_muette_ne_perd_pas_le_message_et_la_reprise_le_traite(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    from arq import Retry

    pdv = "pdv-muet-" + uuid.uuid4().hex[:6]
    cas, etab = await _etablissement_branche(db_session, seconde_base, pdv)
    numero = await _commande_envoyee(cas.base_a, etab, ref="8qknnxn")
    muette = httpx.MockTransport(lambda r: httpx.Response(500, json={}))
    message = _message("m-muet-1", location_id=pdv)
    resultat = await hr.traiter_le_message(None, message, transport=muette)
    assert resultat == {"statut": "echec", "code": "caisse_injoignable"}
    base = await schema.connecter(cas.base_a)
    try:
        liaison = await lia.liaison(base, etab)
        assert (liaison["etat"], liaison["derniere_erreur"]) == ("erreur", "caisse_injoignable")
        assert await base.fetchval("SELECT count(*) FROM mark.resto_message_recu WHERE identifiant = 'm-muet-1'") == 0  # oublié : la reprise le verra neuf
    finally:
        await base.close()
    with pytest.raises(Retry):  # dans arq, une nouvelle tentative espacée
        await hr.traiter_le_message({"job_try": 1}, {**message, "id": "m-muet-2"}, transport=muette)
    caisse = _caisse_enregistree(pdv=pdv, ordres={"8qknnxn": _ordre("21-commande-acceptee.json", private_ref=numero)})
    assert (await hr.traiter_le_message(None, message, transport=caisse))["statut"] == "traite"
    assert await _statut(cas.base_a, numero) == "acceptee"


async def test_carte_ruptures_et_etat_sont_relus_et_caisse_etat_n_est_emis_que_s_il_change(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    pdv = "pdv-relu-" + uuid.uuid4().hex[:6]
    cas, etab = await _etablissement_branche(db_session, seconde_base, pdv)
    avant = len([1 for t, _ in await _evenements(cas.a, etab) if t == "caisse.etat"])
    # la caisse repasse en « normal » : l'état change, un événement
    normal = _caisse_enregistree(pdv=pdv, etat="08-point-de-vente-normal.json")
    assert (await hr.traiter_le_message(None, {"id": "m-loc-1", "resource_type": "location", "event_type": "update", "location_id": pdv}, transport=normal))["effet"] == "etat"
    # le même état relu : rien de changé, aucun événement de plus
    assert (await hr.traiter_le_message(None, {"id": "m-loc-2", "resource_type": "location", "event_type": "update", "location_id": pdv}, transport=normal))["effet"] == "etat_inchange"
    base = await schema.connecter(cas.base_a)
    try:
        assert (await restauration.etat_caisse(base, etab))["mode"] == "normal"
        for code in ("TIRA-1", "SUPP-OEUF"):
            await restauration.poser_rupture(base, etab, code, True, None, "caisse")  # levées : l'inventaire en remet
    finally:
        await base.close()
    r = await hr.traiter_le_message(None, {"id": "m-inv-1", "resource_type": "inventory", "event_type": "patch", "location_id": pdv}, transport=normal)
    assert r["effet"].startswith("ruptures:")
    base = await schema.connecter(cas.base_a)
    try:
        assert {"TIRA-1", "SUPP-OEUF"} & {x["code_caisse"] for x in await restauration.ruptures_du_restaurant(base, etab)}
    finally:
        await base.close()
    assert (await hr.traiter_le_message(None, {"id": "m-cat-1", "resource_type": "catalog", "event_type": "update", "location_id": pdv}, transport=normal))["effet"] == "carte"
    assert (await hr.traiter_le_message(None, {"id": "m-cli-1", "resource_type": "customer", "event_type": "update", "location_id": pdv}, transport=normal))["effet"] == "ignore"
    apres = len([1 for t, _ in await _evenements(cas.a, etab) if t == "caisse.etat"])
    assert apres == avant + 1
