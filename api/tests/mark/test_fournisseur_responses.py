"""[.mark] Le fournisseur compatible OpenAI par l'API Responses (orchestrateur-trois-cerveaux, lot 1, D11 et D19).

La question à laquelle ce fichier répond, et elle seule :

    Un modèle compatible OpenAI (gpt-oss-120b chez Scaleway) réglé sur « API : responses » à
    l'écran est-il construit par la fabrique avec ses réglages, porte-t-il les couches .mark du
    cerveau (main passée, texte du cerveau, reprise sans flux, trace, garde du délai, réflexion
    de secours), traverse-t-il un outil de bout en bout (appel, résultat, relance) -- et un
    agent réglé sur ``chat_completions`` reste-t-il exactement ce qu'il était ?

| Test | Ce qu'il prouve |
|---|---|
| construction | ``api: responses`` construit le service Responses, avec modèle, température, raisonnement, longueur, cache, adresse du fournisseur |
| ``include`` | refusé par Scaleway (400, constaté le 17/10) : jamais envoyé hors d'OpenAI |
| réglages hors API | graine et pénalités partent dans ``extra_body``, seulement si réglées |
| ``chat_completions`` | l'API par défaut construit le même service, la même requête qu'avant, à l'octet |
| écran | le champ ``api`` est au groupe Technique, libellé FR/EN, choix fermé |
| estampille | le run dit son API quand ce n'est pas l'usuelle, rien sinon |
| couches .mark (deux API) | main passée, note de passation, appel écrit en texte, crochets, flux avalé, garde du délai, trace, réflexion de secours |
| outil (R1) | par le vrai service et un faux serveur Responses nourri de la réponse réelle de Scaleway : appel, résultat, relance |
| passage de nœud | un appel de passage attend la fin de la voix quand la réponse a parlé |
| fiche | l'état de la fiche entre dans ``input`` comme dans ``messages`` |
| greffier | une passe en API Responses rend son texte et ses jetons |
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion
from openai.types.chat.chat_completion_chunk import (
    ChatCompletionChunk,
    Choice,
    ChoiceDelta,
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
)
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    FunctionCallsStartedFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMTextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.llm_service import FunctionCallParams
from pipecat.tests import run_test
from pipecat.tests.utils import SleepFrame
from pipecat.utils.types import NOT_GIVEN

from api.services.configuration.registry import OpenAILLMService as OpenAIConfig
from api.services.groupe.passations import NOTE_DE_PASSATION
from api.services.panne.delai_modele import DelaiModeleMixin
from api.services.pipecat import greffier as module_greffier
from api.services.pipecat.main_passee import muter, rendre_la_parole
from api.services.pipecat.replique_inachevee import ReflexionDeRelanceMixin
from api.services.pipecat.responses_llm import MarkOpenAIResponsesLLMService
from api.services.pipecat.service_factory import (
    DograhOpenAILLMService,
    create_llm_service,
    stamp_sampling_settings,
)
from api.services.pipecat.trace_modele import (
    CLE_TRACE_REQUETES,
    FIN_COMPLETE,
    TRACE_REQUETES,
    TraceModeleMixin,
    brancher_la_trace,
)
from api.services.workflow.fiche_au_fil_de_leau import ENTETE_ETAT, montrer_la_fiche
from api.tests.mark.test_fiche_montree import _reglages as _reglages_de_fiche
from api.tests.mark.test_post_scriptum import DEMARRAGE_S

SCALEWAY = "https://api.scaleway.ai/v1"
MODELE = "openai/gpt-oss-120b:fp4"
CLE = "cle-de-test-jamais-envoyee"
FIXTURE = json.loads(
    (Path(__file__).parent / "donnees" / "requete-unitaire-responses-gpt-oss.json").read_text(
        encoding="utf-8"
    )
)
OUTIL = FunctionSchema(
    name="meteo_du_jour",
    description="Donne la météo d'une ville.",
    properties={"ville": {"type": "string"}},
    required=["ville"],
)
DEUX_API = ["chat_completions", "responses"]


def _config(api: str | None = None, model: str = MODELE, **reglages) -> SimpleNamespace:
    """Les réglages de l'écran : le fournisseur compatible OpenAI, chez Scaleway."""
    if api is not None:
        reglages["api"] = api
    return SimpleNamespace(
        llm=OpenAIConfig(api_key=CLE, model=model, base_url=SCALEWAY, **reglages)
    )


