"""[.mark] Builder partie 2, U10 / S1 : le flux temps réel et le contexte d'une session PUBLIQUE.

| Test | Ce qu'il prouve |
|---|---|
| cas rouge (R7) | une session publique pendant laquelle l'agent appelle un outil ne reçoit NI l'appel NI le résultat (traverse ``_handle_offer``) |
| témoin | la même session via l'écran de test (flux complet) reçoit bien l'appel : le cas rouge voit ce qu'il doit voir |
| refus par défaut | un type d'événement inconnu n'arrive jamais au visiteur |
| liste blanche | la parole du bot et le mute passent, sans contenu ; l'erreur est générique |
| transcription, nom d'étape, mesures | retenus |
| la route publique | ``public_signaling_websocket`` demande le flux filtré, la route privée non |
| contexte (D182) | ``etablissement_id``, ``called_number`` et les clés .mark envoyés par la page sont écartés |
| contexte déclaré | une clé déclarée par l'agent passe, une clé .mark déclarée par erreur non |
| établissement d'un agent de site | trois lieux : sans fiche, aucun établissement ; avec fiche, la sienne ; jamais le premier |
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


from starlette.websockets import WebSocketState

from api.routes.webrtc_signaling import SignalingManager
from api.schemas.etablissements import CatalogueEtablissements
from api.services.etablissements.appel import choisir_etablissement
from api.services.pipecat.realtime_feedback_events import (
    build_bot_text_event,
    build_function_call_end_event,
    build_function_call_start_event,
    build_node_transition_event,
    build_user_transcription_event,
)
from api.services.site_mark import flux_public
from api.services.site_mark.contexte_public import (
    CLE_CANAL,
    CANAL_SITE,
    filtrer_contexte_public,
)
from api.tests.mark.test_etablissements_heritage import CREIL, SANS_NUMERO, SENLIS_SITE

_OFFER = {"pc_id": "PC-abc123", "sdp": "v=0\r\n", "type": "offer"}
_USER = SimpleNamespace(id=8267, provider_id="user_x")

OUTIL = "reserver_un_rendez_vous"
SECRET = "jeton-secret-de-l-outil"


def _evenements_sensibles() -> list[dict]:
    return [
        build_function_call_start_event(function_name=OUTIL, tool_call_id="c1", arguments={"cle": SECRET}),
        build_function_call_end_event(function_name=OUTIL, tool_call_id="c1", result={"reponse": SECRET}),
        build_bot_text_event(text="Votre rendez-vous est pris"),
        build_user_transcription_event(text="mon numéro est 0601020304", final=True),
        build_node_transition_event(
            node_id="n2", node_name="Prise de rendez-vous", previous_node_id="n1", previous_node_name="Accueil"
        ),
        {"type": "rtf-latency-measured", "payload": {"latency_seconds": 0.8}},
        {"type": "rtf-ttfb-metric", "payload": {"processor": "llm", "ttfb": 0.3}},
        {"type": "rtf-un-type-qui-n-existe-pas-encore", "payload": {"secret": SECRET}},
    ]


async def _session(flux_public_demande: bool):
    """Joue ``_handle_offer`` comme la signalisation, récupère l'expéditeur inscrit, rend ce que le navigateur reçoit."""
    manager = SignalingManager()
    ws = AsyncMock()
    ws.application_state = WebSocketState.CONNECTED  # sinon l'expéditeur ne envoie rien : le cas rouge serait vide
    inscrits = {}

    def inscrire(run_id, expediteur):
        inscrits[run_id] = expediteur

    with (
        patch("api.routes.webrtc_signaling.call_concurrency", MagicMock()),
        patch(
            "api.routes.webrtc_signaling.authorize_workflow_run_start",
            AsyncMock(return_value=SimpleNamespace(has_quota=True, error_code=None, error_message=None)),
        ),
        patch(
            "api.routes.webrtc_signaling.db_client.get_workflow_run",
            AsyncMock(return_value=SimpleNamespace(is_completed=False, initial_context={})),
        ),
        patch("api.routes.webrtc_signaling.get_ice_servers", MagicMock(return_value=[])),
        patch("api.routes.webrtc_signaling.filter_outbound_sdp", MagicMock(side_effect=lambda sdp: sdp)),
        patch("api.routes.webrtc_signaling.register_ws_sender", inscrire),
        patch("api.routes.webrtc_signaling.run_pipeline_smallwebrtc", AsyncMock(return_value=None)),
        patch("api.routes.webrtc_signaling.SmallWebRTCConnection") as pc_cls,
    ):
        pc_cls.return_value.initialize = AsyncMock()
        pc_cls.return_value.get_answer = MagicMock(
            return_value={"sdp": "v=0\r\n", "type": "answer", "pc_id": _OFFER["pc_id"]}
        )
        await manager._handle_offer(
            ws,
            dict(_OFFER),
            10124,
            630140,
            _USER,
            organization_id=1,
            connection_key="10124:630140:8267:1",
            enforce_call_concurrency=False,
            flux_public=flux_public_demande,
        )
    ws.send_json.reset_mock()  # on ne garde que ce qui part APRÈS la réponse à l'offre
    expediteur = inscrits[630140]
    for message in _evenements_sensibles():
        await expediteur(message)
    return [c.args[0] for c in ws.send_json.await_args_list]


