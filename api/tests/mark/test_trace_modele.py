"""[.mark] La trace du cerveau (chantier repliques-coupees, lot 1, décision D1 du 14/10).

Plan `Labo-agent-vocal/plans/repliques-coupees/`, cas rouges dans `corpus.md`. Des répliques
sortent coupées en pleine phrase (run 1176, tour 7 : « C'est noté. Avez-vous une adresse mail
pour que ») ; la trace dit, pour chaque réponse demandée au cerveau, ce qui est parti (la
requête exacte, jamais une clé) et ce qui est revenu (chaque morceau, son arrêt, le compte de
jetons, comment le flux a fini), et ce que le lecteur de portes a laissé partir à la voix.

| Test | Ce qu'il prouve |
|---|---|
| case éteinte | rien n'est écrit dans la fiche (à l'octet), la requête est la même |
| flux de Qwen3.8 (R1) | par le vrai service puis le vrai lecteur : 6 morceaux dont le dernier porte texte et arrêt, tracés en entier ; texte dit = texte reçu ; fin « complet » |
| jamais de clé | ni la clé du client ni un en-tête glissé dans les réglages n'entrent dans la trace |
| flux lâché en route | une lecture arrêtée avant la fin du flux se voit (« ferme_avant_la_fin ») |
| appel ponctuel | ``run_inference`` du même service n'est jamais tracé |
| Mistral | le service Mistral porte la même trace |
| branchement | case absente, case non booléenne, service sans trace (temps réel) : rien |
| clavier (R1) | par les vraies routes du clavier en greffier : l'entrée du tour existe, ce qui est dit y est |
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from openai.types.chat import ChatCompletionChunk
from pipecat.frames.frames import LLMContextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.tests.utils import SleepFrame

from api.services.pipecat import greffier as module_greffier
from api.services.pipecat.lecteur_de_portes import LecteurDePortes
from api.services.pipecat.service_factory import (
    DograhMistralLLMService,
    DograhOpenAILLMService,
    create_llm_service,
)
from api.services.pipecat.trace_modele import (
    ATTRIBUT_TRACE,
    CLE_TRACE_REQUETES,
    FIN_COMPLETE,
    FIN_FERMEE,
    TRACE_REQUETES,
    TraceDuModele,
    TraceModeleMixin,
    brancher_la_trace,
)
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_MODE,
    CLE_PORTES_DANS_LA_REPONSE,
    MODE_GREFFIER,
    ReglagesFiche,
)
from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter
from api.tests.mark.test_fournisseur_compatible_openai import _openai
from api.tests.mark.test_greffier import _Modele
from api.tests.mark.test_porte_parlee_consigne import _definition
from api.tests.mark.test_porte_parlee_processeur import _Ordre
from api.tests.mark.test_post_scriptum import DEMARRAGE_S
from pipecat.tests import MockLLMService, run_test

CLE = "cle-de-test-jamais-envoyee"
GREFFIER_PORTES = {**FICHE, CLE_MODE: MODE_GREFFIER, CLE_PORTES_DANS_LA_REPONSE: True}

# Le tour 7 du run 1176, tel que Scaleway l'envoie quand il est entier (sonde du 14/10) :
# six gros morceaux, le dernier porte le texte ET l'arrêt ET le compte de jetons.
MORCEAUX_QWEN = [
    "C'est noté.",
    " Avez-vous une adresse",
    " mail pour",
    " que nous",
    " puissions vous",
    " écrire ?",
]
PHRASE = "".join(MORCEAUX_QWEN)


def _morceau(texte: str | None, *, arret: str | None = None, usage: dict | None = None):
    return ChatCompletionChunk.model_validate(
        {
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "qwen3.8-27b",
            "choices": [
                {"index": 0, "delta": {"content": texte}, "finish_reason": arret}
            ],
            "usage": usage,
        }
    )


def _flux_qwen() -> list[ChatCompletionChunk]:
    *debut, dernier = MORCEAUX_QWEN
    return [_morceau(t) for t in debut] + [
        _morceau(
            dernier,
            arret="stop",
            usage={"prompt_tokens": 4381, "completion_tokens": 20, "total_tokens": 4401},
        )
    ]


class _Flux:
    """Le flux du client HTTP : itérable une fois, fermable."""

    def __init__(self, morceaux, *, attente: float = 0.0):
        self._morceaux = morceaux
        self._attente = attente
        self.ferme = False

    def __aiter__(self):
        return self._parcourir()

    async def _parcourir(self):
        for m in self._morceaux:
            if self._attente:
                await asyncio.sleep(self._attente)
            yield m

    async def close(self):
        self.ferme = True


def _client(morceaux, envoyes: list[dict]):
    async def create(**params):
        envoyes.append(params)
        return _Flux(morceaux)

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def _service(morceaux=None, **reglages) -> tuple[DograhOpenAILLMService, list[dict]]:
    service = create_llm_service(_openai(model="qwen3.8-27b", **reglages))
    assert isinstance(service, DograhOpenAILLMService)
    envoyes: list[dict] = []
    service._client = _client(_flux_qwen() if morceaux is None else morceaux, envoyes)
    return service, envoyes


def _moteur(fiche: dict) -> SimpleNamespace:
    return SimpleNamespace(_gathered_context=fiche)


def _contexte() -> LLMContext:
    return LLMContext(
        messages=[
            {"role": "system", "content": "Tu es Marie."},
            {"role": "user", "content": "15 rue de la Gare."},
        ]
    )


def _lecteur(fiche: dict, trace: TraceDuModele | None) -> LecteurDePortes:
    reglages = ReglagesFiche.depuis(GREFFIER_PORTES)
    assert reglages is not None and reglages.portes_dans_la_reponse
    return LecteurDePortes(
        reglages=reglages,
        fiche=lambda: fiche,
        messages=list,
        attendu=lambda: True,
        portes=SimpleNamespace(),
        trace=trace,
    )


async def _jouer(service, lecteur) -> _Ordre:
    ordre = _Ordre()
    await run_test(
        Pipeline([service, lecteur, ordre]),
        frames_to_send=[LLMContextFrame(_contexte()), SleepFrame(sleep=0.3)],
        start_timeout=DEMARRAGE_S,
    )
    return ordre


# --------------------------------------------------------------------------- #
# 1. Case éteinte : rien ne change
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_case_eteinte_rien_n_est_ecrit_et_la_requete_est_la_meme():
    fiche = {"tour_appelant": 7}
    avant = json.dumps(fiche, sort_keys=True)
    service, envoyes = _service()
    assert brancher_la_trace(_moteur(fiche), service, {}) is None
    assert brancher_la_trace(_moteur(fiche), service, {CLE_TRACE_REQUETES: "oui"}) is None
    assert service.mark_trace is None
    ordre = await _jouer(service, _lecteur(fiche, None))
    assert ordre.dit == PHRASE
    assert json.dumps(fiche, sort_keys=True) == avant

    # La même réponse, case allumée : la requête qui part est identique.
    fiche_allumee = {"tour_appelant": 7}
    service_allume, envoyes_allume = _service()
    trace = brancher_la_trace(
        _moteur(fiche_allumee), service_allume, {CLE_TRACE_REQUETES: True}
    )
    assert trace is not None
    await _jouer(service_allume, _lecteur(fiche_allumee, trace))
    assert envoyes_allume == envoyes


# --------------------------------------------------------------------------- #
# 2. Le flux de Qwen3.8, par le vrai service et le vrai lecteur (R1)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_le_flux_en_six_morceaux_est_trace_en_entier_jusqu_au_lecteur():
    fiche = {"tour_appelant": 7}
    service, _ = _service()
    moteur = _moteur(fiche)
    trace = brancher_la_trace(moteur, service, {CLE_TRACE_REQUETES: True})
    assert getattr(moteur, ATTRIBUT_TRACE) is trace
    ordre = await _jouer(service, _lecteur(fiche, trace))

    assert ordre.dit == PHRASE
    [entree] = fiche[TRACE_REQUETES]
    assert entree["tour"] == 7
    assert [m.get("texte") for m in entree["morceaux"]] == MORCEAUX_QWEN
    assert entree["morceaux"][-1]["finish_reason"] == "stop"
    assert all("finish_reason" not in m for m in entree["morceaux"][:-1])
    assert all(isinstance(m["ms"], int) for m in entree["morceaux"])
    assert entree["usage"]["completion_tokens"] == 20
    assert entree["fin"] == FIN_COMPLETE
    assert entree["texte_dit"] == PHRASE
    assert "interrompue" not in entree
    parametres = entree["parametres"]
    assert parametres["model"] == "qwen3.8-27b" and parametres["stream"] is True
    assert parametres["messages"][-1] == {"role": "user", "content": "15 rue de la Gare."}
    # Lisible en JSON tel quel : il part dans la fiche de l'appel.
    json.dumps(fiche)


@pytest.mark.asyncio
async def test_la_trace_ne_contient_jamais_de_cle():
    fiche: dict = {}
    service, envoyes = _service()
    # Un en-tête glissé dans les réglages (un réglage « extra ») ne doit jamais être recopié.
    service._settings.extra = {"extra_headers": {"Authorization": f"Bearer {CLE}"}}
    trace = brancher_la_trace(_moteur(fiche), service, {CLE_TRACE_REQUETES: True})
    await _jouer(service, _lecteur(fiche, trace))
    assert envoyes and envoyes[0]["extra_headers"]["Authorization"].endswith(CLE)
    ecrit = json.dumps(fiche)
    assert CLE not in ecrit
    assert "extra_headers" not in fiche[TRACE_REQUETES][0]["parametres"]


@pytest.mark.asyncio
async def test_un_flux_lache_en_route_se_voit():
    fiche: dict = {}
    service, _ = _service()
    trace = brancher_la_trace(_moteur(fiche), service, {CLE_TRACE_REQUETES: True})
    flux = await service.get_chat_completions(_contexte())
    iterateur = flux.__aiter__()
    await iterateur.__anext__()
    await iterateur.aclose()
    [entree] = fiche[TRACE_REQUETES]
    assert entree["fin"] == FIN_FERMEE
    assert [m.get("texte") for m in entree["morceaux"]] == MORCEAUX_QWEN[:1]
    assert trace is not None


@pytest.mark.asyncio
async def test_un_appel_ponctuel_du_meme_service_n_est_jamais_trace():
    fiche: dict = {}
    service, _ = _service()
    brancher_la_trace(_moteur(fiche), service, {CLE_TRACE_REQUETES: True})

    async def create(**params):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="oui"))]
        )

    service._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    await service.run_inference(_contexte())
    assert TRACE_REQUETES not in fiche


def test_le_service_mistral_porte_la_meme_trace():
    service = DograhMistralLLMService(api_key=CLE, model="mistral-large-2512")
    assert isinstance(service, TraceModeleMixin) and service.mark_trace is None
    fiche: dict = {}
    trace = brancher_la_trace(_moteur(fiche), service, {CLE_TRACE_REQUETES: True})
    entree = trace.ouvrir()
    service._mark_entree_en_cours = entree
    service.build_chat_completion_params(
        {"messages": [{"role": "user", "content": "bonjour"}], "tools": [], "tool_choice": None}
    )
    assert fiche[TRACE_REQUETES][0]["parametres"]["model"] == "mistral-large-2512"
    assert CLE not in json.dumps(fiche)


def test_sans_trace_possible_rien_n_est_branche():
    fiche: dict = {}
    temps_reel = SimpleNamespace()  # un service sans la trace (temps réel, faux modèle)
    assert brancher_la_trace(_moteur(fiche), temps_reel, {CLE_TRACE_REQUETES: True}) is None
    assert brancher_la_trace(_moteur(fiche), None, {CLE_TRACE_REQUETES: True}) is None
    assert fiche == {}


# --------------------------------------------------------------------------- #
# 3. Au clavier, par les vraies routes (R1)
# --------------------------------------------------------------------------- #


class _ModeleTrace(TraceModeleMixin, MockLLMService):
    """Le faux modèle de Pipecat, avec la trace des services de la conversation."""

    def build_chat_completion_params(self, params_from_context):
        return self._mark_tracer_parametres(
            super().build_chat_completion_params(params_from_context)
        )


async def _un_tour(test_client_factory, user, workflow, repliques):
    llm = [_ModeleTrace(mock_steps=[], chunk_delay=0.001)]  # accueil (texte fixe)
    llm += [_ModeleTrace(mock_steps=repliques, chunk_delay=0.001)]
    llm += [MockLLMService(mock_steps=[], chunk_delay=0.001) for _ in range(3)]
    async with test_client_factory(user) as client:
        with (
            patch("api.services.workflow.text_chat_runner.create_llm_service", side_effect=llm),
            patch(
                "api.services.workflow.text_chat_runner.db_client.has_active_recordings",
                new=AsyncMock(return_value=False),
            ),
            patch.object(
                module_greffier,
                "service_du_greffier",
                return_value=(_Modele({}), {"provider": "mistral", "model": "m"}),
            ),
        ):
            creee = await client.post(f"/api/v1/workflow/{workflow.id}/text-chat/sessions", json={})
            assert creee.status_code == 200, creee.text
            session = creee.json()
            reponse = await client.post(
                f"/api/v1/workflow/{workflow.id}/text-chat/sessions/"
                f"{session['workflow_run_id']}/messages",
                json={"text": "15 rue de la Gare.", "expected_revision": session["revision"]},
            )
            assert reponse.status_code == 200, reponse.text
            return reponse.json()


@pytest.mark.asyncio
async def test_au_clavier_la_trace_porte_le_tour_et_ce_qui_est_dit(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(
        db_session,
        async_session,
        {**GREFFIER_PORTES, CLE_TRACE_REQUETES: True},
        _definition(),
    )
    charge = await _un_tour(
        test_client_factory, user, workflow, [MockLLMService.create_text_chunks(PHRASE)]
    )
    contexte = charge["checkpoint"]["gathered_context"]
    entrees = contexte[TRACE_REQUETES]
    assert entrees, contexte
    derniere = entrees[-1]
    assert derniere["texte_dit"] == PHRASE
    assert "".join(m.get("texte", "") for m in derniere["morceaux"]) == PHRASE
    assert derniere["fin"] == FIN_COMPLETE
    assert derniere["parametres"]["messages"][-1]["content"] == "15 rue de la Gare."


@pytest.mark.asyncio
async def test_au_clavier_case_eteinte_aucune_trace(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, GREFFIER_PORTES, _definition())
    charge = await _un_tour(
        test_client_factory, user, workflow, [MockLLMService.create_text_chunks(PHRASE)]
    )
    assert TRACE_REQUETES not in charge["checkpoint"]["gathered_context"]


# --------------------------------------------------------------------------- #
# 4. La requête telle qu'elle part : l'état de la fiche compris (constat du 14/10)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_la_trace_voit_l_etat_de_la_fiche_ajoute_par_le_moteur():
    """Run 1185 : la trace photographiait la requête avant que le moteur y glisse l'état
    de la fiche (``montrer_la_fiche``, posé à sa création, donc AVANT la trace)."""
    from api.services.workflow.fiche_au_fil_de_leau import montrer_la_fiche

    fiche = {"tour_appelant": 5, "nom": "Delaunay", "fiche_etat": {"nom": {"sure": True}}}
    service, envoyes = _service()
    reglages = ReglagesFiche.depuis(GREFFIER_PORTES)
    assert montrer_la_fiche(service, reglages, lambda: fiche)
    brancher_la_trace(_moteur(fiche), service, {CLE_TRACE_REQUETES: True})
    flux = await service.get_chat_completions(_contexte())
    async for _ in flux:
        pass
    parties = fiche[TRACE_REQUETES][0]["parametres"]["messages"]
    assert any("Delaunay" in str(m.get("content")) for m in parties[:-1]), parties
    assert parties == envoyes[0]["messages"]


# --------------------------------------------------------------------------- #
# Revue du 14/10, retenue par Evan : la trace ne sort jamais vers les webhooks.
# --------------------------------------------------------------------------- #


def test_la_trace_n_est_jamais_envoyee_aux_integrations():
    from types import SimpleNamespace

    from api.services.pipecat.trace_modele import TRACE_REQUETES, sans_la_trace
    from api.tasks.run_integrations import _build_render_context

    fiche = {"nom": "Durand", TRACE_REQUETES: [{"tour": 1, "parametres": {"messages": []}}]}
    run = SimpleNamespace(
        id=1,
        name="run",
        workflow_id=2,
        workflow=None,
        campaign_id=None,
        created_at=None,
        initial_context={},
        gathered_context=fiche,
        usage_info={},
        annotations={},
        extra={},
        recording_url=None,
        transcript_url=None,
    )
    contexte = _build_render_context(run)
    assert contexte["gathered_context"] == {"nom": "Durand"}
    # La fiche de l'appel, elle, garde la trace (elle reste dans Dograh).
    assert TRACE_REQUETES in fiche
    assert sans_la_trace(None) == {}
    assert sans_la_trace({"nom": "x"}) == {"nom": "x"}


def test_les_resultats_des_outils_ne_partent_jamais_aux_integrations():
    """[.mark] Lot 3 de cloture-code (b10e829f) : le moteur garde les arguments et les réponses
    des outils dans ``tool_results`` ; comme la trace, ils ne quittent jamais Dograh."""
    from types import SimpleNamespace

    from api.services.pipecat.trace_modele import RESULTATS_DES_OUTILS
    from api.services.workflow.pipecat_engine import ENGINE_OWNED_CONTEXT_KEYS
    from api.tasks.run_integrations import _build_render_context

    assert RESULTATS_DES_OUTILS in ENGINE_OWNED_CONTEXT_KEYS
    fiche = {
        "nom": "Durand",
        RESULTATS_DES_OUTILS: [{"function_name": "noter", "arguments": {"tel": "0612"}}],
    }
    run = SimpleNamespace(
        id=1,
        name="run",
        workflow_id=2,
        workflow=None,
        campaign_id=None,
        created_at=None,
        initial_context={},
        gathered_context=fiche,
        usage_info={},
        annotations={},
        extra={},
        recording_url=None,
        transcript_url=None,
    )
    assert _build_render_context(run)["gathered_context"] == {"nom": "Durand"}
    assert RESULTATS_DES_OUTILS in fiche
