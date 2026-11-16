"""[.mark] SA-33, défaut 1 (appel 2557, « Tester au clavier ») : une réponse du modèle coupée après un résultat d'outil
bloquait l'appel.

La cause, prouvée sur la trace de l'appel 2557 et dans le code :

- la dernière requête au cerveau (après le résultat de ``finaliser``) s'ouvre (HTTP 200) et ne rend AUCUN morceau ; la trace la
  ferme « ferme_avant_la_fin » au bout de 35 004 ms, exactement le délai du chien de garde de la réponse (35 s), qui coupe l'appel ;
  ``depassements_modele`` absent : la garde du délai du modèle (4 s) n'a jamais joué ;
- au clavier, la garde n'est jamais armée : ``garder_l_agent`` est appelé au téléphone (``run_pipeline``) et à la passation dans
  le moteur, mais le passage du clavier (``text_chat_runner.jouer_un_passage``) reconstruit l'agent qui parle à chaque tour sans
  l'appeler : un flux muet y attend sans fin ;
- et même gardé, un flux vide ou coupé APRÈS un résultat d'outil n'était ni relancé ni remplacé : « l'appelant attend » ne valait
  que si le dernier message était le sien (``reponse_avalee.l_appelant_attend``).

L'hypothèse « l'écriture du greffier annule la génération » est infirmée : la passe du greffier ne touche ni le flux ni le contexte
(``greffier.Greffier.une_passe`` écrit la fiche) ; sa réponse (21:00:50.715, la seconde « 200 » du journal) arrive pendant que le
flux du cerveau, ouvert à 21:00:45.242, ne rend toujours rien.

| Test | Ce qu'il prouve |
|---|---|
| clavier | le passage du clavier arme la garde du modèle sur l'agent qui parle, comme le téléphone |
| flux muet sans garde | la cause : il n'en sort jamais (seul le chien de garde de 35 s y met fin, en coupant l'appel) |
| flux muet gardé, après un outil | relancé une fois, puis la ``suggestion`` de l'outil est dite : jamais un silence |
| flux vide après un outil | relancé une fois (même sans jeton compté), la relance est rendue |
| relance vide après un outil | la ``suggestion`` de l'outil est dite (``texte_a_dire`` d'abord) |
| texte déjà dit par le code | le silence du modèle est la bonne réponse : rien n'est relancé ni redit |
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re

import pytest

from api.services.panne.delai_modele import DelaiModeleMixin
from api.services.pipecat.reponse_avalee import RepriseSansFluxMixin
from api.services.workflow import text_chat_runner
from api.tests.mark.test_reponse_avalee import FLUX_AVALE, _Base, _Contexte, _morceau, _reponse

SUGGESTION = "Quel est votre numéro de téléphone ?"


def _apres_l_outil(resultat: dict) -> _Contexte:
    return _Contexte(
        [
            {"role": "user", "content": "Paul."},
            {"role": "assistant", "tool_calls": [{"id": "t", "type": "function", "function": {"name": "finaliser", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "t", "content": json.dumps(resultat, ensure_ascii=False)},
        ]
    )


INCOMPLETE = {"statut": "INCOMPLETE", "faits": {}, "suggestion": SUGGESTION, "manque": "telephone"}


def _texte(morceaux) -> str:
    return "".join(m.choices[0].delta.content or "" for m in morceaux if m.choices)


# --- La garde au clavier ----------------------------------------------------------------------------------------


def test_le_passage_du_clavier_arme_la_garde_du_modele_comme_le_telephone():
    source = inspect.getsource(text_chat_runner)
    garde = re.search(r"await garder_l_agent\(\s*engine,\s*actif,", source)
    assert garde, "Le passage du clavier n'arme pas la garde du modèle sur l'agent qui parle (appel 2557)."
    trace = source.index("brancher_la_trace(\n            engine, agent.llm")
    demarrage = source.index("runner_task = asyncio.create_task(run_pipeline_worker(task))")
    assert trace < garde.start() < demarrage, "La garde s'arme sur le service de l'agent, avant que le circuit ne tourne."


# --- Le flux muet, avec et sans la garde ----------------------------------------------------------------------


class _FluxMuet:
    """Le flux de l'appel 2557 : ouvert, puis plus rien."""

    def __aiter__(self):
        async def gen():
            await asyncio.Event().wait()
            yield  # pragma: no cover

        return gen()


