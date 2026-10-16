"""[.mark] Chantier agents-specialises, lot 5 (= lot 3 bis du plan fiche-etablissement, décision T) :
le transfert vers un humain, le répondeur, l'issue écrite dans la fiche de l'appel.

| Test | Ce qu'il prouve |
|---|---|
| appel Twilio | détection allumée : MachineDetection, notre adresse TwiML, rappel d'état ``?amd=1``, numéro affiché fixe ; éteinte : le TwiML d'avant, sans détection |
| adresse TwiML | machine ou fax = échec « répondeur » publié et raccrochage, jamais de conférence ; humain ou inconnu = conférence et succès ; transfert inconnu = raccrochage |
| rappel d'état | avec détection, « décroché » seul n'ouvre pas le pont ; une machine signalée ici est un échec ; sans détection, le comportement d'avant |
| issue dans la fiche | ``transferts_humains`` : décroché, sans réponse, occupé, répondeur, échec, vers une personne ET vers un numéro ; jamais un numéro en clair |
| options Twilio | seul Twilio reçoit détection, numéro et phrase ; un autre fournisseur, rien de plus qu'avant |
| numéro des transferts | un numéro d'une autre organisation est refusé |
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.enums import ToolCategory
from api.routes import telephony as route_telephony
from api.schemas.call_events import CallEventsSettings
from api.schemas.organization_preferences import OrganizationPreferences, OrganizationPreferencesResponse
from api.services.equipe import transferts_humains as th
from api.services.telephony.providers.twilio import provider as module_twilio
from api.services.telephony.providers.twilio.provider import TwilioProvider
from api.services.telephony.transfer_event_protocol import TransferContext, TransferEventType
from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager
from api.tests.mark.test_diriger_vers_personne import _appeler, _essai, _moteur

# --------------------------------------------------------------------------- #
# 1. L'appel sortant vers Twilio
# --------------------------------------------------------------------------- #


class _Reponse:
    status = 201

    async def text(self):
        return "{}"

    async def json(self):
        return {"sid": "CA123", "status": "queued"}


class _Session:
    envoye: dict = {}

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def post(self, endpoint, data=None, auth=None):
        _Session.envoye = dict(data)
        reponse = _Reponse()

        class _Ctx:
            async def __aenter__(self_inner):
                return reponse

            async def __aexit__(self_inner, *a):
                return False

        return _Ctx()


def _twilio():
    return TwilioProvider(
        {"account_sid": "AC123", "auth_token": "x", "from_numbers": ["+15551230001", "+15551230002"]}
    )


async def _transfert(**options):
    with (
        patch.object(module_twilio.aiohttp, "ClientSession", _Session),
        patch.object(module_twilio, "get_backend_endpoints", AsyncMock(return_value=("https://api.exemple.test", ""))),
    ):
        await _twilio().transfer_call("+33611111111", "tid-1", "transfer-CAxyz", 30, **options)
    return _Session.envoye


@pytest.mark.asyncio
async def test_detection_allumee_twilio_demande_qui_a_decroche_et_laisse_notre_adresse_decider():
    envoye = await _transfert(detection_repondeur=True, from_number="+15551230002", phrase_salarie="Bonjour & merci.")
    assert envoye["MachineDetection"] == "Enable" and envoye["MachineDetectionTimeout"] == th.DELAI_DETECTION_S
    assert envoye["Url"] == "https://api.exemple.test/api/v1/telephony/transfer-twiml/tid-1"
    assert "Twiml" not in envoye  # la mise en conférence se décide à NOTRE adresse
    assert envoye["StatusCallback"].endswith("/transfer-result/tid-1?amd=1")
    assert envoye["From"] == "+15551230002"  # le numéro affiché fixe


@pytest.mark.asyncio
async def test_detection_eteinte_le_transfert_d_avant_sans_detection():
    envoye = await _transfert(detection_repondeur=False, phrase_salarie="Appel transmis & vérifié.")
    assert "MachineDetection" not in envoye and "Url" not in envoye
    assert "<Conference endConferenceOnExit=\"true\">transfer-CAxyz</Conference>" in envoye["Twiml"]
    assert 'language="fr-FR"' in envoye["Twiml"] and "Appel transmis &amp; vérifié." in envoye["Twiml"]
    assert envoye["StatusCallback"].endswith("/transfer-result/tid-1")
    assert envoye["From"] in ("+15551230001", "+15551230002")


@pytest.mark.asyncio
async def test_un_appel_sans_option_est_celui_d_avant():
    envoye = await _transfert()
    assert "MachineDetection" not in envoye and "Twiml" in envoye and "Url" not in envoye


def test_la_phrase_du_salarie_est_en_francais_et_reglable():
    assert th.phrase_du_salarie({}) == th.PHRASE_SALARIE_DEFAUT
    assert th.phrase_du_salarie({"phrase_salarie_transfert": "  Appel   du standard. "}) == "Appel du standard."
    assert "assistant vocal" in th.PHRASE_SALARIE_DEFAUT


def test_l_interrupteur_de_secours(monkeypatch):
    monkeypatch.delenv("DETECTION_REPONDEUR_TRANSFERT", raising=False)
    assert th.detection_allumee() is True
    for valeur in ("0", "false", "non", "OFF"):
        monkeypatch.setenv("DETECTION_REPONDEUR_TRANSFERT", valeur)
        assert th.detection_allumee() is False


# --------------------------------------------------------------------------- #
# 2. Notre adresse TwiML et le rappel d'état (vraies routes)
# --------------------------------------------------------------------------- #


class _Gestionnaire:
    def __init__(self, contexte):
        self.contexte = contexte
        self.evenements = []

    async def get_transfer_context(self, _id):
        return self.contexte

    async def publish_transfer_event(self, evenement):
        self.evenements.append(evenement)


def _contexte():
    return TransferContext(
        transfer_id="tid-1", call_sid="CAsortant", target_number="+33611111111", tool_uuid="u",
        original_call_sid="CAentrant", conference_name="transfer-CAentrant", initiated_at=0.0,
        phrase_salarie="Appel transmis par votre assistant.",
    )


def _poster(chemin, donnees, contexte="oui", requete=""):
    gestionnaire = _Gestionnaire(_contexte() if contexte == "oui" else None)
    app = FastAPI()
    app.include_router(route_telephony.router)
    with patch.object(route_telephony, "get_call_transfer_manager", AsyncMock(return_value=gestionnaire)):
        reponse = TestClient(app).post(f"/telephony{chemin}{requete}", data=donnees)
    return reponse, gestionnaire


@pytest.mark.parametrize("repondu_par", ["machine_start", "machine_end_beep", "machine_end_silence", "machine_end_other", "fax"])
def test_un_repondeur_est_un_echec_et_le_pont_ne_s_ouvre_jamais(repondu_par):
    reponse, gestionnaire = _poster("/transfer-twiml/tid-1", {"AnsweredBy": repondu_par, "CallSid": "CAsortant"})
    assert reponse.status_code == 200 and "<Hangup/>" in reponse.text and "Conference" not in reponse.text
    [evenement] = gestionnaire.evenements
    assert evenement.type == TransferEventType.TRANSFER_FAILED and evenement.reason == "voicemail"


@pytest.mark.parametrize("repondu_par", ["human", "unknown", ""])
def test_un_humain_ou_un_inconnu_est_mis_en_conference(repondu_par):
    """``unknown`` compte comme un humain : jamais d'appelant renvoyé à tort vers l'agent."""
    reponse, gestionnaire = _poster("/transfer-twiml/tid-1", {"AnsweredBy": repondu_par, "CallSid": "CAsortant"})
    assert "<Conference endConferenceOnExit=\"true\">transfer-CAentrant</Conference>" in reponse.text
    assert "Appel transmis par votre assistant." in reponse.text and 'language="fr-FR"' in reponse.text
    [evenement] = gestionnaire.evenements
    assert evenement.type == TransferEventType.DESTINATION_ANSWERED and evenement.conference_name == "transfer-CAentrant"


def test_un_transfert_inconnu_raccroche_sans_rien_publier():
    reponse, gestionnaire = _poster("/transfer-twiml/inconnu", {"AnsweredBy": "human"}, contexte="non")
    assert "<Hangup/>" in reponse.text and gestionnaire.evenements == []


def test_avec_detection_le_simple_decroche_n_ouvre_pas_le_pont():
    reponse, gestionnaire = _poster("/transfer-result/tid-1", {"CallStatus": "in-progress", "CallSid": "CAs"}, requete="?amd=1")
    assert reponse.json() == {"status": "pending"} and gestionnaire.evenements == []


def test_une_machine_signalee_au_rappel_d_etat_est_un_echec():
    reponse, gestionnaire = _poster(
        "/transfer-result/tid-1",
        {"CallStatus": "in-progress", "AnsweredBy": "machine_start", "CallSid": "CAs"},
        requete="?amd=1",
    )
    [evenement] = gestionnaire.evenements
    assert evenement.type == TransferEventType.TRANSFER_FAILED and evenement.reason == "voicemail"


def test_sans_detection_le_rappel_d_etat_est_celui_d_avant():
    reponse, gestionnaire = _poster("/transfer-result/tid-1", {"CallStatus": "in-progress", "CallSid": "CAs"})
    [evenement] = gestionnaire.evenements
    assert evenement.type == TransferEventType.DESTINATION_ANSWERED
    reponse, gestionnaire = _poster("/transfer-result/tid-1", {"CallStatus": "no-answer", "CallSid": "CAs"}, requete="?amd=1")
    assert gestionnaire.evenements[0].reason == "no_answer"


# --------------------------------------------------------------------------- #
# 3. L'issue, écrite dans la fiche de l'appel
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "resultat, issue",
    [
        ({"action": "destination_answered", "status": "success"}, "decroche"),
        ({"action": "transfer_failed", "reason": "no_answer"}, "sans_reponse"),
        ({"action": "transfer_failed", "reason": "timeout"}, "sans_reponse"),
        ({"action": "transfer_failed", "reason": "busy"}, "occupe"),
        ({"action": "transfer_failed", "reason": "voicemail"}, "repondeur"),
        ({"action": "transfer_failed", "reason": "call_failed"}, "echec"),
        ({"action": "transfer_failed", "reason": "provider_error"}, "echec"),
        ({"action": "transfer_failed"}, "echec"),
    ],
)
def test_l_issue_de_chaque_resultat(resultat, issue):
    assert th.issue_du_resultat(resultat) == issue and issue in th.ISSUES


def test_un_numero_n_est_jamais_ecrit_en_clair():
    assert th.masquer("+33344000099") == "numero:***0099" and th.masquer("") == "numero:***"


async def test_vers_une_personne_decroche_et_echec_sont_dans_la_fiche(monkeypatch):
    engine, mgr, enregistres = _moteur(monkeypatch)
    _essai(monkeypatch, "accepte")
    await mgr.register_handlers(["uuid-Diriger"])
    await _appeler(enregistres["diriger"][0], {"personne": "camille"})
    [entree] = engine._gathered_context["transferts_humains"]
    assert entree["issue"] == "decroche" and entree["cible"] == "personne:camille" and entree["le"]
    assert "+33611111111" not in str(engine._gathered_context["transferts_humains"])

    engine2, mgr2, enregistres2 = _moteur(monkeypatch)
    _essai(monkeypatch, "refuse")
    await mgr2.register_handlers(["uuid-Diriger"])
    await _appeler(enregistres2["diriger"][0], {"personne": "camille"})
    [entree] = engine2._gathered_context["transferts_humains"]
    assert entree["issue"] == "echec" and entree["cible"] == "personne:camille"


async def test_vers_le_numero_de_l_etablissement_aussi(monkeypatch):
    """L'outil de transfert ordinaire (numéro de la fiche), pas seulement une personne."""
    engine, mgr, _ = _moteur(monkeypatch)
    _essai(monkeypatch, "accepte")
    outil = MagicMock()
    outil.tool_uuid = "u-transfert"
    outil.name = "Transfert"
    outil.category = ToolCategory.TRANSFER_CALL.value
    outil.definition = {"type": "transfer_call", "config": {"destination": "+33344000099", "timeout": 30}}
    gestionnaire = mgr._create_transfer_call_handler(outil, "transfert")
    await _appeler(gestionnaire, {})
    [entree] = engine._gathered_context["transferts_humains"]
    assert entree == {"le": entree["le"], "cible": "numero:***0099", "issue": "decroche"}

    engine2, mgr2, _ = _moteur(monkeypatch)
    _essai(monkeypatch, "refuse")
    await _appeler(mgr2._create_transfer_call_handler(outil, "transfert"), {})
    assert engine2._gathered_context["transferts_humains"][0]["issue"] == "echec"


