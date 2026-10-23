"""[.mark] Chantier correctifs-apres-banc-commun, lot V : les correctifs officiels de la voix Soniox.

Reprise, dans ``MarkSonioxTTSService``, des correctifs de Pipecat 1.13 (le pointeur du sous-module ne
bouge pas, R2) : PR #6011 (keepalive), PR #6008 (flux configuré avant son texte, contextes fermés à une
reconnexion, crochets qui échouent), ``58d99e98f`` (erreurs classées par code HTTP). Leurs tests
officiels (``test_websocket_tts_keepalive.py``, ``test_tts_reconnect.py``, ``test_soniox_tts.py``) sont
adaptés à notre classe. Aucun appel réel à Soniox : un faux websocket.

| Test | Preuve |
|---|---|
| le keepalive part à chaque délai, survit à un envoi qui échoue, saute une connexion fermée | #6011, V2 (408) |
| un flux jamais ouvert est configuré avant son premier texte, une seule fois | #6008, V2 (invalid_stream_state) |
| une nouvelle connexion ferme les contextes ouverts, le tour continue sous un nouvel identifiant | #6008 |
| un crochet qui échoue ne casse ni l'interruption ni la fin | #6008 |
| 402 = crédit, 401 = clé, 429 = limite, code absent ou illisible = inconnue | 58d99e98f, V2 (429) |
| la voix de la fabrique emprunte la connexion de l'appel : envoi par la prêteuse, messages rendus à qui a ouvert le flux | D22 |
| prêteuse fermée ou absente : la voix ouvre la sienne (comme avant) ; la prêteuse qui se ferme prévient | zéro perte |
| la fabrique des sons demande l'emprunt, et rien pour une voix sans cette capacité | D22 |
"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from websockets.protocol import State

from api.services.pipecat.soniox_cle_en_entete import MarkSonioxTTSService
from api.services.pipecat.soniox_voix_correctifs import (
    ConnexionEmpruntee,
    categorie_de_l_erreur_soniox,
)
from pipecat.utils.asyncio.task_manager import TaskManager
from pipecat.utils.errors import ErrorCategory


class _FauxWebsocket:
    """Une connexion Soniox : ce qu'on lui envoie, ce qu'elle rend."""

    def __init__(self, messages=None):
        self.state = State.OPEN
        self.envoyes: list[dict] = []
        self.a_lire: list[str] = [json.dumps(m) if not isinstance(m, str) else m for m in (messages or [])]
        self.ferme = False
        self.echecs_a_venir = 0

    async def send(self, message):
        if self.echecs_a_venir:
            self.echecs_a_venir -= 1
            raise ConnectionError("coupée")
        self.envoyes.append(json.loads(message))

    async def close(self):
        self.ferme = True
        self.state = State.CLOSED

    def __aiter__(self):
        return self._lire()

    async def _lire(self):
        for message in self.a_lire:
            yield message


def _voix():
    return MarkSonioxTTSService(api_key="cle-de-test")


# --- PR #6011 : keepalive ------------------------------------------------------------------------


@pytest.fixture
def delai_court(monkeypatch):
    import pipecat.services.soniox.tts as tts

    monkeypatch.setattr(tts, "KEEPALIVE_INTERVAL_SECONDS", 0.01)


async def _attendre(condition, delai=2.0):
    async with asyncio.timeout(delai):
        while not condition():
            await asyncio.sleep(0.01)


def _keepalives(ws):
    return [m for m in ws.envoyes if m.get("keep_alive")]


@pytest.mark.asyncio
async def test_le_keepalive_part_a_chaque_delai(delai_court):
    voix = _voix()
    voix._task_manager = TaskManager()
    voix._websocket = _FauxWebsocket()
    tache = voix.create_task(voix._keepalive_task_handler())
    try:
        await _attendre(lambda: len(_keepalives(voix._websocket)) >= 3)
    finally:
        await voix.cancel_task(tache)


@pytest.mark.asyncio
async def test_le_keepalive_survit_a_un_envoi_qui_echoue(delai_court):
    """V2 (408) : la boucle de 1.12 sortait à la première erreur et laissait la connexion s'endormir."""
    voix = _voix()
    voix._task_manager = TaskManager()
    voix._websocket = _FauxWebsocket()
    voix._websocket.echecs_a_venir = 2
    tache = voix.create_task(voix._keepalive_task_handler())
    try:
        await _attendre(lambda: len(_keepalives(voix._websocket)) >= 2)
        assert voix._websocket.echecs_a_venir == 0
        assert not tache.done()
    finally:
        await voix.cancel_task(tache)