class _BaseMuette(_Base):
    def __init__(self):
        super().__init__([])

        async def create(**requete):
            self.requetes.append(requete)
            await asyncio.Event().wait()

        self._client.chat.completions.create = create

    async def get_chat_completions(self, context):
        return _FluxMuet()


class _ServiceGarde(RepriseSansFluxMixin, DelaiModeleMixin, _BaseMuette):
    """L'ordre du cerveau compatible OpenAI : la reprise au-dessus de la garde du délai."""

    def _call_event_handler(self, *a, **k):  # pragma: no cover -- aucun morceau n'arrive
        async def rien():
            return None

        return rien()


async def test_la_cause_un_flux_muet_sans_garde_ne_finit_jamais():
    service = _ServiceGarde()
    service.mark_delai_modele_s = None  # le clavier avant SA-33

    async def lire():
        return [m async for m in await service.get_chat_completions(_apres_l_outil(INCOMPLETE))]

    with pytest.raises((TimeoutError, asyncio.TimeoutError)):
        await asyncio.wait_for(lire(), 0.3)


async def test_un_flux_muet_garde_apres_un_outil_dit_la_suggestion_de_l_outil():
    service = _ServiceGarde()
    service.mark_delai_modele_s = 0.05
    morceaux = await asyncio.wait_for(
        _lire_tout(service, _apres_l_outil(INCOMPLETE)), 2
    )
    assert _texte(morceaux) == SUGGESTION
    assert len(service.requetes) == 1 and service.requetes[0]["stream"] is False  # relancé une fois, sans flux


async def _lire_tout(service, contexte):
    return [m async for m in await service.get_chat_completions(contexte)]


# --- Le flux vide ou coupé après un outil -----------------------------------------------------------------------


class _Service(RepriseSansFluxMixin, _Base):
    pass


async def test_un_flux_vide_apres_un_outil_qui_propose_une_phrase_est_relance():
    flux = [_morceau(), _morceau(fin="stop"), _morceau(jetons=0)]
    service = _Service(flux, reprise=_reponse(texte="Et votre numéro, s'il vous plaît ?"))
    morceaux = await _lire_tout(service, _apres_l_outil(INCOMPLETE))
    assert _texte(morceaux) == "Et votre numéro, s'il vous plaît ?"
    assert len(service.requetes) == 1


async def test_une_relance_vide_apres_un_outil_dit_le_texte_de_l_outil():
    for service in (_Service(FLUX_AVALE, reprise=_reponse()), _Service(FLUX_AVALE, erreur=RuntimeError("x"))):
        assert _texte(await _lire_tout(service, _apres_l_outil(INCOMPLETE))) == SUGGESTION
    a_dire = {**INCOMPLETE, "texte_a_dire": "Votre numéro, s'il vous plaît ?", "restitution": "mot_pour_mot"}
    service = _Service(FLUX_AVALE, reprise=_reponse())
    assert _texte(await _lire_tout(service, _apres_l_outil(a_dire))) == "Votre numéro, s'il vous plaît ?"


async def test_une_suggestion_rangee_dans_data_est_dite_aussi():
    resultat = {"status": "success", "data": {"suggestion": SUGGESTION}}
    service = _Service(FLUX_AVALE, reprise=_reponse())
    assert _texte(await _lire_tout(service, _apres_l_outil(resultat))) == SUGGESTION


async def test_un_texte_deja_dit_par_le_code_laisse_le_silence_du_modele():
    """W17 : la suggestion a déjà été dite à la voix et retirée du résultat ; le modèle a la consigne d'attendre."""
    deja = {"statut": "INCOMPLETE", "faits": {}, "deja_dit_par_le_code": True, "consigne_de_restitution": "Attends sa réponse."}
    flux = [_morceau(), _morceau(fin="stop"), _morceau(jetons=0)]
    service = _Service(flux, reprise=_reponse(texte="jamais"))
    assert await _lire_tout(service, _apres_l_outil(deja)) == flux
    assert service.requetes == []
