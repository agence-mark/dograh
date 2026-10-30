"""[.mark] agent-facon-tala, lot 4 (C5) : une seule relance de silence par silence.

Casques 2447, 2449, 2468 : « Êtes-vous toujours là ? » dit deux fois de suite, avec ``user_idle_max_prompts`` à 1.
La cause exacte n'a pas pu être retrouvée sur les traces (elles sont en production) : le moniteur de l'appel, qui
décide seul de toute relance, tient maintenant l'invariant lui-même. Une seconde relance qui arrive moins d'une
demi-attente après la précédente, sans que l'appelant ait parlé, est écartée ; la vraie seconde relance, qui part
après une attente entière, passe toujours.

| Test | Ce qu'il prouve |
|---|---|
| doublon | la seconde relance du même silence est écartée et le silence reste surveillé |
| vraie seconde | après une attente entière, la seconde relance part (puis l'au revoir comme avant) |
| parole | si l'appelant parle entre deux relances, la suivante part |
| route | un vrai silence : une minuterie, une relance, l'attente suivante |
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.pipecat.call_monitor_processor import CallMonitorProcessor


def _moniteur(delai=10.0):
    relances = AsyncMock()
    moniteur = CallMonitorProcessor(
        response_source=lambda: None,
        on_response_timeout=lambda _s: None,
        on_user_idle=relances,
        conversation_enabled=lambda: True,
    )
    moniteur.user_idle_timeout = delai
    moniteur.user_aggregator = SimpleNamespace(
        user_turn_controller=SimpleNamespace(has_active_user_turn=False)
    )
    moniteur._active = True
    moniteur._waiting_for_user = True
    return moniteur, relances


async def _expirer(moniteur):
    moniteur._arm_idle()
    moniteur._idle_expired(moniteur._revision)
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_la_seconde_relance_du_meme_silence_est_ecartee_et_le_silence_reste_surveille():
    moniteur, relances = _moniteur()
    await _expirer(moniteur)
    assert [c.args for c in relances.await_args_list] == [(1,)]
    # Le même silence réveille le moniteur une seconde fois, aussitôt : écartée.
    moniteur._waiting_for_user = True
    await _expirer(moniteur)
    assert relances.await_count == 1
    assert moniteur._retry_count == 1  # elle ne compte pas non plus
    assert moniteur._deadline_kind == "idle"  # le silence est toujours surveillé
    moniteur._cancel_deadline()


@pytest.mark.asyncio
async def test_apres_une_attente_entiere_la_seconde_relance_part():
    moniteur, relances = _moniteur()
    await _expirer(moniteur)
    moniteur._derniere_relance_a -= 11.5  # l'attente entière (10 s) et la phrase se sont écoulées
    moniteur._waiting_for_user = True
    await _expirer(moniteur)
    assert [c.args for c in relances.await_args_list] == [(1,), (2,)]
    moniteur._cancel_deadline()


@pytest.mark.asyncio
async def test_si_l_appelant_parle_entre_deux_relances_la_suivante_part():
    moniteur, relances = _moniteur()
    await _expirer(moniteur)
    moniteur._user_started()  # l'appelant dit un mot : un autre silence commence
    moniteur._user_turn_active = False
    moniteur._waiting_for_user = True
    await _expirer(moniteur)
    # Il avait parlé : le compte repart (1), la relance part.
    assert [c.args for c in relances.await_args_list] == [(1,), (1,)]
    moniteur._cancel_deadline()


@pytest.mark.asyncio
async def test_un_vrai_silence_arme_une_minuterie_une_relance_puis_l_attente_suivante():
    moniteur, relances = _moniteur(delai=0.05)
    moniteur._arm_idle()
    await asyncio.sleep(0.2)
    assert [c.args for c in relances.await_args_list] == [(1,)]
    # Rien n'a parlé ni bougé : le moniteur n'a rien réarmé de lui-même après la relance (la voix le fait en
    # finissant sa phrase) ; la seconde ne part donc pas toute seule.
    await asyncio.sleep(0.2)
    assert relances.await_count == 1
    moniteur._cancel_deadline()