@pytest.mark.asyncio
async def test_le_keepalive_saute_une_connexion_fermee_puis_reprend(delai_court):
    voix = _voix()
    voix._task_manager = TaskManager()
    voix._websocket = _FauxWebsocket()
    voix._websocket.state = State.CLOSED
    tache = voix.create_task(voix._keepalive_task_handler())
    try:
        await asyncio.sleep(0.08)
        assert _keepalives(voix._websocket) == []
        voix._websocket.state = State.OPEN
        await _attendre(lambda: len(_keepalives(voix._websocket)) >= 1)
    finally:
        await voix.cancel_task(tache)


# --- PR #6008 : flux configuré avant son texte, contextes d'une ancienne connexion -----------------


@pytest.mark.asyncio
async def test_un_flux_jamais_ouvert_est_configure_avant_son_premier_texte():
    """Après une reconnexion, l'identifiant est neuf pour Soniox : texte sans configuration = refus."""
    voix = _voix()
    voix._websocket = _FauxWebsocket()
    async for _ in voix.run_tts("Bonjour.", "flux-1"):
        pass
    async for _ in voix.run_tts("Encore.", "flux-1"):
        pass
    envoyes = voix._websocket.envoyes
    assert [m.get("stream_id") for m in envoyes] == ["flux-1"] * 3
    assert "text" not in envoyes[0] and envoyes[0]["api_key"] == "cle-de-test"
    assert [m.get("text") for m in envoyes[1:]] == ["Bonjour.", "Encore."]


@pytest.mark.asyncio
async def test_un_flux_deja_ouvert_a_l_avance_n_est_pas_configure_deux_fois():
    voix = _voix()
    voix._websocket = _FauxWebsocket()
    await voix._send_config("flux-1")
    async for _ in voix.run_tts("Bonjour.", "flux-1"):
        pass
    assert len([m for m in voix._websocket.envoyes if "api_key" in m]) == 1


@pytest.mark.asyncio
async def test_un_envoi_de_configuration_qui_echoue_est_dit_et_la_connexion_refaite():
    from pipecat.frames.frames import ErrorFrame, TTSStoppedFrame

    voix = _voix()
    voix._websocket = _FauxWebsocket()
    voix._websocket.echecs_a_venir = 1
    reconnexions = []

    async def _deconnecter():
        reconnexions.append("deconnexion")

    async def _connecter():
        reconnexions.append("connexion")

    voix._disconnect = _deconnecter
    voix._connect = _connecter
    frames = [f async for f in voix.run_tts("Bonjour.", "flux-1")]
    assert isinstance(frames[0], ErrorFrame) and frames[0].exception is not None
    assert isinstance(frames[1], TTSStoppedFrame)
    assert reconnexions == ["deconnexion", "connexion"]


@pytest.mark.asyncio
async def test_une_nouvelle_connexion_ferme_les_contextes_et_change_l_identifiant_du_tour(monkeypatch):
    from pipecat.services import websocket_service

    async def fausse_connexion(*args, **kwargs):
        return object()

    monkeypatch.setattr(websocket_service, "websocket_connect", fausse_connexion)
    voix = _voix()
    fermes = []

    async def _retirer(contexte):
        fermes.append(contexte)

    voix.get_audio_contexts = lambda: ["ancien-1", "ancien-2"]
    voix.remove_audio_context = _retirer
    voix._turn_context_id = "tour-en-cours"
    await voix._websocket_connect("wss://test")
    assert fermes == ["ancien-1", "ancien-2"]
    assert voix._turn_context_id not in (None, "tour-en-cours")


@pytest.mark.asyncio
async def test_la_premiere_connexion_ne_touche_a_rien(monkeypatch):
    from pipecat.services import websocket_service

    async def fausse_connexion(*args, **kwargs):
        return object()

    monkeypatch.setattr(websocket_service, "websocket_connect", fausse_connexion)
    voix = _voix()
    await voix._websocket_connect("wss://test")
    assert voix.get_audio_contexts() == [] and voix._turn_context_id is None


@pytest.mark.asyncio
async def test_un_crochet_qui_echoue_ne_casse_ni_l_interruption_ni_la_fin(monkeypatch):
    from pipecat.services.soniox.tts import SonioxTTSService

    async def casse(self, context_id):
        raise RuntimeError("crochet cassé")

    monkeypatch.setattr(SonioxTTSService, "on_audio_context_interrupted", casse)
    voix = _voix()
    await voix.on_audio_context_interrupted("ctx")  # ne lève pas
    # Le crochet de fin : celui du parent direct de notre mélange échoue, le mélange l'absorbe.
    from pipecat.services.tts_service import TTSService

    monkeypatch.setattr(TTSService, "on_audio_context_completed", casse)
    await voix.on_audio_context_completed("ctx")


# --- 58d99e98f : erreurs par code HTTP ----------------------------------------------------------