def _contexte(*messages: dict, outil: bool = True) -> LLMContext:
    messages = messages or ({"role": "user", "content": "Quelle est la météo à Beauvais ?"},)
    return LLMContext(
        messages=[{"role": "system", "content": "Tu es Marie."}, *messages],
        tools=ToolsSchema(standard_tools=[OUTIL]) if outil else NOT_GIVEN,
    )


# --- Un fournisseur imité, dans les deux API ---------------------------------------------------


class Rep:
    """Ce que le fournisseur répond à une requête : du texte, des appels d'outil, des jetons."""

    def __init__(self, texte=None, appels=(), jetons=20, attente=0.0):
        self.texte = texte
        self.appels = list(appels)  # [(nom, arguments JSON, id)]
        self.jetons = jetons
        self.attente = attente


def _reponse_responses(rep: Rep) -> dict:
    """Une réponse Responses, bâtie comme celle de Scaleway (fixture du lot 0) : le raisonnement
    d'abord, puis le message ou les appels."""
    sortie: list[dict] = [
        {
            "id": "rs_1",
            "type": "reasoning",
            "summary": [],
            "content": [{"type": "reasoning_text", "text": "Je réfléchis."}],
            "encrypted_content": None,
            "status": None,
        }
    ]
    if rep.texte:
        sortie.append(
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": rep.texte, "annotations": []}],
            }
        )
    for i, (nom, arguments, ident) in enumerate(rep.appels):
        sortie.append(
            {
                "id": f"fc_{ident}",
                "type": "function_call",
                "call_id": ident,
                "name": nom,
                "arguments": arguments,
                "status": "completed",
            }
        )
    return {
        "id": "resp_1",
        "object": "response",
        "model": "gpt-oss-120b",
        "status": "completed",
        "output": sortie,
        "usage": {
            "input_tokens": 100,
            "output_tokens": rep.jetons,
            "total_tokens": 100 + rep.jetons,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


def _evenements(reponse: dict) -> list[dict]:
    """La réponse racontée en événements de flux, comme le fournisseur les envoie."""
    evenements: list[dict] = [
        {"type": "response.created", "response": {**reponse, "status": "in_progress", "output": []}}
    ]
    for i, item in enumerate(reponse["output"]):
        if item["type"] == "reasoning":
            evenements += [
                {"type": "response.output_item.added", "output_index": i, "item": {**item, "content": []}},
                {"type": "response.reasoning_text.delta", "output_index": i, "item_id": item["id"],
                 "content_index": 0, "delta": item["content"][0]["text"]},
                {"type": "response.output_item.done", "output_index": i, "item": item},
            ]
        elif item["type"] == "message":
            texte = item["content"][0]["text"]
            evenements.append(
                {"type": "response.output_item.added", "output_index": i, "item": {**item, "content": []}}
            )
            milieu = max(1, len(texte) // 2)
            for morceau in (texte[:milieu], texte[milieu:]):
                if morceau:
                    evenements.append(
                        {"type": "response.output_text.delta", "output_index": i, "item_id": item["id"],
                         "content_index": 0, "delta": morceau}
                    )
            evenements.append({"type": "response.output_item.done", "output_index": i, "item": item})
        elif item["type"] == "function_call":
            evenements += [
                {"type": "response.output_item.added", "output_index": i, "item": {**item, "arguments": ""}},
                {"type": "response.function_call_arguments.delta", "output_index": i,
                 "item_id": item["id"], "delta": item["arguments"]},
                {"type": "response.function_call_arguments.done", "output_index": i,
                 "item_id": item["id"], "name": item["name"], "arguments": item["arguments"]},
                {"type": "response.output_item.done", "output_index": i, "item": item},
            ]
    evenements.append({"type": "response.completed", "response": reponse})
    return [{**e, "sequence_number": n} for n, e in enumerate(evenements)]


class FauxServeurResponses:
    """Un faux serveur Responses, au niveau HTTP : le vrai client OpenAI, le vrai service.
    Chaque requête ``POST …/responses`` reçoit la réponse suivante, en flux (``stream`` vrai)
    ou d'un bloc. Les requêtes reçues sont gardées telles quelles dans ``vus``."""

    def __init__(self, reponses):
        self._reponses = list(reponses)
        self.vus: list[dict] = []
        self.client = AsyncOpenAI(
            api_key=CLE,
            base_url=SCALEWAY,
            max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(self._repondre)),
        )

    async def _repondre(self, requete: httpx.Request) -> httpx.Response:
        assert requete.url.path.endswith("/responses"), requete.url
        corps = json.loads(requete.content)
        self.vus.append(corps)
        rep = self._reponses.pop(0)
        if isinstance(rep, Rep):
            if rep.attente:
                await asyncio.sleep(rep.attente)
            reponse = _reponse_responses(rep)
        else:
            reponse = rep  # une réponse réelle, telle que le fournisseur l'a envoyée
        if not corps.get("stream"):
            return httpx.Response(200, json=reponse)
        flux = "".join(
            f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in _evenements(reponse)
        )
        return httpx.Response(
            200, content=flux.encode(), headers={"content-type": "text/event-stream"}
        )


_COMMUN = {"id": "c", "created": 0, "model": "m", "object": "chat.completion.chunk"}


class _FluxChat:
    def __init__(self, morceaux, attente=0.0):
        self._morceaux = morceaux
        self._attente = attente

    def __aiter__(self):
        return self._parcourir()

    async def _parcourir(self):
        for m in self._morceaux:
            if self._attente:
                await asyncio.sleep(self._attente)
            yield m

    async def close(self):
        return None


def _morceaux_chat(rep: Rep) -> list[ChatCompletionChunk]:
    def morceau(delta=None, fin=None):
        return ChatCompletionChunk(
            **_COMMUN, choices=[Choice(index=0, delta=delta or ChoiceDelta(), finish_reason=fin)]
        )

    morceaux = []
    if rep.texte:
        milieu = max(1, len(rep.texte) // 2)
        for partie in (rep.texte[:milieu], rep.texte[milieu:]):
            if partie:
                morceaux.append(morceau(ChoiceDelta(content=partie)))
    for i, (nom, arguments, ident) in enumerate(rep.appels):
        morceaux.append(
            morceau(
                ChoiceDelta(
                    tool_calls=[
                        ChoiceDeltaToolCall(
                            index=i,
                            id=ident,
                            type="function",
                            function=ChoiceDeltaToolCallFunction(name=nom, arguments=arguments),
                        )
                    ]
                )
            )
        )
    if not morceaux:
        morceaux.append(morceau(ChoiceDelta(content=None)))
    morceaux.append(morceau(fin="tool_calls" if rep.appels else "stop"))
    morceaux.append(
        ChatCompletionChunk(
            **_COMMUN,
            choices=[],
            usage={"prompt_tokens": 100, "completion_tokens": rep.jetons, "total_tokens": 100 + rep.jetons},
        )
    )
    return morceaux


def _completion_chat(rep: Rep) -> ChatCompletion:
    message: dict = {"role": "assistant", "content": rep.texte}
    if rep.appels:
        message["tool_calls"] = [
            {"id": ident, "type": "function", "function": {"name": nom, "arguments": arguments}}
            for nom, arguments, ident in rep.appels
        ]
    return ChatCompletion.model_validate(
        {
            "id": "r", "created": 0, "model": "m", "object": "chat.completion",
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "tool_calls" if rep.appels else "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": rep.jetons, "total_tokens": 100 + rep.jetons},
        }
    )


class FauxServeurChat:
    """Le pendant de ``FauxServeurResponses`` pour chat completions : un client dont
    ``chat.completions.create`` rend le flux ou la réponse suivante."""

    def __init__(self, reponses):
        self._reponses = list(reponses)
        self.vus: list[dict] = []

        async def create(**params):
            self.vus.append({k: v for k, v in params.items() if k != "extra_headers"})
            rep = self._reponses.pop(0)
            if rep.attente:
                await asyncio.sleep(rep.attente)
            if params.get("stream"):
                return _FluxChat(_morceaux_chat(rep))
            return _completion_chat(rep)

        self.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def _service(api: str, reponses, **reglages):
    """Le service que la fabrique construit pour cet écran, branché sur le faux fournisseur."""
    service = create_llm_service(_config(api, **reglages))
    faux = FauxServeurResponses(reponses) if api == "responses" else FauxServeurChat(reponses)
    service._client = faux.client
    return service, faux


def _entrees(api: str, requete: dict) -> list:
    """La conversation d'une requête : ``input`` en Responses, ``messages`` en chat completions."""
    return requete["input"] if api == "responses" else requete["messages"]


async def _jouer(service, contexte=None, apres=(), delai=0.4) -> tuple[str, list]:
    descendant, _ = await run_test(
        service,
        frames_to_send=[LLMContextFrame(contexte or _contexte()), SleepFrame(sleep=delai), *apres],
        start_timeout=DEMARRAGE_S,
    )
    return "".join(f.text for f in descendant if isinstance(f, LLMTextFrame)), list(descendant)


# --- 1. La construction, depuis les réglages de l'écran ---------------------------------------


def _parametres(api=None, **reglages) -> dict:
    service = create_llm_service(_config(api, **reglages))
    invocation = service.get_llm_adapter().get_llm_invocation_params(_contexte())
    return service.build_chat_completion_params(invocation)


def test_responses_construit_le_service_responses_avec_les_reglages_de_l_ecran():
    service = create_llm_service(
        _config(
            "responses",
            temperature=0.4,
            top_p=0.9,
            max_tokens=300,
            reasoning_effort="low",
            prompt_cache=True,
        ),
        prompt_cache_key="mark-wf-46",
    )
    assert isinstance(service, MarkOpenAIResponsesLLMService)
    assert str(service._client.base_url).startswith(SCALEWAY)
    p = _parametres(
        "responses", temperature=0.4, top_p=0.9, max_tokens=300, reasoning_effort="low"
    )
    assert p["model"] == MODELE
    assert (p["stream"], p["store"]) == (True, False)
    assert (p["temperature"], p["top_p"], p["max_output_tokens"]) == (0.4, 0.9, 300)
    assert p["reasoning"] == {"effort": "low"}
    # Les outils de l'écran ont la forme d'un outil Responses (« type », « name » à plat).
    assert p["tools"][0]["type"] == "function" and p["tools"][0]["name"] == "meteo_du_jour"
    # La conversation est dans « input », jamais dans « messages ».
    assert "messages" not in p and p["input"][-1]["content"].startswith("Quelle")


def test_la_cle_de_cache_part_si_l_ecran_la_demande():
    service = create_llm_service(_config("responses", prompt_cache=True), prompt_cache_key="mark-wf-46")
    invocation = service.get_llm_adapter().get_llm_invocation_params(_contexte())
    assert service.build_chat_completion_params(invocation)["prompt_cache_key"] == "mark-wf-46"
    sans = create_llm_service(_config("responses"), prompt_cache_key="mark-wf-46")
    assert "prompt_cache_key" not in sans.build_chat_completion_params(invocation)


def test_responses_rien_regle_la_requete_ne_porte_que_le_necessaire():
    p = _parametres("responses")
    assert p["temperature"] == 0.1
    for cle in ("reasoning", "include", "top_p", "max_output_tokens", "prompt_cache_key", "extra_body"):
        assert cle not in p, cle


def test_include_est_refuse_par_scaleway_donc_jamais_envoye_hors_d_openai():
    # Pipecat l'ajoute dès qu'un raisonnement est réglé ; Scaleway répond 400 (constaté le 17/10).
    assert "include" not in _parametres("responses", reasoning_effort="low")
    chez_openai = SimpleNamespace(
        llm=OpenAIConfig(api_key=CLE, model="gpt-5-mini", reasoning_effort="low", api="responses")
    )
    service = create_llm_service(chez_openai)
    invocation = service.get_llm_adapter().get_llm_invocation_params(_contexte())
    assert service.build_chat_completion_params(invocation)["include"] == [
        "reasoning.encrypted_content"
    ]


def test_graine_et_penalites_partent_dans_extra_body_seulement_si_reglees():
    p = _parametres("responses", seed=7, frequency_penalty=0.2, presence_penalty=0.1)
    assert p["extra_body"] == {"seed": 7, "frequency_penalty": 0.2, "presence_penalty": 0.1}
    for cle in ("seed", "frequency_penalty", "presence_penalty"):
        assert cle not in p, "pas de mot-clé que le client refuserait"


def test_chat_completions_est_inchange_a_l_octet():
    # L'API par défaut, nommée ou non : le même service, la même requête qu'avant le champ.
    reglages = dict(temperature=0.3, reasoning_effort="low", prompt_cache=True, seed=5)
    nommee = create_llm_service(_config("chat_completions", **reglages), prompt_cache_key="k")
    absente = create_llm_service(_config(None, **reglages), prompt_cache_key="k")
    assert type(nommee) is DograhOpenAILLMService and type(absente) is DograhOpenAILLMService
    contexte = {"messages": [{"role": "user", "content": "bonjour"}], "tools": [], "tool_choice": None}
    attendu = absente.build_chat_completion_params(contexte)
    assert nommee.build_chat_completion_params(contexte) == attendu
    assert attendu["temperature"] == 0.3 and attendu["reasoning_effort"] == "low"
    assert attendu["seed"] == 5 and attendu["prompt_cache_key"] == "k"
    assert "reasoning" not in attendu and "input" not in attendu
    assert OpenAIConfig(api_key=CLE).api == "chat_completions", "le défaut"


def test_le_champ_api_est_a_l_ecran_choix_ferme_libelle_en_deux_langues():
    schema = OpenAIConfig.model_json_schema()["properties"]["api"]
    assert schema["enum"] == ["chat_completions", "responses"] and schema["default"] == "chat_completions"
    assert schema["mark_groupe"] == "technique"
    assert schema["mark_libelle"] == {"en": "API", "fr": "Type d'API"}
    assert MODELE in OpenAIConfig.model_json_schema()["properties"]["model"]["examples"]


def test_l_estampille_dit_l_api_quand_ce_n_est_pas_l_usuelle():
    assert stamp_sampling_settings({}, _config("responses").llm)["llm_sampling"]["api"] == "responses"
    assert "api" not in stamp_sampling_settings({}, _config("chat_completions", temperature=0.3).llm)["llm_sampling"]
    # Chat completions par défaut : l'estampille d'avant, sans le moindre mot de plus.
    assert stamp_sampling_settings({}, _config("chat_completions").llm) == {
        "llm_sampling": {"temperature": 0.1}
    }


def test_le_service_responses_porte_les_couches_mark():
    service = create_llm_service(_config("responses"))
    assert isinstance(service, (TraceModeleMixin, DelaiModeleMixin, ReflexionDeRelanceMixin))
    assert service.mark_api == "responses"
    # Les noms que la fiche, la trace et le greffier enveloppent ou lisent.
    for nom in ("get_chat_completions", "build_chat_completion_params", "_process_context",
                "_push_llm_text", "_run_or_defer_function_calls", "run_function_calls",
                "_function_is_node_transition"):
        assert hasattr(service, nom), nom


# --- 2. Les couches .mark, dans les deux API --------------------------------------------------


@pytest.mark.parametrize("api", DEUX_API)
async def test_main_passee_un_agent_muet_ne_demande_rien_puis_reparle(api):
    service, faux = _service(api, [Rep(texte="Bonjour.")])
    muter(service)
    texte, _ = await _jouer(service)
    assert texte == "" and faux.vus == [], "aucune requête ne part"
    rendre_la_parole(service)
    texte, _ = await _jouer(service)
    assert texte == "Bonjour." and len(faux.vus) == 1


@pytest.mark.parametrize("api", DEUX_API)
async def test_main_passee_une_requete_finie_par_l_assistant_recoit_la_note(api):
    service, faux = _service(api, [Rep(texte="Oui.")])
    contexte = _contexte(
        {"role": "user", "content": "Bonjour"},
        {"role": "assistant", "content": "Je vous passe un collègue."},
    )
    await _jouer(service, contexte)
    dernier = _entrees(api, faux.vus[0])[-1]
    assert dernier == {"role": "user", "content": NOTE_DE_PASSATION}
    # Le contexte lui-même n'a pas bougé : la note n'est que dans la requête.
    assert contexte.messages[-1]["role"] == "assistant"


@pytest.mark.parametrize("api", DEUX_API)
async def test_texte_du_cerveau_un_appel_ecrit_en_texte_devient_un_vrai_appel(api):
    ecrit = 'Je regarde. [TOOL_CALLS][{"name": "meteo_du_jour", "arguments": {"ville": "Beauvais"}}]'
    service, faux = _service(api, [Rep(texte=ecrit)])
    recus = []

    async def meteo(params: FunctionCallParams):
        recus.append(params.arguments)
        await params.result_callback({"ciel": "nuageux"})

    service.register_function("meteo_du_jour", meteo)
    texte, _ = await _jouer(service)
    assert recus == [{"ville": "Beauvais"}], "l'outil est appelé, pas lu à voix haute"
    assert "TOOL_CALLS" not in texte and texte.strip() == "Je regarde."


@pytest.mark.parametrize("api", DEUX_API)
async def test_texte_du_cerveau_un_texte_entre_crochets_n_est_jamais_dit(api):
    service, _ = _service(api, [Rep(texte="Bonjour [sourire] Madame, je vous écoute.")])
    texte, _ = await _jouer(service)
    assert "[" not in texte and texte.replace("  ", " ") == "Bonjour Madame, je vous écoute."


@pytest.mark.parametrize("api", DEUX_API)
async def test_reprise_sans_flux_un_flux_avale_est_relance_une_fois_sans_flux(api):
    # Le fournisseur compte des jetons mais le flux est vide ; la relance, sans flux, répond.
    service, faux = _service(api, [Rep(jetons=10), Rep(texte="Bonjour, je vous écoute.")])
    texte, _ = await _jouer(service)
    assert texte == "Bonjour, je vous écoute."
    assert len(faux.vus) == 2
    assert faux.vus[0]["stream"] is True and faux.vus[1]["stream"] is False
    assert _entrees(api, faux.vus[0]) == _entrees(api, faux.vus[1]), "la même conversation"


@pytest.mark.parametrize("api", DEUX_API)
async def test_reprise_sans_flux_relance_vide_le_code_dit_la_phrase_de_repli(api):
    service, faux = _service(api, [Rep(jetons=10), Rep(jetons=10)])
    texte, _ = await _jouer(service)
    assert texte == "Pardon, je n'ai pas bien saisi. Vous pouvez répéter ?"
    assert len(faux.vus) == 2


@pytest.mark.parametrize("api", DEUX_API)
async def test_garde_du_delai_une_reponse_trop_lente_leve_l_evenement(api):
    service, _ = _service(api, [Rep(texte="Bonjour.", attente=0.6)])
    service.mark_delai_modele_s = 0.1
    vus = []

    @service.event_handler("on_delai_modele_depasse")
    async def _depasse(_service, depassement):
        vus.append(depassement.moment)

    texte, _ = await _jouer(service, delai=1.0)
    assert vus == ["premier_morceau"] and texte == ""


@pytest.mark.parametrize("api", DEUX_API)
async def test_trace_la_requete_et_le_flux_sont_notes_sans_cle(api):
    service, faux = _service(api, [Rep(texte="Bonjour, je vous écoute.")])
    fiche: dict = {}
    trace = brancher_la_trace(SimpleNamespace(_gathered_context=fiche), service, {CLE_TRACE_REQUETES: True})
    assert trace is not None
    texte, _ = await _jouer(service)
    [entree] = fiche[TRACE_REQUETES]
    assert entree["fin"] == FIN_COMPLETE
    assert "".join(m.get("texte", "") for m in entree["morceaux"]) == texte == "Bonjour, je vous écoute."
    assert entree["usage"] is not None
    assert "input" in entree["parametres"] or "messages" in entree["parametres"]
    assert CLE not in json.dumps(entree)


@pytest.mark.parametrize("api", DEUX_API)
async def test_reflexion_de_secours_la_prochaine_reponse_seule_part_avec(api):
    service, faux = _service(
        api, [Rep(texte="Une."), Rep(texte="Deux.")], reasoning_effort="medium"
    )
    service.mark_reflexion_de_relance = "low"
    service.armer_la_relance()

    def effort(requete):
        return (requete.get("reasoning") or {}).get("effort") if api == "responses" else requete.get("reasoning_effort")

    await _jouer(service)
    await _jouer(service)
    assert [effort(r) for r in faux.vus] == ["low", "medium"], "le réglage normal revient ensuite"


async def test_le_raisonnement_regle_part_dans_la_requete_reelle():
    service, faux = _service("responses", [Rep(texte="Oui.")], reasoning_effort="low")
    await _jouer(service)
    assert faux.vus[0]["reasoning"] == {"effort": "low"} and "include" not in faux.vus[0]
    assert faux.vus[0]["model"] == MODELE and faux.vus[0]["tools"][0]["name"] == "meteo_du_jour"


class _Dit(FrameProcessor):
    """Tout ce qui part à la voix, relevé entre le service et l'agrégateur."""

    def __init__(self):
        super().__init__()
        self.texte = ""

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMTextFrame):
            self.texte += frame.text
        await self.push_frame(frame, direction)


# --- 3. Un outil de bout en bout, sur la réponse réelle de Scaleway (R1) -----------------------


async def test_un_outil_est_appele_son_resultat_relance_et_la_phrase_finale_dite():
    """Les trois réponses enregistrées le 17/10 chez Scaleway (gpt-oss-120b) : l'outil est
    appelé avec ses arguments, son résultat repart au modèle, la phrase finale est dite."""
    reponses = [FIXTURE["avec_outil"]["reponse"], FIXTURE["resultat_relance"]["reponse"]]
    service, faux = _service("responses", reponses)
    recus = []

    async def meteo(params: FunctionCallParams):
        recus.append((params.tool_call_id, params.arguments))
        await params.result_callback({"ciel": "nuageux", "temperature": 12})

    service.register_function("meteo_du_jour", meteo)
    contexte = _contexte()
    pair = LLMContextAggregatorPair(contexte)
    voix = _Dit()
    await run_test(
        Pipeline([service, voix, pair.assistant()]),
        frames_to_send=[LLMContextFrame(contexte), SleepFrame(sleep=0.8)],
        start_timeout=DEMARRAGE_S,
    )
    appel = "call_bb1882dc62456522"
    assert recus == [(appel, {"ville": "Beauvais"})]
    assert len(faux.vus) == 2
    premiere, relance = faux.vus
    assert premiere["stream"] is True and premiere["tools"][0]["name"] == "meteo_du_jour"
    entrees = relance["input"]
    assert {"type": "function_call", "call_id": appel, "name": "meteo_du_jour",
            "arguments": '{\n  "ville": "Beauvais"\n}'} in entrees or any(
        e.get("type") == "function_call" and e.get("call_id") == appel for e in entrees
    )
    sorties = [e for e in entrees if e.get("type") == "function_call_output"]
    assert [s["call_id"] for s in sorties] == [appel]
    assert json.loads(sorties[0]["output"]) == {"ciel": "nuageux", "temperature": 12}
    assert voix.texte == FIXTURE["resultat_relance"]["reponse"]["output"][0]["content"][0]["text"]
    assert voix.texte.startswith("À Beauvais, le ciel est nuageux")


# --- 4. Un passage de nœud attend la fin de la voix --------------------------------------------


class _Spy(FrameProcessor):
    def __init__(self, ordre):
        super().__init__()
        self._ordre = ordre

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMFullResponseEndFrame):
            self._ordre.append("réponse finie")
        elif isinstance(frame, FunctionCallsStartedFrame):
            self._ordre.append("appels lancés")
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._ordre.append("voix finie")
        await self.push_frame(frame, direction)


