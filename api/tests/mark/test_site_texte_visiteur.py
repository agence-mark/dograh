"""[.mark] Builder partie 2, U10 / S5 : le texte tapé par le visiteur pendant l'appel du widget.

| Test | Ce qu'il prouve |
|---|---|
| le texte arrive au modèle | le moteur ajoute UN message ``user`` et relance le modèle (``run_llm``) |
| interruption propre | si l'agent parlait : interruption, circuit vidé, PUIS ajout (dans cet ordre) ; sinon pas d'interruption |
| rien après la fin | appel fini ou pas monté : ``False``, aucun cadre envoyé ; porte retirée : ``termine`` |
| bornes | vide, trop long, pas du texte, trop rapide, trop par minute, plafond de la conversation |
| nettoyage | caractères de contrôle écartés, espaces resserrés |
| verbatim | le texte est gardé comme un tour écrit (``ecrit: true``) |
| signalisation | publique : la porte de SA conversation ; privée (écran de test) : ignoré ; sans porte : ``termine`` |
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pipecat.frames.frames import LLMMessagesAppendFrame
from starlette.websockets import WebSocketState

from api.routes.webrtc_signaling import SignalingManager
from api.services.site_mark import texte_visiteur as tv
from api.services.workflow.pipecat_engine import PipecatEngine


def _moteur(*, parle: bool = False, fini: bool = False, monte: bool = True):
    ordre: list[str] = []

    async def ajout(_trame):
        ordre.append("ajout")

    async def interruption():
        ordre.append("interruption")

    async def vidage():
        ordre.append("vidage")
        return True

    faux = SimpleNamespace(
        _call_disposed=fini,
        call_worker=object() if monte else None,
        _answer_user_aggregator=SimpleNamespace(broadcast_interruption=interruption) if monte else None,
        call_monitor=SimpleNamespace(bot_speaking=parle),
        active_agent=SimpleNamespace(queue_frame=AsyncMock(side_effect=ajout)),
        drain_call_pipeline=vidage,
    )
    return faux, ordre


async def _injecter(faux, texte="Dupont"):
    return await PipecatEngine.injecter_texte_visiteur(faux, texte)


async def test_le_texte_arrive_au_modele_comme_un_tour_utilisateur():
    faux, ordre = _moteur()
    assert await _injecter(faux, "mon numéro est le 06 12") is True
    trame = faux.active_agent.queue_frame.call_args.args[0]
    assert isinstance(trame, LLMMessagesAppendFrame)
    assert trame.messages == [{"role": "user", "content": "mon numéro est le 06 12"}]
    assert trame.run_llm is True
    assert ordre == ["ajout"]


async def test_si_l_agent_parlait_interruption_puis_vidage_puis_ajout():
    faux, ordre = _moteur(parle=True)
    assert await _injecter(faux) is True
    assert ordre == ["interruption", "vidage", "ajout"]


async def test_rien_ne_s_envoie_apres_la_fin():
    for faux, _ in (_moteur(fini=True), _moteur(monte=False)):
        assert await _injecter(faux) is False
        faux.active_agent.queue_frame.assert_not_awaited()
    # L'appel se termine pendant le vidage : le message n'est pas ajouté.
    faux, _ordre = _moteur(parle=True)

    async def fin_pendant_le_vidage():
        faux._call_disposed = True
        return True

    faux.drain_call_pipeline = fin_pendant_le_vidage
    assert await _injecter(faux) is False
    faux.active_agent.queue_frame.assert_not_awaited()


class Horloge:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def _porte(horloge=None, reussi=True):
    recus: list[str] = []

    async def injecter(texte):
        recus.append(texte)
        return reussi

    return tv.PorteTexte(injecter, horloge or Horloge()), recus


async def test_bornes_de_la_porte():
    h = Horloge()
    porte, recus = _porte(h)
    assert await porte.recevoir("   ") == tv.VIDE
    assert await porte.recevoir(None) == tv.INVALIDE
    assert await porte.recevoir({"a": 1}) == tv.INVALIDE
    assert await porte.recevoir("x" * (tv.MAX_CARACTERES + 1)) == tv.TROP_LONG
    assert recus == []
    assert await porte.recevoir("x" * tv.MAX_CARACTERES) == tv.OK
    assert await porte.recevoir("deux") == tv.TROP_RAPIDE
    h.t += 2
    assert await porte.recevoir("deux") == tv.OK
    assert len(recus) == 2


async def test_frequence_par_minute_et_plafond_de_la_conversation():
    h = Horloge()
    porte, _recus = _porte(h)
    for _ in range(tv.MAX_PAR_MINUTE):
        h.t += 2
        assert await porte.recevoir("a") == tv.OK
    h.t += 2
    assert await porte.recevoir("a") == tv.TROP_RAPIDE
    h.t += 61
    assert await porte.recevoir("a") == tv.OK
    porte2, _ = _porte(h)
    porte2._total = tv.MAX_PAR_CONVERSATION
    assert await porte2.recevoir("a") == tv.PLAFOND


async def test_porte_fermee_ou_injection_refusee():
    porte, recus = _porte()
    porte.fermer()
    assert await porte.recevoir("a") == tv.TERMINE
    assert recus == []
    refus, _ = _porte(reussi=False)
    assert await refus.recevoir("a") == tv.TERMINE


def test_nettoyage():
    assert tv.nettoyer("  a\x00b\x07 \n  c\t d  ") == "a b c d"
    assert tv.nettoyer(12) is None


async def test_le_texte_est_garde_dans_le_verbatim_comme_un_tour_ecrit():
    engine = SimpleNamespace(injecter_texte_visiteur=AsyncMock(return_value=True))
    buffer = SimpleNamespace(append=AsyncMock())
    assert await tv.fabriquer_injecteur(engine, buffer)("Dupont") is True
    evenement = buffer.append.call_args.args[0]
    assert evenement["payload"]["text"] == "Dupont"
    assert evenement["payload"]["ecrit"] is True
    engine.injecter_texte_visiteur = AsyncMock(return_value=False)
    buffer.append.reset_mock()
    assert await tv.fabriquer_injecteur(engine, buffer)("Dupont") is False
    buffer.append.assert_not_awaited()


@pytest.fixture
def porte_enregistree():
    porte, recus = _porte()
    tv.enregistrer_porte(901, porte)
    yield recus
    tv.retirer_porte(901)


def _ws():
    return SimpleNamespace(application_state=WebSocketState.CONNECTED, send_json=AsyncMock())


async def _message(flux_public, ws, run=901, payload=None):
    gestionnaire = SignalingManager()
    await gestionnaire._handle_message(
        ws,
        {"type": "texte-visiteur", "payload": payload if payload is not None else {"texte": "Dupont"}},
        9,
        run,
        SimpleNamespace(id=1),
        5,
        "cle",
        False,
        "public_embed",
        False,
        flux_public,
    )


async def test_signalisation_publique_passe_par_la_porte_de_sa_conversation(porte_enregistree):
    ws = _ws()
    await _message(True, ws)
    assert porte_enregistree == ["Dupont"]
    ws.send_json.assert_awaited_once_with({"type": "texte-visiteur-resultat", "payload": {"ok": True, "code": "ok"}})


async def test_une_autre_conversation_n_atteint_pas_cette_porte(porte_enregistree):
    ws = _ws()
    await _message(True, ws, run=902)
    assert porte_enregistree == []
    assert ws.send_json.call_args.args[0]["payload"] == {"ok": False, "code": "termine"}


async def test_ecran_de_test_ignore_le_message(porte_enregistree):
    ws = _ws()
    await _message(False, ws)
    assert porte_enregistree == []
    ws.send_json.assert_not_awaited()


async def test_charge_utile_mal_formee_refusee_proprement(porte_enregistree):
    ws = _ws()
    await _message(True, ws, payload={"texte": ["a"]})
    assert ws.send_json.call_args.args[0]["payload"]["code"] == "invalide"
    assert porte_enregistree == []


async def test_porte_retiree_a_la_fin_de_l_appel(porte_enregistree):
    tv.retirer_porte(901)
    ws = _ws()
    await _message(True, ws)
    assert ws.send_json.call_args.args[0]["payload"]["code"] == "termine"
    assert porte_enregistree == []