async def test_un_resultat_de_repondeur_est_note_comme_tel(monkeypatch):
    engine, mgr, _ = _moteur(monkeypatch)
    mgr._cible_transfert_humain = "personne:camille"
    capte = []

    async def rappel(resultat, *a, **k):
        capte.append(resultat)

    params = SimpleNamespace(result_callback=rappel)
    await mgr._handle_transfer_result(
        {"action": "transfer_failed", "reason": "voicemail", "status": "transfer_failed", "message": "m"},
        params,
        None,
    )
    assert engine._gathered_context["transferts_humains"][0]["issue"] == "repondeur"
    assert capte[0]["reason"] == "voicemail"


# --------------------------------------------------------------------------- #
# 4. Les options propres à Twilio, et le numéro des transferts
# --------------------------------------------------------------------------- #


async def test_seul_twilio_recoit_detection_numero_et_phrase(monkeypatch):
    engine, mgr, _ = _moteur(monkeypatch)
    contexte = _contexte()
    preferences = OrganizationPreferences(numero_des_transferts="+15551230002")
    with patch(
        "api.services.organization_preferences.get_organization_preferences", AsyncMock(return_value=preferences)
    ):
        options = await mgr._options_de_transfert(SimpleNamespace(PROVIDER_NAME="twilio"), 1, contexte)
        assert options == {
            "detection_repondeur": True,
            "phrase_salarie": "Appel transmis par votre assistant.",
            "from_number": "+15551230002",
        }
        assert await mgr._options_de_transfert(SimpleNamespace(PROVIDER_NAME="telnyx"), 1, contexte) == {}
    # Aucun numéro choisi : celui du fournisseur, comme avant.
    with patch(
        "api.services.organization_preferences.get_organization_preferences",
        AsyncMock(return_value=OrganizationPreferences()),
    ):
        options = await mgr._options_de_transfert(SimpleNamespace(PROVIDER_NAME="twilio"), 1, contexte)
        assert "from_number" not in options