@pytest.mark.parametrize(
    "code,attendu",
    [
        (402, ErrorCategory.QUOTA),
        (401, ErrorCategory.AUTHENTICATION),
        (429, ErrorCategory.RATE_LIMIT),
        ("oups", None),
        (None, None),
        (True, None),
    ],
)
def test_la_categorie_suit_le_code_http(code, attendu):
    assert categorie_de_l_erreur_soniox(code) == attendu


@pytest.mark.asyncio
async def test_une_erreur_du_flux_porte_la_categorie_de_son_code(monkeypatch):
    """Par la vraie lecture des messages : 429 (limite de flux) n'est plus « inconnue »."""
    from pipecat.processors.frame_processor import FrameProcessor

    vues = []

    async def push_error_amont(self, error_msg, exception=None, fatal=False, category=None, **kw):
        vues.append(category)

    monkeypatch.setattr(FrameProcessor, "push_error", push_error_amont)
    voix = _voix()
    voix._websocket = _FauxWebsocket(
        [
            {"error_code": 402, "error_type": "organization_balance_exhausted"},
            {"error_code": 401, "error_type": "unauthorized"},
            {"error_code": 429, "error_type": "limit_exceeded", "stream_id": "s"},
            {"error_code": "oops"},
            {"audio": "AAAA", "stream_id": "s"},
        ]
    )
    await voix._receive_messages()
    assert vues == [
        ErrorCategory.QUOTA,
        ErrorCategory.AUTHENTICATION,
        ErrorCategory.RATE_LIMIT,
        None,
    ]


# --- Connexion empruntée par la fabrique des sons --------------------------------------------------


def _paire():
    appel = _voix()
    appel._websocket = _FauxWebsocket()
    sons = _voix()
    return appel, sons


@pytest.mark.asyncio
async def test_la_voix_des_sons_emprunte_la_connexion_de_l_appel_et_n_en_ouvre_pas_une_seconde(monkeypatch):
    from pipecat.services import websocket_service

    async def interdit(*args, **kwargs):
        raise AssertionError("une seconde connexion a été ouverte")

    monkeypatch.setattr(websocket_service, "websocket_connect", interdit)
    appel, sons = _paire()
    assert sons.partager_la_connexion_de(appel) is True
    await sons._connect_websocket()
    assert isinstance(sons._websocket, ConnexionEmpruntee)
    await sons._send_config("flux-sons")
    await sons._websocket.send(json.dumps({"stream_id": "flux-sons", "text": "Un instant.", "text_end": False}))
    envoyes = appel._websocket.envoyes
    assert [m["stream_id"] for m in envoyes] == ["flux-sons", "flux-sons"]
    assert envoyes[0]["api_key"] == "cle-de-test"


@pytest.mark.asyncio
async def test_les_messages_reviennent_a_la_voix_qui_a_ouvert_le_flux():
    appel, sons = _paire()
    sons.partager_la_connexion_de(appel)
    await sons._connect_websocket()
    await sons._send_config("flux-sons")
    appel._websocket.a_lire = [
        json.dumps({"stream_id": "flux-appel", "audio": "AAAA"}),
        json.dumps({"stream_id": "flux-sons", "audio": "BBBB"}),
        json.dumps({"stream_id": "flux-sons", "terminated": True}),
    ]
    lus_par_l_appel = [json.loads(m) async for m in appel._get_websocket()]
    assert [m["stream_id"] for m in lus_par_l_appel] == ["flux-appel"]
    file = sons._websocket.messages.file
    assert [json.loads(file.get_nowait())["stream_id"] for _ in range(2)] == ["flux-sons"] * 2
    assert file.empty()
    # La voix des sons lit sa file par sa propre lecture de messages.
    file.put_nowait(json.dumps({"stream_id": "flux-sons", "audio_end": True}))
    file.put_nowait(None)
    assert [json.loads(m)["stream_id"] async for m in sons._get_websocket()] == ["flux-sons"]


@pytest.mark.asyncio
async def test_f6_une_erreur_d_un_flux_des_sons_ne_va_jamais_a_la_voix_de_l_appel():
    """Lot 11 (F-6, revue 8). Doc Soniox (api-reference/errors) : une erreur qui porte son ``stream_id`` ne ferme
    pas la connexion, les autres flux continuent ; seule une erreur de connexion (``stream_id`` vide) la ferme.
    L'erreur d'un flux de la fabrique revient donc à la fabrique : la phrase de l'appel n'est jamais touchée."""
    appel, sons = _paire()
    sons.partager_la_connexion_de(appel)
    await sons._connect_websocket()
    await sons._send_config("flux-sons")
    appel._websocket.a_lire = [
        json.dumps({"stream_id": "flux-sons", "error_code": 400, "error_message": "Stream not found"}),
        json.dumps({"stream_id": "flux-appel", "audio": "AAAA"}),
    ]
    lus_par_l_appel = [json.loads(m) async for m in appel._get_websocket()]
    assert lus_par_l_appel == [{"stream_id": "flux-appel", "audio": "AAAA"}]
    assert "_mark_code_d_erreur" not in appel.__dict__  # l'appel ne pousse aucune erreur pour ce flux
    assert json.loads(sons._websocket.messages.file.get_nowait())["error_code"] == 400


