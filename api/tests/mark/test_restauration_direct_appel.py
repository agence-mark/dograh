"""[.mark] Module Restauration, lot 21 : le direct des appels, branché sur le déroulé réel de l'appel.

Vraies bases de clients, vrai Redis. Les événements sont ceux que l'observateur de l'amont envoie au canal de l'appel (``rtf-*``), jamais un appel réel.

| Test | Ce qu'il prouve |
|---|---|
| déroulé | ``appel.commence`` (numéro masqué), les tours FINAUX seulement (jamais le provisoire), ce que dit l'agent, l'outil appelé puis terminé, ``appel.fini`` : dans l'ordre, dans le flux de l'établissement de l'appel |
| motif | une commande de CET appel : « Commande » ; une réservation : « Réservation » ; l'appelant a parlé sans rien commander : « Question » ; personne n'a parlé : « Abandonné » ; la commande d'un autre appel ne compte pas |
| coupure | l'appel annulé en plein vol quitte quand même « en cours » (``appel.fini``), une seule fois, même si la fin est appelée deux fois |
| cloisonnement | l'appel d'une organisation n'écrit jamais dans le flux d'une autre, ni d'un autre établissement ; le numéro n'est jamais en clair |
| rapidité | de l'événement du pipeline à l'événement lisible dans le flux : moins de 2 secondes (mesuré) |
| canal | le canal de l'amont est composé, jamais remplacé : il reçoit chaque événement tel quel, et ce qu'il lève, il le lève comme avant ; notre part ne lève jamais |
| panne | un flux en panne : l'appel continue, la fin se fait quand même, rien ne lève |
| module | un agent sans le module, un établissement inconnu, une base absente : pas de direct (l'appel est celui d'avant) |
| branchement | ``run_pipeline`` prépare le direct APRÈS le canal de l'amont et le ferme dans le ``finally`` final ; aucun fichier de Pipecat n'est touché |
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path

import pytest
import redis.asyncio as aioredis

from api.constants import REDIS_URL
from api.db.bases_clients import connexion as schema
from api.services.restauration import direct_appel as direct
from api.services.restauration import flux
from api.tests.mark.equipe_commun import sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import seconde_base  # noqa: F401
from api.tests.mark.test_restauration_caisse_routes import _evenements
from api.tests.mark.test_restauration_flux import _deux_organisations_avec_des_etablissements

TEL = "+33612345678"
SWITCH = {"commande_sur_catalogue": True}


def _evt(type_: str, **payload):
    return {"type": type_, "payload": payload}


def _tour_appelant(texte: str, final: bool = True):
    return _evt("rtf-user-transcription", text=texte, final=final)


async def _direct(cas, run: int = 4242, *, base=None, etab=None, org=None) -> direct.DirectDeLAppel:
    org, base, etab = org or cas.a, base or cas.base_a, etab or cas.sites_a[0]
    return direct.DirectDeLAppel(org, etab, base, 77, run, TEL)


async def _vider(cas):
    flux._redis = None
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        for cle in await r.keys("mark:resto:flux:*"):
            await r.delete(cle)
    finally:
        await r.aclose()
    flux._redis = None


async def test_le_deroule_de_l_appel_va_dans_le_flux_de_son_etablissement_final_seulement(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    d = await _direct(cas)
    d.commencer()
    for e in (
        _tour_appelant("Bonjour je voudrais", final=False), _tour_appelant("Bonjour je voudrais une pizza", final=True),
        _evt("rtf-bot-text", text="Bien sûr, laquelle ?"), _evt("rtf-function-call-start", function_name="chercher", tool_call_id="1", arguments={}),
        _evt("rtf-function-call-end", function_name="chercher", tool_call_id="1", result={}), _evt("rtf-latency-measured", latency_seconds=1.2), _evt("rtf-node-transition"),
        _tour_appelant("   ", final=True),
    ):
        d.sur_evenement(e)
    await d.fermer()
    evenements = await _evenements(cas.a, cas.sites_a[0])
    assert [t for t, _ in evenements] == ["appel.commence", "appel.tour", "appel.tour", "appel.outil", "appel.outil", "appel.fini"]
    assert evenements[0][1] == {"appel_id": "4242", "agent_id": "77", "telephone_masque": "+33 6 ** ** ** 78"}
    assert [(x["role"], x["texte"]) for t, x in evenements if t == "appel.tour"] == [("appelant", "Bonjour je voudrais une pizza"), ("agent", "Bien sûr, laquelle ?")]
    assert [x["statut"] for t, x in evenements if t == "appel.outil"] == ["appele", "termine"]
    assert evenements[-1][1] == {"appel_id": "4242", "motif": "Question"}
    assert TEL not in json.dumps(evenements) and "12345678" not in json.dumps(evenements)


async def _ligne(base: str, requete: str, *args):
    c = await schema.connecter(base)
    try:
        await c.execute(requete, *args)
    finally:
        await c.close()


async def test_le_motif_se_lit_dans_le_classeur_pour_cet_appel_seulement(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    await _ligne(cas.base_a, "INSERT INTO mark.resto_commande (numero, numero_court, site_id, mode, total, statut, appel_id) VALUES ($1, 'C1', $2, 'emporter', 1000, 'nouvelle', '501')", uuid.uuid4(), etab)
    await _ligne(cas.base_a, "INSERT INTO mark.resto_reservation (numero, site_id, debut, duree_minutes, couverts, appel_id) VALUES (gen_random_uuid(), $1, now(), 60, 2, '502')", etab)
    attendu = {501: "Commande", 502: "Réservation", 503: "Question", 504: "Abandonné"}
    for run, motif in attendu.items():
        d = await _direct(cas, run)
        if run == 503:
            d.sur_evenement(_tour_appelant("Allô ?"))
        await d.fermer()
        fini = [x for t, x in await _evenements(cas.a, etab) if t == "appel.fini" and x["appel_id"] == str(run)]
        assert [x["motif"] for x in fini] == [motif], run
    # la commande de l'appel 501 ne rend pas « Commande » pour l'appel 505 : l'identifiant d'appel fait foi
    d = await _direct(cas, 505)
    await d.fermer()
    assert [x["motif"] for t, x in await _evenements(cas.a, etab) if t == "appel.fini" and x["appel_id"] == "505"] == ["Abandonné"]


async def test_un_passage_de_main_pour_une_plainte_fait_une_reclamation(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    from api.services.integrations.connectors import mesures

    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    attendu = {601: ("plainte", "Réclamation"), 602: ("probleme_reel", "Question"), 603: (None, "Question")}
    for run, (motif, reponse) in attendu.items():
        fiche: dict = {}
        if motif:
            assert mesures.ecrire(fiche, "service.passage_de_main", "service.passage_de_main", motif)
        d = await _direct(cas, run)
        d.sur_evenement(_tour_appelant("Allô ?"))
        await d.fermer(fiche)
        fini = [x for t, x in await _evenements(cas.a, etab) if t == "appel.fini" and x["appel_id"] == str(run)]
        assert [x["motif"] for x in fini] == [reponse], run
    # sans fiche (un essai isolé), rien ne se lit : la lecture d'avant
    d = await _direct(cas, 604)
    await d.fermer(None)
    assert [x["motif"] for t, x in await _evenements(cas.a, etab) if t == "appel.fini" and x["appel_id"] == "604"] == ["Abandonné"]


async def test_un_appel_coupe_en_plein_vol_quitte_quand_meme_en_cours_une_seule_fois(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    d = await _direct(cas, 600)
    d.commencer()

    async def appel():  # ce que fait ``run_pipeline`` : le direct se ferme dans le ``finally``
        try:
            d.sur_evenement(_tour_appelant("Bonjour"))
            await asyncio.sleep(30)
        finally:
            await d.fermer()

    tache = asyncio.create_task(appel())
    await asyncio.sleep(0.2)
    tache.cancel()
    with pytest.raises(asyncio.CancelledError):
        await tache
    await d.fermer()  # appelée deux fois : rien de plus
    types = [t for t, x in await _evenements(cas.a, cas.sites_a[0]) if x["appel_id"] == "600"]
    assert types == ["appel.commence", "appel.tour", "appel.fini"]


async def test_l_appel_d_une_organisation_n_ecrit_jamais_chez_une_autre(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    await _vider(cas)
    d = await _direct(cas, 700)
    d.commencer()
    d.sur_evenement(_evt("rtf-bot-text", text="Phrase de A"))
    await d.fermer()
    assert [t for t, _ in await _evenements(cas.a, cas.sites_a[0])] == ["appel.commence", "appel.tour", "appel.fini"]
    for org, etab in ((cas.a, cas.sites_a[1]), (cas.b, cas.sites_b[0]), (cas.b, cas.sites_b[1])):
        assert await _evenements(org, etab) == [], (org, etab)  # ni un autre établissement, ni l'autre organisation, même à numéro d'établissement égal


async def test_de_l_evenement_du_pipeline_au_flux_en_moins_de_2_secondes(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    d = await _direct(cas, 800)
    mesures = []
    for i in range(5):
        avant = time.perf_counter()
        d.sur_evenement(_evt("rtf-bot-text", text=f"Phrase {i}"))
        while True:
            vus = [x for t, x in await _evenements(cas.a, cas.sites_a[0]) if t == "appel.tour" and x["texte"] == f"Phrase {i}"]
            if vus or time.perf_counter() - avant > 5:
                break
            await asyncio.sleep(0.01)
        mesures.append(time.perf_counter() - avant)
        assert vus
    await d.fermer()
    assert max(mesures) < 2.0, mesures


async def test_le_canal_de_l_amont_est_compose_jamais_remplace(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    d = await _direct(cas, 900)
    recus = []

    async def amont(message):
        recus.append(message)

    envoyer = d.composer(amont)
    message = _tour_appelant("Bonjour")
    await envoyer(message)
    assert recus == [message]  # l'amont reçoit l'événement tel quel, avec ou sans notre part
    sans_amont = d.composer(None)
    await sans_amont(_evt("rtf-bot-text", text="Seul"))  # pas de navigateur au bout : le canal n'existait pas, le nôtre suffit

    async def casse(_message):
        raise RuntimeError("l'amont casse")

    with pytest.raises(RuntimeError):
        await d.composer(casse)(_evt("rtf-bot-text", text="Encore"))  # ce que lève l'amont, il le lève comme avant
    d.sur_evenement({"type": None, "payload": None})  # un événement illisible : rien, jamais d'exception
    d.sur_evenement({})
    await d.fermer()
    textes = [x["texte"] for t, x in await _evenements(cas.a, cas.sites_a[0]) if t == "appel.tour" and x["appel_id"] == "900"]
    assert textes == ["Bonjour", "Seul", "Encore"]


async def test_un_flux_en_panne_ne_casse_ni_l_appel_ni_sa_fin(db_session, seconde_base, sans_preparation_des_organisations, monkeypatch):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)

    async def en_panne(*a, **k):
        raise ConnectionError("Redis est tombé")

    monkeypatch.setattr(flux, "_ecrire", en_panne)
    d = await _direct(cas, 1000)
    d.commencer()
    d.sur_evenement(_evt("rtf-bot-text", text="Bonjour"))
    await asyncio.wait_for(d.fermer(), 10)  # rend la main, sans lever


async def test_sans_le_module_ou_sans_etablissement_il_n_y_a_pas_de_direct(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    from api.tests.mark.test_restauration_caisse_routes import _etablissements_propres  # noqa: F401

    async def preparer(**plus):
        base = dict(organisation_id=cas.a, workflow_id=77, workflow_run_id=1100, run_configs=SWITCH, cle_etablissement="un", contexte={"caller_number": TEL})
        return await direct.preparer_le_direct(**{**base, **plus})

    await _ligne(cas.base_a, "INSERT INTO mark.resto_reglage (site_id, module_actif) VALUES ($1, false)", cas.sites_a[0])
    assert await preparer() is None  # le module Restauration n'est pas allumé pour cet établissement
    await _ligne(cas.base_a, "UPDATE mark.resto_reglage SET module_actif = true WHERE site_id = $1", cas.sites_a[0])
    assert await preparer(run_configs={"commande_sur_catalogue": False}) is None  # l'agent n'a pas le module de commande
    assert await preparer(cle_etablissement=None) is None and await preparer(cle_etablissement="inconnu") is None  # établissement inconnu de la base
    assert await preparer(organisation_id=None) is None and await preparer(organisation_id=999_999_999) is None  # pas de base rattachée
    present = await preparer()  # le module, un établissement connu, une base rattachée : le direct existe
    assert present is not None and present.etablissement_id == cas.sites_a[0] and present.telephone == TEL
    await present.fermer()
    sans_numero = await preparer(contexte=None)
    assert sans_numero is not None and sans_numero.telephone is None
    await sans_numero.fermer()


def test_run_pipeline_prepare_le_direct_apres_le_canal_de_l_amont_et_le_ferme_dans_le_finally_final():
    racine = Path(direct.__file__).resolve().parents[2]
    source = (racine / "services" / "pipecat" / "run_pipeline.py").read_text(encoding="utf-8")
    assert source.count("preparer_le_direct(") == 1 and source.count("direct_restauration.fermer(") == 1
    i_canal, i_direct, i_composer = source.index("ws_sender = get_ws_sender(workflow_run_id)"), source.index("preparer_le_direct("), source.index("direct_restauration.composer(ws_sender)")
    assert i_canal < i_direct < i_composer
    i_fin = source.index("direct_restauration.fermer(")
    assert source.rindex("    finally:\n", 0, i_fin) > source.index("await run_worker_runner(worker_runner, task)")  # le dernier ``finally``, celui qui suit la boucle de l'appel
    # R9 : ce lot ne touche pas Pipecat (aucun import ni appel de la bibliothèque dans le service du direct)
    assert "import pipecat" not in Path(direct.__file__).read_text(encoding="utf-8") and "from pipecat" not in Path(direct.__file__).read_text(encoding="utf-8")
