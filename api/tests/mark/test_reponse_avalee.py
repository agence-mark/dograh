"""[.mark] Chantier agents-specialises, après le banc du 16/10 : la réponse avalée par le fournisseur.

| Test | Ce qu'il prouve |
|---|---|
| flux vide, jetons comptés | relancé une fois sans flux ; l'appel d'outil de la relance est rendu en morceaux |
| flux normal | passe tel quel, aucune relance |
| flux vide, aucun jeton | relancé aussi (C2 : un flux vide n'est jamais une réponse) |
| relance en erreur ou vide, l'appelant attend | le code dit la phrase de repli, jamais un silence |
| relance en erreur ou vide, l'appelant n'attend pas | le flux d'origine est rendu, l'erreur ne remonte pas |
| requête de la relance | la même que l'originale (enveloppes de l'instance comprises), ``stream`` à faux |
| branchement | le cerveau compatible OpenAI porte la relance, sous la trace |
"""

from __future__ import annotations

from types import SimpleNamespace

from openai.types.chat import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk, Choice, ChoiceDelta
from openai.types.completion_usage import CompletionUsage

from api.services.pipecat.reponse_avalee import RepriseSansFluxMixin

class _Contexte(list):
    """Un contexte comme celui de Pipecat : ses messages, dans ``messages``."""

    @property
    def messages(self):
        return list(self)



COMMUN = {"id": "c", "created": 0, "model": "m", "object": "chat.completion.chunk"}


def _morceau(contenu=None, fin=None, jetons=None):
    if jetons is not None:
        return ChatCompletionChunk(
            **COMMUN, choices=[], usage=CompletionUsage(completion_tokens=jetons, prompt_tokens=5, total_tokens=5 + jetons)
        )
    return ChatCompletionChunk(**COMMUN, choices=[Choice(index=0, delta=ChoiceDelta(content=contenu), finish_reason=fin)])


FLUX_AVALE = [_morceau(), _morceau(fin="stop"), _morceau(jetons=10)]


def _reponse(outil=None, texte=None):
    message = {"role": "assistant", "content": texte}
    if outil:
        message["tool_calls"] = [
            {"id": "t1", "type": "function", "function": {"name": outil, "arguments": "{}"}}
        ]
    return ChatCompletion.model_validate(
        {
            "id": "r", "created": 0, "model": "m", "object": "chat.completion",
            "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if outil else "stop"}],
            "usage": {"completion_tokens": 10, "prompt_tokens": 5, "total_tokens": 15},
        }
    )


class _Flux:
    def __init__(self, morceaux):
        self._morceaux = list(morceaux)

    def __aiter__(self):
        async def gen():
            for m in self._morceaux:
                yield m
        return gen()


class _Base:
    def __init__(self, morceaux, reprise=None, erreur=None):
        self._morceaux = morceaux
        self.requetes = []

        async def create(**requete):
            self.requetes.append(requete)
            if erreur is not None:
                raise erreur
            return reprise

        self._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        self._settings = SimpleNamespace(system_instruction="consigne")
        self.supports_developer_role = True

    async def get_chat_completions(self, context):
        return _Flux(self._morceaux)

    def get_llm_adapter(self):
        return SimpleNamespace(get_llm_invocation_params=lambda context, **k: {"messages": context})

    def build_chat_completion_params(self, params):
        return {"model": "m", "stream": True, "stream_options": {"include_usage": True}, **params}


class _Service(RepriseSansFluxMixin, _Base):
    pass


async def _lire(service):
    return [m async for m in await service.get_chat_completions(["bonjour"])]


async def test_un_flux_avale_est_relance_sans_flux_et_l_appel_d_outil_est_rendu():
    service = _Service(FLUX_AVALE, reprise=_reponse(outil="passer_a_l_agent_informations"))
    morceaux = await _lire(service)
    appels = [a for m in morceaux if m.choices for a in (m.choices[0].delta.tool_calls or [])]
    assert [a.function.name for a in appels] == ["passer_a_l_agent_informations"]
    assert appels[0].function.arguments == "{}" and appels[0].id == "t1"
    assert [m.choices[0].finish_reason for m in morceaux if m.choices][-1] == "tool_calls"
    assert morceaux[-1].usage.completion_tokens == 20, "le flux vide (10) et la relance (10)"
    [requete] = service.requetes
    assert requete["stream"] is False and "stream_options" not in requete
    assert requete["messages"] == ["bonjour"] and requete["model"] == "m"


async def test_un_flux_normal_passe_tel_quel_sans_relance():
    flux = [_morceau(), _morceau("Bonjour"), _morceau(fin="stop"), _morceau(jetons=3)]
    service = _Service(flux, reprise=_reponse(texte="jamais"))
    assert await _lire(service) == flux
    assert service.requetes == []


