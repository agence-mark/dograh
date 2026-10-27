"""[.mark] Une erreur du fournisseur en cours de flux, avant toute parole (chantier actions-sures-et-parite-clavier, lot D).

Plan `Labo-agent-vocal/plans/actions-sures-et-parite-clavier/`. Run 2054 (banc de fin du 27/10), tour 8 : Scaleway répond
« 200 OK », commence un appel d'outil, puis glisse une erreur de son serveur dans le flux (« list index out of range »,
``APIError``). La relance d'hier ne partait que si RIEN d'utile n'était arrivé ; le début d'un appel d'outil comptait comme
« déjà dit ». Or rien n'avait été dit : un appel d'outil ne s'exécute qu'à la fin de la réponse. L'agent se taisait
(« undefined »). Réparation : un appel d'outil inachevé est gardé jusqu'à la fin du flux (aucune latence : il part à la fin
de toute façon) ; le flux qui casse avant toute parole suit la relance, puis la phrase de repli.

| Test | Ce qu'il prouve |
|---|---|
| run 2054 | début d'appel d'outil puis erreur : relance sans flux, seul l'appel de la relance part, entier |
| relance en échec | même cas, la relance échoue aussi : la phrase de repli est dite |
| parole déjà dite | du texte puis l'erreur : l'erreur remonte comme avant (rien n'est dit deux fois) |
| flux normal | des appels d'outil sans erreur : rendus tels quels, dans l'ordre, sans relance |
| texte puis outil | du texte puis un appel d'outil : rendus tels quels, sans relance |
"""

from __future__ import annotations

import pytest
from openai import APIError
from openai.types.chat.chat_completion_chunk import (
    ChatCompletionChunk,
    Choice,
    ChoiceDelta,
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
)

from api.services.pipecat.reponse_avalee import RepriseSansFluxMixin, phrase_de_repli
from api.tests.mark.test_reponse_avalee import COMMUN, _Base, _Contexte, _morceau, _reponse, _Service


def _debut_d_appel(nom="confier_le_travail", arguments='{"dem'):
    return ChatCompletionChunk(
        **COMMUN,
        choices=[
            Choice(
                index=0,
                delta=ChoiceDelta(
                    tool_calls=[
                        ChoiceDeltaToolCall(
                            index=0, id="x1", type="function",
                            function=ChoiceDeltaToolCallFunction(name=nom, arguments=arguments),
                        )
                    ]
                ),
            )
        ],
    )


def _erreur_du_serveur():
    import httpx

    return APIError("list index out of range", httpx.Request("POST", "https://exemple.test"), body=None)


class _FluxQuiCasse:
    def __init__(self, morceaux, erreur):
        self._morceaux, self._erreur = list(morceaux), erreur

    def __aiter__(self):
        async def gen():
            for m in self._morceaux:
                yield m
            raise self._erreur

        return gen()


class _BaseQuiCasse(_Base):
    """La base de test, dont le flux casse après ses morceaux."""

    def __init__(self, morceaux, erreur_du_flux, **k):
        super().__init__(morceaux, **k)
        self._erreur_du_flux = erreur_du_flux

    async def get_chat_completions(self, context):
        return _FluxQuiCasse(self._morceaux, self._erreur_du_flux)


class _Casse(RepriseSansFluxMixin, _BaseQuiCasse):
    pass


ATTEND = _Contexte([{"role": "user", "content": "Non non, pas jeudi ! Je veux un samedi."}])


async def _lire(service, contexte=ATTEND):
    return [m async for m in await service.get_chat_completions(contexte)]


def _appels(morceaux):
    return [a for m in morceaux if m.choices for a in (m.choices[0].delta.tool_calls or [])]


async def test_run_2054_debut_d_appel_puis_erreur_la_relance_rend_un_appel_entier():
    service = _Casse([_morceau(), _debut_d_appel()], _erreur_du_serveur(), reprise=_reponse(outil="confier_le_travail"))
    morceaux = await _lire(service)
    appels = _appels(morceaux)
    assert [(a.function.name, a.function.arguments) for a in appels] == [("confier_le_travail", "{}")]
    assert len(service.requetes) == 1 and service.requetes[0]["stream"] is False


async def test_run_2054_la_relance_echoue_aussi_la_phrase_de_repli_est_dite():
    service = _Casse([_debut_d_appel()], _erreur_du_serveur(), erreur=RuntimeError("encore"))
    morceaux = await _lire(service)
    assert not _appels(morceaux)
    assert "".join(m.choices[0].delta.content or "" for m in morceaux if m.choices) == phrase_de_repli(None)


async def test_une_parole_deja_dite_puis_l_erreur_remonte_comme_avant():
    service = _Casse([_morceau("Je regarde"), _debut_d_appel()], _erreur_du_serveur(), reprise=_reponse(texte="jamais"))
    with pytest.raises(APIError):
        await _lire(service)
    assert service.requetes == []


async def test_des_appels_d_outil_sans_erreur_passent_tels_quels_dans_l_ordre():
    flux = [_morceau(), _debut_d_appel(arguments='{"demande": '), _debut_d_appel(arguments='"x"}'), _morceau(fin="tool_calls"),
            _morceau(jetons=7)]
    service = _Service(flux, reprise=_reponse(texte="jamais"))
    assert await _lire(service) == flux
    assert service.requetes == []


async def test_du_texte_puis_un_appel_d_outil_passent_tels_quels():
    flux = [_morceau("Je regarde."), _debut_d_appel(arguments="{}"), _morceau(fin="tool_calls"), _morceau(jetons=4)]
    service = _Service(flux, reprise=_reponse(texte="jamais"))
    assert await _lire(service) == flux
    assert service.requetes == []
