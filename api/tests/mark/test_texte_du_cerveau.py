"""[.mark] Rejeu du 16/10 (run 1410) : ce que le cerveau écrit en texte et qui n'est pas une parole.

| Test | Ce qu'il prouve |
|---|---|
| porte écrite au format Mistral | « [TOOL_CALLS]fin » puis la phrase devient « → fin » puis la phrase (le lecteur de portes la prend) |
| outil déclaré écrit en texte | Mistral (``nom[ARGS]{…}``, liste JSON) et Qwen (``<tool_call>``) deviennent un vrai appel d'outil |
| nom inconnu sans portes dans la réponse | jeton et nom retirés, le reste dit |
| crochets | le passage entre crochets n'est jamais dit, même coupé en morceaux ; un crochet jamais fermé est rendu |
| flux ordinaire | passe tel quel, morceau par morceau |
| branchement | le cerveau compatible OpenAI porte le nettoyage, sous la trace, au-dessus de la relance |
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from openai.types.chat.chat_completion_chunk import ChatCompletionChunk, Choice, ChoiceDelta
from openai.types.completion_usage import CompletionUsage

from api.services.pipecat.texte_du_cerveau import FluxNettoye, TexteDuCerveauMixin

COMMUN = {"id": "c", "created": 0, "model": "m", "object": "chat.completion.chunk"}


def _m(texte=None, fin=None):
    return ChatCompletionChunk(**COMMUN, choices=[Choice(index=0, delta=ChoiceDelta(content=texte), finish_reason=fin)])


def _usage():
    return ChatCompletionChunk(**COMMUN, choices=[], usage=CompletionUsage(completion_tokens=9, prompt_tokens=1, total_tokens=10))


class _Flux:
    def __init__(self, morceaux):
        self._morceaux = morceaux

    def __aiter__(self):
        async def gen():
            for m in self._morceaux:
                yield m
        return gen()


async def _lire(morceaux, outils=(), portes=False):
    return [m async for m in FluxNettoye(_Flux(morceaux), outils, portes)]


def _dit(sorties):
    return "".join((m.choices[0].delta.content or "") for m in sorties if m.choices)


def _appels(sorties):
    return [a for m in sorties if m.choices for a in (m.choices[0].delta.tool_calls or [])]


async def test_une_porte_ecrite_au_format_mistral_devient_la_ligne_de_porte():
    sorties = await _lire(
        [_m(), _m("[TOOL_CALLS]"), _m("fin"), _m(), _m("Je"), _m(" vous souhaite"), _m(" une bonne soirée."), _m(fin="stop"), _usage()],
        portes=True,
    )
    assert _dit(sorties) == "→ fin\nJe vous souhaite une bonne soirée."
    assert sorties[-1].usage.completion_tokens == 9
    assert not _appels(sorties)


async def test_un_outil_declare_ecrit_au_format_mistral_devient_un_appel():
    for ecrit in (
        ["[TOOL_CALLS]", "outil_a", "[ARGS]", '{"cle": "valeur"}'],
        ['[TOOL_CALLS][{"name": "outil_a", "arguments": {"cle": "valeur"}}]'],
    ):
        sorties = await _lire(
            [_m("Un instant. "), *[_m(t) for t in ecrit], _m(fin="stop")],
            outils=["outil_a"],
            portes=True,
        )
        [appel] = _appels(sorties)
        assert appel.function.name == "outil_a"
        assert json.loads(appel.function.arguments) == {"cle": "valeur"}
        assert _dit(sorties) == "Un instant. "
        assert [m.choices[0].finish_reason for m in sorties if m.choices][-1] == "tool_calls"


async def test_un_outil_declare_ecrit_au_format_qwen_devient_un_appel():
    sorties = await _lire(
        [_m("<tool_call>"), _m('\n{"name": "outil_b", "arguments": {}}\n'), _m("</tool_call>"), _m(fin="stop")],
        outils=["outil_b"],
    )
    assert [a.function.name for a in _appels(sorties)] == ["outil_b"]
    assert _dit(sorties) == ""


async def test_un_nom_inconnu_sans_portes_dans_la_reponse_est_retire():
    sorties = await _lire([_m("[TOOL_CALLS]"), _m("fin"), _m(), _m("Au revoir."), _m(fin="stop")])
    assert _dit(sorties) == "Au revoir."


async def test_le_texte_entre_crochets_n_est_jamais_dit():
    sorties = await _lire(
        [_m("["), _m("Une"), _m(" indication"), _m(" de"), _m(" scène"), _m("]\n\n"), _m("Bonjour,"), _m(" je vous écoute."), _m(fin="stop")]
    )
    assert _dit(sorties) == "Bonjour, je vous écoute."
    assert [m.choices[0].finish_reason for m in sorties if m.choices][-1] == "stop"


async def test_un_crochet_jamais_ferme_est_rendu_tel_quel():
    sorties = await _lire([_m("Le total [environ"), _m(" douze."), _m(fin="stop")])
    assert _dit(sorties) == "Le total [environ douze."


async def test_un_flux_ordinaire_passe_tel_quel():
    flux = [_m(), _m("Bonjour,"), _m(" que puis-je faire ?"), _m(fin="stop"), _usage()]
    assert await _lire(flux) == flux


async def test_le_mixin_lit_les_outils_et_la_fleche_de_la_requete():
    class _Base:
        _settings = SimpleNamespace(system_instruction="Écris → nom_de_la_porte puis la phrase.")

        async def get_chat_completions(self, context):
            return _Flux([_m("[TOOL_CALLS]"), _m("porte_b"), _m(), _m("Une question ?"), _m(fin="stop")])

    class _Service(TexteDuCerveauMixin, _Base):
        pass

    contexte = SimpleNamespace(tools=None, messages=[])
    sorties = [m async for m in await _Service().get_chat_completions(contexte)]
    assert _dit(sorties) == "→ porte_b\nUne question ?"


def test_le_cerveau_compatible_openai_porte_le_nettoyage():
    from api.services.pipecat.main_passee import MainPasseeMixin
    from api.services.pipecat.reponse_avalee import RepriseSansFluxMixin
    from api.services.pipecat.service_factory import DograhOpenAILLMService
    from api.services.pipecat.trace_modele import TraceModeleMixin

    ordre = DograhOpenAILLMService.__mro__
    assert (
        ordre.index(TraceModeleMixin)
        < ordre.index(MainPasseeMixin)
        < ordre.index(TexteDuCerveauMixin)
        < ordre.index(RepriseSansFluxMixin)
    )


async def test_un_jeton_qwen_coupe_en_deux_n_est_jamais_dit():
    sorties = await _lire(
        [_m("Un instant. <tool"), _m("_call>"), _m('{"name": "outil_b", "arguments": {}}</tool_call>'), _m(fin="stop")],
        outils=["outil_b"],
    )
    assert [a.function.name for a in _appels(sorties)] == ["outil_b"]
    assert _dit(sorties) == "Un instant. "


async def test_un_nom_d_outil_complet_ne_se_colle_pas_a_la_suite():
    sorties = await _lire([_m("[TOOL_CALLS]"), _m("outil_a"), _m("bonne"), _m(fin="stop")], outils=["outil_a"])
    assert [a.function.name for a in _appels(sorties)] == ["outil_a"]


async def test_plusieurs_appels_en_liste_sont_tous_rendus():
    ecrit = (
        '[TOOL_CALLS][{"name": "outil_a", "arguments": {}}, '
        '{"name": "outil_b", "arguments": {"x": 1}}, {"name": "inconnu", "arguments": {}}]'
    )
    sorties = await _lire([_m(ecrit), _m(fin="stop")], outils=["outil_a", "outil_b"])
    appels = _appels(sorties)
    assert [(a.index, a.function.name) for a in appels] == [(0, "outil_a"), (1, "outil_b")]
    assert json.loads(appels[1].function.arguments) == {"x": 1}