async def test_un_flux_vide_sans_jeton_est_relance_quand_l_appelant_attend():
    flux = [_morceau(), _morceau(fin="stop"), _morceau(jetons=0)]
    service = _Service(flux, reprise=_reponse(texte="Oui"))
    contexte = _Contexte([{"role": "user", "content": "Allô ?"}])
    morceaux = [m async for m in await service.get_chat_completions(contexte)]
    assert "".join(m.choices[0].delta.content or "" for m in morceaux if m.choices) == "Oui"
    assert len(service.requetes) == 1


async def test_un_silence_apres_un_resultat_d_outil_sans_jeton_reste_un_silence():
    """Revue du 16/10 : sans jeton compté et sans appelant qui attend, rien n'est relancé."""
    flux = [_morceau(), _morceau(fin="stop"), _morceau(jetons=0)]
    service = _Service(flux, reprise=_reponse(texte="jamais"))
    contexte = _Contexte([{"role": "user", "content": "x"}, {"role": "tool", "content": "{}"}])
    assert [m async for m in await service.get_chat_completions(contexte)] == flux
    assert service.requetes == []


async def test_texte_et_appel_d_outil_de_la_relance_partent_en_morceaux_separes():
    """Revue du 16/10 : Pipecat lit « outil, sinon texte » et le premier appel d'un morceau."""
    reprise = ChatCompletion.model_validate(
        {
            "id": "r", "created": 0, "model": "m", "object": "chat.completion",
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": "Je vous transfère.",
                "tool_calls": [
                    {"id": "a", "type": "function", "function": {"name": "un", "arguments": "{}"}},
                    {"id": "b", "type": "function", "function": {"name": "deux", "arguments": "{}"}},
                ]}}],
            "usage": {"completion_tokens": 7, "prompt_tokens": 100, "total_tokens": 107},
        }
    )
    morceaux = await _lire(_Service(FLUX_AVALE, reprise=reprise))
    deltas = [m.choices[0].delta for m in morceaux if m.choices]
    assert deltas[0].content == "Je vous transfère." and not deltas[0].tool_calls
    assert [d.tool_calls[0].function.name for d in deltas if d.tool_calls] == ["un", "deux"]
    assert all(len(d.tool_calls) == 1 for d in deltas if d.tool_calls)
    # Les jetons du flux vide comptent aussi (10 + 7 générés).
    assert morceaux[-1].usage.completion_tokens == 17


async def test_une_relance_qui_ne_repond_pas_tombe_sur_la_phrase_de_repli_au_delai():
    import asyncio

    from api.services.pipecat.reponse_avalee import PHRASE_DE_REPLI

    service = _Service(FLUX_AVALE)

    async def lent(**requete):
        await asyncio.sleep(5)

    service._client.chat.completions.create = lent
    service.mark_delai_modele_s = 0.05
    contexte = _Contexte([{"role": "user", "content": "Allô ?"}])
    morceaux = [m async for m in await service.get_chat_completions(contexte)]
    assert "".join(m.choices[0].delta.content or "" for m in morceaux if m.choices) == PHRASE_DE_REPLI


async def test_deux_fois_rien_et_l_appelant_attend_le_code_dit_la_phrase_de_repli():
    from api.services.pipecat.reponse_avalee import PHRASE_DE_REPLI

    for service in (_Service(FLUX_AVALE, reprise=_reponse()), _Service(FLUX_AVALE, erreur=RuntimeError("x"))):
        contexte = _Contexte([{"role": "assistant", "content": "Bonjour."}, {"role": "user", "content": "Allô ?"}])
        morceaux = [m async for m in await service.get_chat_completions(contexte)]
        assert "".join(m.choices[0].delta.content or "" for m in morceaux if m.choices) == PHRASE_DE_REPLI


async def test_une_relance_vide_sans_appelant_qui_attend_rend_le_flux_d_origine():
    service = _Service(FLUX_AVALE, erreur=RuntimeError("panne"))
    assert await _lire(service) == FLUX_AVALE
    service = _Service(FLUX_AVALE, reprise=_reponse())
    assert await _lire(service) == FLUX_AVALE


async def test_la_relance_passe_par_les_enveloppes_de_l_instance():
    """Le moteur enveloppe ``build_chat_completion_params`` sur l'instance (l'état de la fiche) :
    la relance envoie la même requête que l'originale."""
    service = _Service(FLUX_AVALE, reprise=_reponse(texte="Oui"))
    construire = service.build_chat_completion_params
    service.build_chat_completion_params = lambda p: {**construire(p), "fiche": "état"}
    morceaux = await _lire(service)
    assert service.requetes[0]["fiche"] == "état"
    assert "".join(m.choices[0].delta.content or "" for m in morceaux if m.choices) == "Oui"


def test_le_cerveau_compatible_openai_porte_la_relance_sous_la_trace():
    from api.services.pipecat.service_factory import DograhOpenAILLMService
    from api.services.pipecat.trace_modele import TraceModeleMixin

    ordre = DograhOpenAILLMService.__mro__
    assert ordre.index(TraceModeleMixin) < ordre.index(RepriseSansFluxMixin)
