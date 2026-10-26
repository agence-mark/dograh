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
| requête refusée à l'ouverture du flux (fiabilite-de-la-conversation, runs 2019 et 2026) | même relance sans flux, puis la phrase de repli ; l'appelant n'attend pas : l'erreur remonte ; le délai de garde passe tel quel |
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
    def __init__(self, morceaux, reprise=None, erreur=None, refus=None):
        self._morceaux = morceaux
        self._refus = refus
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
        if self._refus is not None:
            raise self._refus
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

    from api.services.pipecat.reponse_avalee import phrase_de_repli

    PHRASE_DE_REPLI = phrase_de_repli(None)

    service = _Service(FLUX_AVALE)

    async def lent(**requete):
        await asyncio.sleep(5)

    service._client.chat.completions.create = lent
    service.mark_delai_modele_s = 0.05
    contexte = _Contexte([{"role": "user", "content": "Allô ?"}])
    morceaux = [m async for m in await service.get_chat_completions(contexte)]
    assert "".join(m.choices[0].delta.content or "" for m in morceaux if m.choices) == PHRASE_DE_REPLI


async def test_deux_fois_rien_et_l_appelant_attend_le_code_dit_la_phrase_de_repli():
    from api.services.pipecat.reponse_avalee import phrase_de_repli

    PHRASE_DE_REPLI = phrase_de_repli(None)

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


# --- fiabilite-de-la-conversation (26/10) : la requête refusée dès l'ouverture du flux --------------------------
# Banc de référence, runs 2019 et 2026 : le fournisseur refuse la requête de l'agent qui parle (``APIError``, aucun
# morceau) ; ni relance ni phrase de repli, l'agent se tait (« undefined » au clavier, un silence au téléphone).


def _refus():
    import httpx
    from openai import APIError

    return APIError("refusé", httpx.Request("POST", "https://exemple.test"), body=None)


async def test_une_requete_refusee_a_l_ouverture_est_relancee_sans_flux_quand_l_appelant_attend():
    service = _Service([], reprise=_reponse(texte="Oui, je vous entends."), refus=_refus())
    contexte = _Contexte([{"role": "user", "content": "Allô ?"}])
    morceaux = [m async for m in await service.get_chat_completions(contexte)]
    assert "".join(m.choices[0].delta.content or "" for m in morceaux if m.choices) == "Oui, je vous entends."
    assert len(service.requetes) == 1 and service.requetes[0]["stream"] is False


async def test_une_requete_refusee_puis_une_relance_en_erreur_tombent_sur_la_phrase_de_repli():
    from api.services.pipecat.reponse_avalee import phrase_de_repli

    service = _Service([], erreur=RuntimeError("encore"), refus=_refus())
    contexte = _Contexte([{"role": "user", "content": "Allô ?"}])
    morceaux = [m async for m in await service.get_chat_completions(contexte)]
    assert "".join(m.choices[0].delta.content or "" for m in morceaux if m.choices) == phrase_de_repli(None)


async def test_une_requete_refusee_sans_appelant_qui_attend_remonte_l_erreur_comme_avant():
    import pytest
    from openai import APIError

    service = _Service([], erreur=RuntimeError("encore"), refus=_refus())
    with pytest.raises(APIError):
        await _lire(service)


async def test_le_delai_de_garde_depasse_a_l_ouverture_passe_tel_quel_a_la_garde():
    import pytest

    from api.services.panne.delai_modele import DelaiModeleDepasse

    service = _Service([], reprise=_reponse(texte="jamais"), refus=DelaiModeleDepasse("premier_morceau", 4.0))
    contexte = _Contexte([{"role": "user", "content": "Allô ?"}])
    with pytest.raises(DelaiModeleDepasse):
        await service.get_chat_completions(contexte)
    assert service.requetes == []


async def test_la_relance_sans_flux_garde_les_enveloppes_de_la_conversation():
    # Revue du 26/10 (R-1) : l'état de la fiche et les notices ne s'ajoutent qu'« en conversation » (une variable de
    # contexte posée le temps de ``get_chat_completions``) ; la relance, construite pendant la lecture du flux, ne les gardait pas.
    from contextvars import ContextVar

    service = _Service(FLUX_AVALE, reprise=_reponse(texte="Oui"))
    en_conversation: ContextVar[bool] = ContextVar("en_conversation_test", default=False)
    obtenir, construire = service.get_chat_completions, service.build_chat_completion_params

    async def get_chat_completions(context):
        jeton = en_conversation.set(True)
        try:
            return await obtenir(context)
        finally:
            en_conversation.reset(jeton)

    def build_chat_completion_params(params):
        params = construire(params)
        if en_conversation.get():
            params["messages"] = [*params["messages"], "état de la fiche"]
        return params

    service.get_chat_completions = get_chat_completions
    service.build_chat_completion_params = build_chat_completion_params
    contexte = _Contexte([{"role": "user", "content": "Allô ?"}])
    [m async for m in await service.get_chat_completions(contexte)]
    [requete] = service.requetes
    assert requete["messages"][-1] == "état de la fiche"