async def test_cas_rouge_une_session_publique_ne_recoit_ni_l_appel_ni_le_resultat_d_un_outil():
    recus = await _session(True)
    texte = repr(recus)
    assert OUTIL not in texte, "l'appel d'outil est arrivé au visiteur"
    assert SECRET not in texte, "un argument ou un résultat d'outil est arrivé au visiteur"
    assert not [m for m in recus if m["type"] in ("rtf-function-call-start", "rtf-function-call-end")]
    # Ni la transcription, ni le texte de l'agent, ni le nom des étapes, ni les mesures, ni le type inconnu.
    assert "rendez-vous" not in texte and "0601020304" not in texte and "Prise de" not in texte
    assert recus == []


async def test_temoin_l_ecran_de_test_garde_son_flux_complet():
    recus = await _session(False)
    types = {m["type"] for m in recus}
    assert {"rtf-function-call-start", "rtf-function-call-end", "rtf-bot-text", "rtf-user-transcription"} <= types
    assert SECRET in repr(recus)


async def test_un_type_inconnu_n_arrive_jamais_au_visiteur():
    envoyes = []

    async def navigateur(message):
        envoyes.append(message)

    public = flux_public.expediteur_public(navigateur)
    for inconnu in ("rtf-futur", "", None, 12, "function-call"):
        await public({"type": inconnu, "payload": {"secret": SECRET}})
    await public("pas un dictionnaire")  # type: ignore[arg-type]
    await public({"payload": {}})
    assert envoyes == []


async def test_la_liste_blanche_laisse_passer_la_parole_et_le_mute_sans_contenu():
    envoyes = []

    async def navigateur(message):
        envoyes.append(message)

    public = flux_public.expediteur_public(navigateur)
    await public({"type": "rtf-bot-started-speaking", "payload": {"x": SECRET}, "node_name": "Étape 3"})
    await public({"type": "rtf-bot-stopped-speaking", "payload": {}})
    await public({"type": "rtf-user-mute-started", "payload": {}})
    await public({"type": "rtf-user-mute-stopped", "payload": {}})
    assert [m["type"] for m in envoyes] == [
        "rtf-bot-started-speaking",
        "rtf-bot-stopped-speaking",
        "rtf-user-mute-started",
        "rtf-user-mute-stopped",
    ]
    assert all(m == {"type": m["type"], "payload": {}} for m in envoyes)  # rien d'autre que le type


async def test_l_erreur_du_pipeline_est_generique_sans_detail():
    envoyes = []

    async def navigateur(message):
        envoyes.append(message)

    public = flux_public.expediteur_public(navigateur)
    await public(
        {
            "type": "rtf-pipeline-error",
            "payload": {"error": f"401 clé {SECRET} refusée", "fatal": True, "processor": "ElevenLabsTTS"},
        }
    )
    assert envoyes == [
        {"type": "rtf-pipeline-error", "payload": {"fatal": True, "message": flux_public.MESSAGE_ERREUR_GENERIQUE}}
    ]
    assert SECRET not in repr(envoyes) and "ElevenLabs" not in repr(envoyes)