@pytest.mark.parametrize(
    "texte, attendu",
    [
        ("Je vous passe quelqu'un.", ["réponse finie", "appels lancés", "voix finie"]),
        (None, ["appels lancés", "réponse finie", "voix finie"]),
    ],
)
async def test_un_appel_de_passage_attend_la_fin_de_la_voix_quand_la_reponse_a_parle(texte, attendu):
    service, faux = _service("responses", [Rep(texte=texte, appels=[("passer", "{}", "call_p")])])
    ordre: list[str] = []

    async def passer(params: FunctionCallParams):
        await params.result_callback({"statut": "ok"})

    service.register_function("passer", passer, is_node_transition=True)
    await run_test(
        Pipeline([service, _Spy(ordre)]),
        frames_to_send=[
            LLMContextFrame(_contexte(outil=False)),
            SleepFrame(sleep=0.4),
            BotStoppedSpeakingFrame(),
            SleepFrame(sleep=0.2),
        ],
        start_timeout=DEMARRAGE_S,
    )
    assert ordre == attendu


# --- 5. La fiche et le greffier -----------------------------------------------------------------


async def test_l_etat_de_la_fiche_entre_dans_input_comme_dans_messages():
    service, faux = _service("responses", [Rep(texte="Bien.")])
    fiche = {"nom": "Dupont"}
    assert montrer_la_fiche(service, _reglages_de_fiche(), lambda: fiche) is True
    contexte = _contexte(
        {"role": "user", "content": "Bonjour"},
        {"role": "assistant", "content": "Je vous écoute."},
        {"role": "user", "content": "Je m'appelle Dupont."},
    )
    await _jouer(service, contexte)
    entrees = faux.vus[0]["input"]
    assert entrees[-1]["content"] == "Je m'appelle Dupont.", "la parole de l'appelant reste la dernière"
    assert entrees[-2]["role"] == "user" and entrees[-2]["content"].startswith(ENTETE_ETAT)
    assert [m["content"] for m in contexte.messages].count(entrees[-2]["content"]) == 0


async def test_le_greffier_en_api_responses_rend_son_texte_et_ses_jetons():
    service, faux = _service("responses", [Rep(texte='{"nom": "Dupont"}')])
    texte, jetons = await module_greffier.interroger(service, "Tu es le greffier.", "Voici la conversation.")
    assert json.loads(texte) == {"nom": "Dupont"}
    assert jetons == {"jetons_entree": 100, "jetons_sortie": 20}
    requete = faux.vus[0]
    assert requete["stream"] is False
    assert requete["text"] == {"format": {"type": "json_object"}}
    assert requete["instructions"] == "Tu es le greffier."
    assert "messages" not in requete
