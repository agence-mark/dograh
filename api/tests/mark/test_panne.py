"""[.mark] Non-regression test for the outage fallback (chantier l-agent-travaille, L7; plan
panne-vers-magasin, PN1 to PN8).

The questions this file answers:

    When a part of the agent fails on an inbound Twilio call, does the live call get Twilio's
    own voice and the second number of the establishment when it is open, the call-back promise
    with the reopening date when it is closed (or forced closed, or without a second number), an
    apology on an outbound call? Is that decided ONCE, whatever fails next? Does the serializer
    leave a handed-over call alone, and still hang up every other call? Is the run marked
    (``panne``, ``panne_technique``, event for Incidents) and the alert sent? Does the result of
    the ringing answer with the prepared promise, and refuse a request Twilio did not sign? Does
    the inbound instruction redirect to the TwiML Bin only for an agent that switched it on
    (word for word the 40 s pause otherwise)? Does the model's delay give « Un instant » then the
    fallback, and the voice's delay the fallback? Does a call lost by an outage always make its
    request « to call back »? Does the catch-up from Twilio's call log create each request once?

The Twilio is a stand-in (``httpx.MockTransport``): no request leaves the machine, no number is
touched.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

import httpx
import pytest

from api.schemas.panne import DEFAUT_RENVOI, PanneAgent, ReglagesPanne
from api.services.panne import consigne, raccroche, rattrapage
from api.services.panne import twilio as client_twilio
from api.services.panne.declencheurs import ObservateurVoixLente, sur_erreur_terminale
from api.services.panne.delai_modele import (
    DelaiModeleDepasse,
    FluxAvecDelai,
    ReplisDelaiModele,
)
from api.services.panne.gardien import ContextePanne, GardienPanne

PARIS = ZoneInfo("Europe/Paris")
HORAIRES = chr(10).join(
    [
        *(
            f"{j} : 9h-12h, 14h-18h"
            for j in ("lundi", "mardi", "mercredi", "jeudi", "vendredi")
        ),
        "samedi : fermé",
        "dimanche : fermé",
    ]
)


class FauxTwilio:
    def __init__(self, appels=None, statut=200):
        self.recus: list[dict] = []
        self.appels = appels or []
        self.statut = statut

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        corps = (
            {k: v[0] for k, v in parse_qs(requete.content.decode()).items()}
            if requete.content
            else {}
        )
        self.recus.append(
            {
                "methode": requete.method,
                "chemin": requete.url.path,
                "params": dict(requete.url.params),
                **corps,
            }
        )
        if self.statut >= 400:
            return httpx.Response(self.statut)
        if requete.url.path.endswith("/Calls.json"):
            return httpx.Response(
                200, json={"calls": self.appels, "next_page_uri": None}
            )
        if requete.url.path.endswith("/IncomingPhoneNumbers.json"):
            return httpx.Response(
                200, json={"incoming_phone_numbers": [{"sid": "PN1"}]}
            )
        return httpx.Response(200, json={"sid": "CA1"})


@pytest.fixture
def twilio():
    faux = FauxTwilio()
    with patch.object(
        client_twilio,
        "nouveau_client",
        lambda **o: httpx.AsyncClient(transport=httpx.MockTransport(faux), **o),
    ):
        yield faux


class Journal:
    def __init__(self):
        self.evenements = []

    async def append(self, e):
        self.evenements.append(e)


def _engine(variables=None):
    engine = SimpleNamespace(
        _gathered_context={"extracted_variables": {}},
        _call_context_vars=variables or {},
        journal_du_run=Journal(),
    )
    engine.dispositions = []
    engine.set_call_disposition = lambda d: (
        engine.dispositions.append(d),
        engine._gathered_context.__setitem__("call_disposition", d),
    )
    return engine


def _gardien(
    engine,
    *,
    entrant=True,
    call_sid="CAessai",
    reglages_annonce=None,
    second="+33344000000",
):
    ctx = ContextePanne(
        run_id=7,
        organization_id=1,
        workflow_id=3,
        reglages=PanneAgent(actif=True),
        entrant=entrant,
        call_sid=call_sid,
        run=SimpleNamespace(initial_context={}),
        url_resultat="https://dograh.example.org/api/v1/telephony/twilio/panne/7/resultat",
        reglages_annonce=reglages_annonce,
    )
    servi = (
        SimpleNamespace(etablissement=SimpleNamespace(second_numero=second))
        if second
        else None
    )
    patches = [
        patch(
            "api.services.etablissements.appel.etablissement_de_lappel",
            AsyncMock(return_value=servi),
        ),
        patch(
            "api.services.telephony.factory.get_telephony_provider_for_run",
            AsyncMock(
                return_value=SimpleNamespace(
                    account_sid="ACessai", auth_token="jeton-twilio-0123456789"
                )
            ),
        ),
        patch(
            "api.services.apres_appel.notification.notifier",
            AsyncMock(return_value=["alerte@example.org"]),
        ),
    ]
    return GardienPanne(ctx, engine), patches


async def _declencher(gardien, patches, *args):
    for p in patches:
        p.start()
    try:
        decision = await gardien.declencher(*args)
        await asyncio.sleep(0)  # the alert task
        return decision
    finally:
        for p in patches:
            p.stop()


def _a(jour: str, heure: str) -> datetime:
    return datetime.fromisoformat(f"{jour}T{heure}").replace(tzinfo=PARIS)


# --------------------------------------------------------------------------- #
# 1. The decision and the instruction (PN1, PN4, P6)
# --------------------------------------------------------------------------- #


async def test_ouvert_renvoi_vers_le_second_numero_une_seule_fois(twilio):
    engine = _engine({"caller_number": "+33612345678", "horaires_ouverture": HORAIRES})
    gardien, patches = _gardien(engine)
    with patch.object(
        GardienPanne, "_etat", lambda self, maintenant=None: ("OUVERT", "")
    ):
        assert (
            await _declencher(
                gardien, patches, "erreur_terminale", "voix", "invalid key"
            )
            == "renvoi"
        )
        assert (
            await _declencher(gardien, patches, "voix_lente", "voix") == "renvoi"
        )  # once per call
    assert len(twilio.recus) == 1
    envoi = twilio.recus[0]
    assert envoi["chemin"] == "/2010-04-01/Accounts/ACessai/Calls/CAessai.json"
    twiml = envoi["Twiml"]
    assert 'voice="Polly.Lea-Neural"' in twiml and DEFAUT_RENVOI in twiml
    assert (
        '<Dial timeout="20" action="https://dograh.example.org/api/v1/telephony/twilio/panne/7/resultat"'
        in twiml
    )
    assert "<Number>+33344000000</Number>" in twiml
    trace = engine._gathered_context["panne"]
    assert (
        trace["decision"] == "renvoi"
        and trace["a_rappeler"] == "+33612345678"
        and trace["consigne_rappel"]
    )
    assert engine.dispositions == ["panne_technique"]
    assert [e["type"] for e in engine.journal_du_run.evenements] == ["mark-panne"]
    assert raccroche.est_renvoye("CAessai")
    raccroche.oublier("CAessai")


async def test_ferme_promesse_de_rappel_datee_sans_dial(twilio):
    engine = _engine({"caller_number": "+33612345678", "horaires_ouverture": HORAIRES})
    gardien, patches = _gardien(engine)
    with patch.object(
        GardienPanne,
        "_etat",
        lambda self, maintenant=None: ("FERME", "lundi à 9 heures"),
    ):
        assert await _declencher(gardien, patches, "modele_lent", "modele") == "rappel"
    twiml = twilio.recus[0]["Twiml"]
    assert "<Dial" not in twiml and "<Hangup/>" in twiml
    assert "Nous vous rappelons dès la réouverture, lundi à 9 heures." in twiml
    raccroche.oublier("CAessai")


async def test_etat_reel_horaires_et_forcage(twilio):
    """The state is computed at that instant from the hours, and a forced closing wins."""
    engine = _engine({"horaires_ouverture": HORAIRES})
    gardien, _ = _gardien(engine)
    assert gardien._etat(_a("2030-01-07", "10:00"))[0] == "OUVERT"  # a Monday
    etat, reouverture = gardien._etat(_a("2030-01-05", "10:00"))  # a Saturday
    assert etat == "FERME" and reouverture
    force = SimpleNamespace(etat_force="FERME", etat_force_jusqu_a=None)
    gardien_force, _ = _gardien(engine, reglages_annonce=force)
    assert gardien_force._etat(_a("2030-01-07", "10:00"))[0] == "FERME"


async def test_sans_second_numero_sortant_et_sans_telephonie(twilio):
    engine = _engine({"caller_number": "+33612345678"})
    gardien, patches = _gardien(engine, second=None)
    with patch.object(
        GardienPanne, "_etat", lambda self, maintenant=None: ("OUVERT", "")
    ):
        assert (
            await _declencher(gardien, patches, "erreur_terminale", "voix") == "rappel"
        )
    gardien, patches = _gardien(
        _engine({"called_number": "+33698765432"}), entrant=False
    )
    assert await _declencher(gardien, patches, "erreur_terminale", "voix") == "excuse"
    assert (
        "<Dial" not in twilio.recus[-1]["Twiml"]
        and "excuser" in twilio.recus[-1]["Twiml"]
    )
    navigateur = _engine()
    gardien, patches = _gardien(navigateur, call_sid=None)
    avant = len(twilio.recus)
    assert (
        await _declencher(gardien, patches, "erreur_terminale", "voix")
        == "sans_telephonie"
    )
    assert (
        len(twilio.recus) == avant
        and navigateur._gathered_context["panne"]["decision"] == "sans_telephonie"
    )
    for sid in ("CAessai",):
        raccroche.oublier(sid)


async def test_twilio_refuse_le_raccroche_redevient_normal():
    faux = FauxTwilio(statut=500)
    engine = _engine({"caller_number": "+33612345678"})
    gardien, patches = _gardien(engine, call_sid="CArefus")
    with (
        patch.object(
            client_twilio,
            "nouveau_client",
            lambda **o: httpx.AsyncClient(transport=httpx.MockTransport(faux), **o),
        ),
        patch.object(
            GardienPanne, "_etat", lambda self, maintenant=None: ("OUVERT", "")
        ),
    ):
        assert (
            await _declencher(gardien, patches, "erreur_terminale", "voix")
            == "echec_twilio"
        )
    assert not raccroche.est_renvoye("CArefus")
    assert "jeton-twilio" not in json.dumps(engine._gathered_context)


def test_le_texte_tape_ne_devient_jamais_une_consigne():
    twiml = consigne.rappel("Fermé.</Say><Dial>+33100000000</Dial><Say>")
    assert "<Dial>" not in twiml and "&lt;/Say&gt;" in twiml


# --------------------------------------------------------------------------- #
# 2. The serializer leaves a handed-over call alone, and only it (C2)
# --------------------------------------------------------------------------- #


async def test_raccroche_evite_pour_l_appel_renvoye_seulement(monkeypatch):
    from api.services.telephony.providers.twilio.strategies import TwilioHangupStrategy

    raccroches = []

    async def faux_raccroche(self, context):
        raccroches.append(context["call_sid"])
        return True

    monkeypatch.setattr(TwilioHangupStrategy, "execute_hangup", faux_raccroche)
    from api.services.telephony.providers.twilio.transport import (
        TwilioHangupStrategyMark,
    )

    strategie = TwilioHangupStrategyMark()
    raccroche.marquer_renvoye("CArenvoye")
    assert await strategie.execute_hangup({"call_sid": "CArenvoye"}) is True
    assert await strategie.execute_hangup({"call_sid": "CAnormal"}) is True
    assert raccroches == ["CAnormal"]
    raccroche.oublier("CArenvoye")
    from api.services.telephony.providers.twilio import transport

    assert "TwilioHangupStrategyMark()" in Path(transport.__file__).read_text(
        encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# 3. The inbound instruction (PN5, C1)
# --------------------------------------------------------------------------- #


async def test_consigne_d_entree_pause_d_avant_sauf_agent_allume(monkeypatch):
    from api.services.telephony.providers.twilio.provider import TwilioProvider

    eteint = SimpleNamespace(
        workflow_id=3,
        definition=SimpleNamespace(workflow_configurations={}),
        initial_context={},
    )
    allume = SimpleNamespace(
        workflow_id=3,
        definition=SimpleNamespace(workflow_configurations={"panne": {"actif": True}}),
        initial_context={"called_number": "+33100000001"},
    )
    from api.db import db_client

    monkeypatch.setattr(
        db_client,
        "get_workflow_by_id",
        AsyncMock(return_value=SimpleNamespace(organization_id=1)),
    )
    monkeypatch.setattr(
        "api.services.panne.routes.lire_reglages",
        AsyncMock(
            return_value=ReglagesPanne(
                url_secours="https://handler.twilio.com/twiml/EHessai"
            )
        ),
    )
    monkeypatch.setattr(
        "api.services.etablissements.appel.etablissement_de_lappel",
        AsyncMock(
            return_value=SimpleNamespace(
                etablissement=SimpleNamespace(second_numero="+33344000000")
            )
        ),
    )
    fournisseur = TwilioProvider(
        {"account_sid": "AC", "auth_token": "t", "from_numbers": []}
    )

    monkeypatch.setattr(
        db_client, "get_workflow_run_by_id", AsyncMock(return_value=eteint)
    )
    reponse = await fournisseur.start_inbound_stream(
        websocket_url="wss://x/ws",
        workflow_run_id=5,
        normalized_data=None,
        backend_endpoint="https://b",
    )
    assert (
        reponse.body.decode().count('<Pause length="40"/>') == 1
        and "<Redirect" not in reponse.body.decode()
    )

    monkeypatch.setattr(
        db_client, "get_workflow_run_by_id", AsyncMock(return_value=allume)
    )
    reponse = await fournisseur.start_inbound_stream(
        websocket_url="wss://x/ws",
        workflow_run_id=5,
        normalized_data=None,
        backend_endpoint="https://b",
    )
    corps = reponse.body.decode()
    assert (
        '<Redirect method="POST">https://handler.twilio.com/twiml/EHessai?Renvoi=%2B33344000000</Redirect>'
        in corps
    )
    assert "<Pause" not in corps
    assert "{{Renvoi}}" in consigne.texte_du_bin()
    with pytest.raises(ValueError):
        ReglagesPanne(url_secours="http://handler.twilio.com/x")


# --------------------------------------------------------------------------- #
# 4. The triggers: model too slow (PN2), voice too slow (PN3), terminal error
# --------------------------------------------------------------------------- #


async def test_flux_du_modele_borne_par_le_delai():
    async def jamais():
        await asyncio.sleep(5)
        yield "x"

    async def cale():
        yield "a"
        yield "b"
        await asyncio.sleep(5)
        yield "c"

    async def normal():
        for m in ("a", "b"):
            yield m

    debuts = []

    async def au_premier():
        debuts.append(1)

    with pytest.raises(DelaiModeleDepasse) as e:
        [m async for m in FluxAvecDelai(jamais(), 0.1, au_premier)]
    assert e.value.moment == "premier_morceau"
    recus = []
    with pytest.raises(DelaiModeleDepasse) as e:
        async for m in FluxAvecDelai(cale(), 0.1, au_premier):
            recus.append(m)
    assert e.value.moment == "en_cours" and recus == ["a", "b"]
    assert [m async for m in FluxAvecDelai(normal(), 0.5, au_premier)] == ["a", "b"]
    assert debuts == [1, 1]


async def test_service_mistral_sans_delai_inchange_et_evenement_sans_erreur():
    from api.services.pipecat.service_factory import DograhMistralLLMService

    service = DograhMistralLLMService(
        api_key="cle-de-test-0123456789", model="mistral-small-latest"
    )
    assert service.mark_delai_modele_s is None
    recus = []
    service.event_handler("on_delai_modele_depasse")(
        lambda s, d: recus.append(d.moment) or asyncio.sleep(0)
    )

    async def bloque(self, context):
        await asyncio.sleep(5)

    service.mark_delai_modele_s = 0.1
    with patch(
        "pipecat.services.mistral.llm.MistralLLMService.get_chat_completions", bloque
    ):
        await service._process_context(SimpleNamespace())
    await asyncio.sleep(0.05)
    assert recus == ["premier_morceau"]


async def test_replis_un_instant_puis_le_repli_compteur_remis_par_une_reponse():
    from pipecat.frames.frames import LLMRunFrame, TTSSpeakFrame

    engine = _engine()
    task = SimpleNamespace(queue_frames=AsyncMock())
    gardien = SimpleNamespace(declencher=AsyncMock(return_value="renvoi"))
    terminer = AsyncMock()
    replis = ReplisDelaiModele(engine, task, gardien, terminer)
    depasse = DelaiModeleDepasse("premier_morceau", 4.0)
    await replis._depasse(None, depasse)
    trames = task.queue_frames.await_args.args[0]
    assert (
        isinstance(trames[0], TTSSpeakFrame)
        and trames[0].text == "Un instant, s'il vous plaît."
        and isinstance(trames[1], LLMRunFrame)
    )
    await replis._commencee(None)  # an answer started: back to zero (D6)
    await replis._depasse(None, depasse)
    gardien.declencher.assert_not_awaited()
    await replis._depasse(None, depasse)  # second in a row
    gardien.declencher.assert_awaited_once()
    terminer.assert_awaited_once()
    assert engine._gathered_context["depassements_modele"] == 3
    assert (
        sum(
            e["type"] == "mark-delai-modele-depasse"
            for e in engine.journal_du_run.evenements
        )
        == 3
    )


async def test_voix_lente_au_dela_du_seuil_seulement():
    from pipecat.frames.frames import TTSAudioRawFrame, TTSStartedFrame
    from pipecat.observers.base_observer import FramePushed
    from pipecat.processors.frame_processor import FrameDirection

    tts = object()
    recus = []

    async def au_depassement(ecart):
        recus.append(ecart)

    def pousse(trame, source=tts):
        return FramePushed(
            source=source,
            destination=None,
            frame=trame,
            direction=FrameDirection.DOWNSTREAM,
            timestamp=0,
        )

    rapide = ObservateurVoixLente(tts, 0.2, au_depassement)
    await rapide.on_push_frame(pousse(TTSStartedFrame()))
    await asyncio.sleep(0.05)
    await rapide.on_push_frame(
        pousse(TTSAudioRawFrame(audio=b"\0\0", sample_rate=16000, num_channels=1))
    )
    await asyncio.sleep(0.3)
    assert recus == []
    lente = ObservateurVoixLente(tts, 0.1, au_depassement)
    await lente.on_push_frame(pousse(TTSStartedFrame()))
    await asyncio.sleep(0.25)
    assert len(recus) == 1 and recus[0] >= 0.1


async def test_erreur_terminale_donne_le_repli_avant_la_fin():
    from pipecat.frames.frames import ErrorFrame

    class FauxTTSService:
        pass

    erreur = ErrorFrame(
        error="401 invalid api key",
    )
    erreur.processor = FauxTTSService()
    engine = SimpleNamespace(
        mark_gardien_panne=SimpleNamespace(declencher=AsyncMock(return_value="renvoi"))
    )
    await sur_erreur_terminale(engine, erreur)
    engine.mark_gardien_panne.declencher.assert_awaited_once_with(
        "erreur_terminale", "voix", "401 invalid api key"
    )
    await sur_erreur_terminale(SimpleNamespace(), erreur)  # no guard: nothing, no error
    from api.services.pipecat import event_handlers

    assert "sur_erreur_terminale(engine, error)" in Path(
        event_handlers.__file__
    ).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 5. The result of the ringing (signature checked)
# --------------------------------------------------------------------------- #


async def test_resultat_du_renvoi_signe_seulement(monkeypatch):
    from fastapi import FastAPI

    from api.db import db_client
    from api.services.panne import routes

    run = SimpleNamespace(
        workflow_id=3,
        gathered_context={
            "panne": {
                "decision": "renvoi",
                "consigne_rappel": consigne.rappel(
                    "Nous vous rappelons demain à 9 heures."
                ),
            }
        },
    )
    monkeypatch.setattr(
        db_client, "get_workflow_run_by_id", AsyncMock(return_value=run)
    )
    monkeypatch.setattr(
        db_client,
        "get_workflow_by_id",
        AsyncMock(return_value=SimpleNamespace(organization_id=1)),
    )
    ecrit = AsyncMock()
    monkeypatch.setattr(db_client, "update_workflow_run", ecrit)
    signature = {"ok": False}
    fournisseur = SimpleNamespace(
        verify_inbound_signature=AsyncMock(side_effect=lambda *a: signature["ok"])
    )
    monkeypatch.setattr(
        "api.services.telephony.factory.get_telephony_provider_for_run",
        AsyncMock(return_value=fournisseur),
    )
    app = FastAPI()
    app.include_router(routes.routeur_twilio)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as c:
        assert (
            await c.post(
                "/telephony/twilio/panne/7/resultat",
                data={"DialCallStatus": "no-answer"},
            )
        ).status_code == 401
        signature["ok"] = True
        r = await c.post(
            "/telephony/twilio/panne/7/resultat", data={"DialCallStatus": "no-answer"}
        )
        assert "demain à 9 heures" in r.text and "<Hangup/>" in r.text
        assert (
            ecrit.await_args.kwargs["gathered_context"]["panne"]["rappel_promis"]
            is True
        )
        r = await c.post(
            "/telephony/twilio/panne/7/resultat", data={"DialCallStatus": "completed"}
        )
        assert r.text.endswith("<Response><Hangup/></Response>")


# --------------------------------------------------------------------------- #
# 6. Always a request « to call back » (PN1), and the catch-up from Twilio (PN5)
# --------------------------------------------------------------------------- #


@pytest.fixture
async def base_v5(base_essai):  # noqa: F811
    from api.db.bases_clients import connexion as schema

    await schema.creer_base(base_essai)
    return base_essai


from api.tests.mark.test_base_client import base_essai  # noqa: F401  (fixture)


async def test_rattrapage_cree_chaque_demande_une_seule_fois(base_v5, monkeypatch):
    from api.db import db_client
    from api.db.bases_clients import connexion as schema

    maintenant = datetime.now(UTC)
    ancien = SimpleNamespace(
        is_completed=False, state="running", created_at=maintenant - timedelta(hours=1)
    )
    fini = SimpleNamespace(
        is_completed=True, state="completed", created_at=maintenant - timedelta(hours=1)
    )
    appels = [
        {
            "sid": "CAperdu",
            "direction": "inbound",
            "status": "completed",
            "from": "+33612345678",
            "to": "+33100000001",
            "start_time": "Mon, 07 Oct 2030 09:00:00 +0000",
        },
        {
            "sid": "CAinacheve",
            "direction": "inbound",
            "status": "completed",
            "from": "+33611111111",
            "to": "+33100000001",
            "start_time": "Mon, 07 Oct 2030 09:05:00 +0000",
        },
        {
            "sid": "CAnormal",
            "direction": "inbound",
            "status": "completed",
            "from": "+33622222222",
            "to": "+33100000001",
        },
        {
            "sid": "CAencours",
            "direction": "inbound",
            "status": "in-progress",
            "from": "+33633333333",
            "to": "+33100000001",
        },
    ]
    faux = FauxTwilio(appels=appels)
    runs = {"CAperdu": None, "CAinacheve": ancien, "CAnormal": fini}
    monkeypatch.setattr(
        db_client,
        "run_par_appel",
        AsyncMock(side_effect=lambda org, sid: runs.get(sid)),
    )
    monkeypatch.setattr(
        rattrapage,
        "_comptes",
        AsyncMock(return_value=[("ACessai", "jeton", ["+33100000001"])]),
    )
    monkeypatch.setattr(
        "api.services.base_client.rattachement.nom_de_la_base",
        AsyncMock(return_value=base_v5),
    )
    alertes = AsyncMock(return_value=["a@example.org"])
    monkeypatch.setattr("api.services.apres_appel.notification.notifier", alertes)
    from api.services.etablissements import copie as module_copie
    from api.tests.mark.test_base_client import _RedisFactice

    monkeypatch.setattr(module_copie, "_redis", AsyncMock(return_value=_RedisFactice()))
    with patch.object(
        client_twilio,
        "nouveau_client",
        lambda **o: httpx.AsyncClient(transport=httpx.MockTransport(faux), **o),
    ):
        premier = await rattrapage.rattraper(1, maintenant)
        second = await rattrapage.rattraper(1, maintenant)
    assert premier == {
        "appels_lus": 4,
        "demandes_creees": 2,
        "deja_connus": 0,
        "erreurs": [],
    }
    assert second["demandes_creees"] == 0 and second["deja_connus"] == 2
    assert alertes.await_count == 1 and "+33612345678" in alertes.await_args.args[2]
    assert all(
        r["methode"] == "GET" for r in faux.recus
    )  # reads the call log, writes nothing at Twilio
    connexion = await schema.connecter(base_v5)
    try:
        demandes = await connexion.fetch("SELECT priorite, statut FROM mark.demande")
        assert [tuple(d) for d in demandes] == [(1, "a_traiter"), (1, "a_traiter")]
        assert await connexion.fetchval("SELECT count(*) FROM mark.appel_perdu") == 2
    finally:
        await connexion.close()


async def test_rattrapage_sans_base_n_alerte_qu_une_fois_par_appel(monkeypatch):
    """Revue 8: without a client database the lost calls are only alerted; the hourly pass
    must not alert the same Twilio call again (a mark per call, like the recap)."""
    from api.services.etablissements import copie as module_copie
    from api.tests.mark.test_base_client import _RedisFactice

    appels = [
        {
            "sid": "CAseul",
            "direction": "inbound",
            "status": "completed",
            "from": "+33612345678",
            "to": "+33100000001",
        }
    ]
    faux = FauxTwilio(appels=appels)
    monkeypatch.setattr("api.db.db_client.run_par_appel", AsyncMock(return_value=None))
    monkeypatch.setattr(
        rattrapage,
        "_comptes",
        AsyncMock(return_value=[("ACessai", "jeton", ["+33100000001"])]),
    )
    monkeypatch.setattr(
        "api.services.base_client.rattachement.nom_de_la_base",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(module_copie, "_redis", AsyncMock(return_value=_RedisFactice()))
    alertes = AsyncMock(return_value=["a@example.org"])
    monkeypatch.setattr("api.services.apres_appel.notification.notifier", alertes)
    with patch.object(
        client_twilio,
        "nouveau_client",
        lambda **o: httpx.AsyncClient(transport=httpx.MockTransport(faux), **o),
    ):
        await rattrapage.rattraper(1)
        await rattrapage.rattraper(1)
        await rattrapage.rattraper(2)  # another organization: its own marks
    assert alertes.await_count == 2
    assert [c.args[0] for c in alertes.await_args_list] == [1, 2]


def test_les_defauts_de_l_ecran_sont_ceux_du_serveur():
    """The screen offers the three sentences with the texts the server says without them."""
    from pathlib import Path

    from api.schemas.panne import DEFAUT_EXCUSE, DEFAUT_RAPPEL

    ecran = (
        Path(__file__).resolve().parents[3]
        / "ui/src/components/mark/parametres-organisation/ModalePhrases.tsx"
    ).read_text(encoding="utf-8")
    for texte in (DEFAUT_RENVOI, DEFAUT_RAPPEL, DEFAUT_EXCUSE.replace("'", "'")):
        assert texte in ecran


async def test_traversee_erreur_terminale_par_les_vrais_gestionnaires(
    twilio, monkeypatch
):
    """Through the REAL ``register_event_handlers``: a voice left unusable gives the instruction to
    Twilio BEFORE the call ends; an agent without the fallback ends as before, nothing at Twilio."""
    from pipecat.frames.frames import ErrorFrame

    from api.services.panne.declencheurs import ATTRIBUT_GARDIEN
    from api.services.pipecat.event_handlers import register_event_handlers
    from api.services.pipecat.termination_funnel_processor import (
        TerminationFunnelProcessor,
    )
    from api.tests.test_pipeline_error_handling import _EventSource

    monkeypatch.setattr(
        "api.services.pipecat.event_handlers.db_client.get_workflow_run_by_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "api.services.pipecat.event_handlers._capture_call_event", AsyncMock()
    )
    ordre: list[str] = []

    def brancher(engine):
        task = _EventSource()
        register_event_handlers(
            task=task,
            transport=_EventSource(),
            workflow_run_id=7,
            engine=engine,
            audio_buffer=SimpleNamespace(
                start_recording=AsyncMock(), stop_recording=AsyncMock()
            ),
            in_memory_logs_buffer=SimpleNamespace(),
            transcript_log_coordinator=SimpleNamespace(),
            pipeline_metrics_aggregator=SimpleNamespace(),
            termination_funnel=TerminationFunnelProcessor(),
            audio_config=SimpleNamespace(pipeline_sample_rate=16000),
        )
        return task

    class FauxTTSService:
        is_usable = False

    erreur = ErrorFrame("TTS: invalid API key")
    erreur.processor = FauxTTSService()

    engine = _engine({"caller_number": "+33612345678"})
    engine.end_call_with_reason = AsyncMock(
        side_effect=lambda *a, **k: ordre.append(f"fin:{len(twilio.recus)}")
    )
    gardien, patches = _gardien(engine, call_sid="CAtraversee")
    setattr(engine, ATTRIBUT_GARDIEN, gardien)
    task = brancher(engine)
    for p in patches:
        p.start()
    try:
        with patch.object(
            GardienPanne, "_etat", lambda self, maintenant=None: ("OUVERT", "")
        ):
            await task.handlers["on_pipeline_error"](task, erreur)
            await asyncio.sleep(0)
    finally:
        for p in patches:
            p.stop()
    assert ordre == ["fin:1"]  # Twilio had its instruction before the end
    assert "<Number>+33344000000</Number>" in twilio.recus[0]["Twiml"]
    assert engine._gathered_context["panne"]["brique"] == "voix"
    raccroche.oublier("CAtraversee")

    sans = SimpleNamespace(end_call_with_reason=AsyncMock())
    task = brancher(sans)
    await task.handlers["on_pipeline_error"](task, erreur)
    sans.end_call_with_reason.assert_awaited_once()
    assert len(twilio.recus) == 1