@pytest.mark.asyncio
async def test_sans_emprunt_la_connexion_de_l_appel_lit_tout_comme_avant():
    appel, _ = _paire()
    appel._websocket.a_lire = [json.dumps({"stream_id": "a", "audio": "AA"}), "pas du json"]
    assert len([m async for m in appel._get_websocket()]) == 2


@pytest.mark.asyncio
async def test_pas_d_emprunt_si_la_voix_de_l_appel_n_est_pas_connectee_ou_n_est_pas_soniox(monkeypatch):
    from pipecat.services import websocket_service

    ouvertes = []

    async def fausse_connexion(adresse, **kwargs):
        ouvertes.append(adresse)
        return _FauxWebsocket()

    monkeypatch.setattr(websocket_service, "websocket_connect", fausse_connexion)
    appel, sons = _paire()
    appel._websocket = None
    assert sons.partager_la_connexion_de(appel) is False
    assert sons.partager_la_connexion_de(SimpleNamespace(_websocket=_FauxWebsocket())) is False
    assert sons.partager_la_connexion_de(sons) is False
    await sons._connect_websocket()
    assert len(ouvertes) == 1 and not isinstance(sons._websocket, ConnexionEmpruntee)


@pytest.mark.asyncio
async def test_la_preteuse_qui_se_ferme_previent_la_voix_des_sons_et_une_reconnexion_ouvre_la_sienne(monkeypatch):
    from pipecat.services import websocket_service

    ouvertes = []

    async def fausse_connexion(adresse, **kwargs):
        ouvertes.append(adresse)
        return _FauxWebsocket()

    monkeypatch.setattr(websocket_service, "websocket_connect", fausse_connexion)
    appel, sons = _paire()
    sons.partager_la_connexion_de(appel)
    await sons._connect_websocket()
    await sons._send_config("flux-sons")
    await appel._disconnect_websocket()
    assert sons._websocket.messages.file.get_nowait() is None
    # La voix de l'appel est fermée : les sons rouvrent leur propre connexion.
    await sons._disconnect_websocket()
    await sons._connect_websocket()
    assert len(ouvertes) == 1 and not isinstance(sons._websocket, ConnexionEmpruntee)


@pytest.mark.asyncio
async def test_la_voix_qui_emprunte_n_envoie_pas_de_keepalive(delai_court):
    appel, sons = _paire()
    sons._task_manager = TaskManager()
    sons.partager_la_connexion_de(appel)
    await sons._connect_websocket()
    tache = sons.create_task(sons._keepalive_task_handler())
    try:
        await asyncio.sleep(0.08)
        assert _keepalives(appel._websocket) == []
    finally:
        await sons.cancel_task(tache)


@pytest.mark.asyncio
async def test_la_fabrique_des_sons_demande_l_emprunt_de_la_connexion_de_l_appel():
    from api.services.phrases.sons import FabriqueDesSons
    from pipecat.tests import MockTTSService

    demandes = []

    class VoixAvecEmprunt(MockTTSService):
        def partager_la_connexion_de(self, autre):
            demandes.append(autre)
            return True

    voix_de_l_appel = object()
    ajoutes = []

    async def ajouter(worker):
        ajoutes.append(worker)
        raise RuntimeError("fin du test")

    fabrique = FabriqueDesSons(
        creer_la_voix=lambda: VoixAvecEmprunt(mock_audio_duration_ms=60, frame_delay=0),
        ajouter_le_circuit=ajouter,
        taux_attendu=16000,
        voix_de_l_appel=voix_de_l_appel,
    )
    await fabrique.fabriquer(["Un instant."])
    assert demandes == [voix_de_l_appel] and len(ajoutes) == 1
    # Une voix sans cette capacité (autre fournisseur) : rien n'est demandé, rien ne change.
    sans = FabriqueDesSons(
        creer_la_voix=lambda: MockTTSService(mock_audio_duration_ms=60, frame_delay=0),
        ajouter_le_circuit=ajouter,
        taux_attendu=16000,
        voix_de_l_appel=voix_de_l_appel,
    )
    await sans.fabriquer(["Un instant."])
    assert demandes == [voix_de_l_appel]