async def test_la_route_publique_demande_le_flux_filtre_et_la_privee_non():
    from api.routes import webrtc_signaling as module

    # Publique : jeton de session valide, run voix, domaine autorisé.
    session = SimpleNamespace(expires_at=None, embed_token_id=5, workflow_run_id=9)
    jeton = SimpleNamespace(
        id=5, workflow_id=33, organization_id=11, created_by=7, allowed_domains=["https://client.fr"]
    )
    run = SimpleNamespace(workflow_id=33, mode="smallwebrtc")
    ws = MagicMock()
    ws.headers = {"origin": "https://client.fr"}
    ws.close = AsyncMock()
    with (
        patch.object(module, "db_client") as db,
        patch.object(module, "signaling_manager") as manager,
    ):
        db.get_embed_session_by_token = AsyncMock(return_value=session)
        db.get_embed_token_by_id = AsyncMock(return_value=jeton)
        db.get_workflow_run = AsyncMock(return_value=run)
        db.get_user_by_id = AsyncMock(return_value=SimpleNamespace(id=7))
        manager.handle_websocket = AsyncMock()
        await module.public_signaling_websocket(ws, "emb_session_x")
        assert manager.handle_websocket.await_args.kwargs["flux_public"] is True

    with patch.object(module, "db_client") as db, patch.object(module, "signaling_manager") as manager:
        db.get_workflow_run = AsyncMock(return_value=SimpleNamespace(workflow_id=33))
        manager.handle_websocket = AsyncMock()
        user = SimpleNamespace(id=7, selected_organization_id=11)
        await module.signaling_websocket(ws, 33, 9, user)
        assert not manager.handle_websocket.await_args.kwargs.get("flux_public", False)


# ----------------------------------------------------------------------------- contexte (D182)
def test_le_contexte_de_la_page_ne_choisit_ni_le_lieu_ni_le_numero():
    page = {
        "page_url": "https://client.fr/tarifs",
        "today": "2026-11-03",
        "etablissement_id": "creil",
        "called_number": "+33344000001",
        "etablissement_de_lappel": "senlis",
        "greeting_override": "Bonjour pirate",
        "numero_transfert": "+33600000000",
        "equipe": {"x": 1},
        CLE_CANAL: "telephone",
        "verification_appelant": True,
    }
    assert filtrer_contexte_public(page, {}) == {"page_url": "https://client.fr/tarifs", "today": "2026-11-03"}


def test_une_cle_declaree_par_l_agent_passe_une_cle_mark_declaree_par_erreur_non():
    page = {"plan_choisi": "pro", "etablissement_id": "creil", "autre": 1}
    configs = {"contexte_public_cles": ["plan_choisi", "etablissement_id"]}
    assert filtrer_contexte_public(page, configs) == {"plan_choisi": "pro"}


# ----------------------------------------------------------------------------- établissement
CATALOGUE_3 = CatalogueEtablissements(etablissements=[CREIL, SENLIS_SITE, SANS_NUMERO])


def test_un_agent_de_site_sans_lieu_ne_recoit_aucun_etablissement():
    contexte = {CLE_CANAL: CANAL_SITE}
    assert choisir_etablissement(CATALOGUE_3, contexte, [], None) is None


def test_un_agent_de_site_ne_prend_ni_l_essai_ni_le_premier_ni_le_numero_appele():
    contexte = {
        CLE_CANAL: CANAL_SITE,
        "etablissement_id": "senlis",  # « essai »
        "called_number": "+33344000002",
    }
    assert choisir_etablissement(CATALOGUE_3, contexte, ["+33344000001"], None) is None


def test_un_agent_de_site_avec_lieu_sert_sa_fiche():
    choix = choisir_etablissement(CATALOGUE_3, {CLE_CANAL: CANAL_SITE}, [], "senlis")
    assert choix is not None and choix[0].id == "senlis"


def test_une_fiche_disparue_donne_aucun_etablissement_pas_le_premier():
    assert choisir_etablissement(CATALOGUE_3, {CLE_CANAL: CANAL_SITE}, [], "supprimee") is None


def test_un_agent_de_telephone_garde_son_comportement_d_avant():
    # Sans numéro appelé ni fiche : « le premier » (le chemin d'avant, intact).
    choix = choisir_etablissement(CATALOGUE_3, {}, [], None)
    assert choix is not None and choix[0].id == "creil" and choix[1] == "premier"
