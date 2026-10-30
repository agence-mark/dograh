"""[.mark] agent-facon-tala (C1), règle « code agnostique de la brique » : le nettoyage du texte du cerveau (appel écrit en
texte, crochets, nom d'outil écrit) vaut pour TOUT cerveau de conversation de la fabrique, pas seulement la classe OpenAI.

Constat du banc local (groupe 64-70, Mistral Small 4) : la case `reconnaitre_un_outil_ecrit` n'avait aucun effet, parce que
``TexteDuCerveauMixin`` n'était posé que sur ``DograhOpenAILLMService`` ; ``DograhMistralLLMService`` ne l'avait pas (le
« [TOOL_CALLS] » préexistant non plus).

| Test | Ce qu'il prouve |
|---|---|
| inventaire | chaque classe de service que ``create_llm_service_from_provider`` construit est couverte (mixin de classe ou ``couvrir_le_cerveau``) ou figure dans les exceptions avec sa raison ; échoue sur une classe nouvelle non couverte |
| exceptions | la liste des exceptions ne garde que des classes qui existent et qui ne sont pas couvrables |
| Mistral réel | le service construit par la fabrique pour `provider: mistral` : nom d'outil nu → appel, jamais dit ; case éteinte → à l'octet ; « [TOOL_CALLS] » → vrai appel |
| autres familles | un service OpenAI-compatible sans mixin de classe reçoit le même nettoyage, une fois |
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk, Choice, ChoiceDelta

from api.services.pipecat import service_factory
from api.services.pipecat.texte_du_cerveau import (
    ATTRIBUT_OUTIL_ECRIT,
    couvrir_le_cerveau,
    est_couvert,
)

FABRIQUE = Path(service_factory.__file__)

# Les services que la fabrique construit et dont le flux n'a pas la forme d'un flux de chat completions : ils n'ont pas de
# ``get_chat_completions`` à nettoyer. Chacun avec sa raison ; tout autre service doit être couvert.
EXCEPTIONS = {
    "DograhGoogleLLMService": "Gemini : flux ``generate_content_stream`` du SDK Google (parties de contenu), pas de chunks chat completions",
    "DograhGoogleVertexLLMService": "idem Gemini, par Vertex",
    "AWSBedrockLLMService": "Bedrock : flux ``converse_stream`` (événements Bedrock), pas de chunks chat completions",
}
REALTIME = re.compile(r"Realtime|Live|NovaSonic")  # parole à parole : ni texte de cerveau ni flux de conversation à nettoyer

COMMUN = {"id": "c", "created": 0, "model": "m", "object": "chat.completion.chunk"}
OUTILS = ["fin", "retour"]


def _classes_construites() -> list[str]:
    source = FABRIQUE.read_text(encoding="utf-8")
    debut = source.index("def create_llm_service_from_provider(")
    fin = source.index("\ndef ", debut + 10)
    noms = re.findall(r"return\s+(\w*LLMService)\(", source[debut:fin])
    return sorted(set(noms))


def _classe(nom: str):
    if hasattr(service_factory, nom):
        return getattr(service_factory, nom)
    return None


def test_inventaire_chaque_cerveau_de_conversation_de_la_fabrique_est_couvert():
    noms = [n for n in _classes_construites() if not REALTIME.search(n)]
    assert len(noms) >= 8, noms  # l'inventaire lit bien la fabrique
    non_couverts = []
    for nom in noms:
        classe = _classe(nom)
        if classe is None:
            if nom not in EXCEPTIONS:
                non_couverts.append(f"{nom} (classe introuvable dans la fabrique)")
            continue
        if nom in EXCEPTIONS:
            continue
        couvrable = hasattr(classe, "get_chat_completions")
        deja = any(c.__name__ in ("TexteDuCerveauMixin", "TexteDuCerveauResponsesMixin") for c in classe.__mro__)
        if not (deja or couvrable):
            non_couverts.append(nom)
    assert not non_couverts, (
        f"cerveaux de conversation sans nettoyage du texte : {non_couverts}. Poser le mixin, ou écrire l'exception avec sa "
        "raison dans EXCEPTIONS."
    )


def test_exceptions_seulement_des_classes_construites_et_non_couvrables():
    construites = set(_classes_construites())
    for nom, raison in EXCEPTIONS.items():
        assert nom in construites, f"{nom} n'est plus construit par la fabrique : retirer l'exception"
        assert raison
        classe = _classe(nom)
        if classe is not None:
            assert not hasattr(classe, "get_chat_completions"), f"{nom} peut être couvert : retirer l'exception"


def test_les_classes_openai_mistral_et_responses_ont_le_mixin_de_classe():
    from api.services.pipecat.responses_llm import MarkOpenAIResponsesLLMService

    for classe in (service_factory.DograhOpenAILLMService, service_factory.DograhMistralLLMService, MarkOpenAIResponsesLLMService):
        assert any(c.__name__.startswith("TexteDuCerveau") for c in classe.__mro__), classe


def _m(texte=None, fin=None):
    return ChatCompletionChunk(**COMMUN, choices=[Choice(index=0, delta=ChoiceDelta(content=texte), finish_reason=fin)])


class _Flux:
    def __init__(self, morceaux):
        self._morceaux = morceaux

    def __aiter__(self):
        async def gen():
            for m in self._morceaux:
                yield m

        return gen()


def _contexte():
    outil = lambda nom: SimpleNamespace(name=nom)  # noqa: E731
    return SimpleNamespace(tools=SimpleNamespace(standard_tools=[outil(n) for n in OUTILS]), messages=[])


def _dit(sorties):
    return "".join((m.choices[0].delta.content or "") for m in sorties if m.choices)


def _appels(sorties):
    return [a for m in sorties if m.choices for a in (m.choices[0].delta.tool_calls or [])]


def _mistral_reel():
    """Le service que la fabrique construit pour un agent `provider: mistral`."""
    config = SimpleNamespace(
        llm=SimpleNamespace(provider="mistral", model="mistral-small-latest", api_key="cle-de-test", base_url=None)
    )
    llm = service_factory.create_llm_service(config, prompt_cache_key="mark-wf-1")
    assert isinstance(llm, service_factory.DograhMistralLLMService)
    return llm


async def _lire(llm, morceaux, monkeypatch):
    """Le flux simulé arrive là où le client OpenAI le rendrait : sous la classe du fournisseur, sur la vraie route."""

    async def flux_du_fournisseur(self, context):
        return _Flux(morceaux)

    monkeypatch.setattr(service_factory.MistralLLMService, "get_chat_completions", flux_du_fournisseur)
    return [m async for m in await llm.get_chat_completions(_contexte())]


@pytest.mark.asyncio
async def test_mistral_reel_case_allumee_le_nom_d_outil_nu_devient_l_appel_jamais_dit(monkeypatch):
    llm = _mistral_reel()
    assert est_couvert(llm)
    setattr(llm, ATTRIBUT_OUTIL_ECRIT, True)
    for ecrit in ("fin", "_fin_", "*retour*"):
        sorties = await _lire(llm, [_m(ecrit), _m(fin="stop")], monkeypatch)
        assert _dit(sorties) == ""  # jamais dit, donc jamais dans l'historique
        [appel] = _appels(sorties)
        assert appel.function.name in OUTILS
        assert [m.choices[0].finish_reason for m in sorties if m.choices][-1] == "tool_calls"


@pytest.mark.asyncio
async def test_mistral_reel_case_eteinte_le_flux_est_rendu_a_l_octet(monkeypatch):
    llm = _mistral_reel()
    for ecrit in ("fin", "_retour_"):
        morceaux = [_m(ecrit), _m(fin="stop")]
        sorties = await _lire(llm, morceaux, monkeypatch)
        assert sorties == morceaux and not _appels(sorties)


@pytest.mark.asyncio
async def test_mistral_reel_le_jeton_d_appel_ecrit_devient_un_vrai_appel(monkeypatch):
    llm = _mistral_reel()
    sorties = await _lire(llm, [_m("[TOOL_CALLS]"), _m("fin"), _m(fin="stop")], monkeypatch)
    assert [a.function.name for a in _appels(sorties)] == ["fin"] and _dit(sorties) == ""


@pytest.mark.asyncio
async def test_un_service_compatible_sans_mixin_de_classe_recoit_le_meme_nettoyage_une_seule_fois():
    class _Autre:  # n'importe quelle famille qui rend des chunks chat completions
        _settings = SimpleNamespace(system_instruction="")

        async def get_chat_completions(self, context):
            return _Flux([_m("_retour_"), _m(fin="stop")])

    llm = _Autre()
    assert not est_couvert(llm)
    assert couvrir_le_cerveau(llm) is llm and est_couvert(llm)
    premiere = llm.get_chat_completions
    couvrir_le_cerveau(llm)
    assert llm.get_chat_completions is premiere  # idempotent
    setattr(llm, ATTRIBUT_OUTIL_ECRIT, True)
    sorties = [m async for m in await llm.get_chat_completions(_contexte())]
    assert _dit(sorties) == "" and [a.function.name for a in _appels(sorties)] == ["retour"]
    # Un service sans requête de conversation en flux n'est pas touché.
    sans = SimpleNamespace()
    assert couvrir_le_cerveau(sans) is sans and not est_couvert(sans)