def test_le_numero_des_transferts_doit_etre_un_numero_de_l_organisation():
    from api.routes import organization as route_organization
    from api.services.auth.depends import get_user_with_selected_organization

    app = FastAPI()
    app.include_router(route_organization.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: SimpleNamespace(
        id=1, provider_id="p", selected_organization_id=7
    )
    lignes = [("+15551230002", None, None, None, True)]
    with (
        patch.object(route_organization.db_client, "lister_numeros_de_lorganisation", AsyncMock(return_value=lignes)),
        patch.object(
            route_organization,
            "update_organization_preferences",
            AsyncMock(return_value=OrganizationPreferencesResponse(call_events=CallEventsSettings())),
        ) as ecrit,
    ):
        client = TestClient(app)
        refus = client.put("/organizations/preferences", json={"numero_des_transferts": "+15559990000"})
        assert refus.status_code == 422 and "not a Telephony number" in refus.text and ecrit.await_count == 0
        client.put("/organizations/preferences", json={"numero_des_transferts": "+1 555 123 0002"})
        assert ecrit.await_count == 1
        mauvais = client.put("/organizations/preferences", json={"numero_des_transferts": "0612345678"})
        assert mauvais.status_code == 422


def test_la_route_twiml_figure_dans_la_spec_publiee():
    from api.app import app

    assert "/api/v1/telephony/transfer-twiml/{transfer_id}" in app.openapi()["paths"]
