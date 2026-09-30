"""[.mark] K2 : sous Flux, un seul mot ne coupe pas l'accueil (minimum de mots, E1).

Chantier correctifs-apres-figeage (30/09/2026). Run 909 : l'accueil du n° 34 (interruptible, 2 mots minimum) coupé
à 1,7 s par un seul mot transcrit, « De », au moment où l'agent disait « Nuances de Feu ». Question : le minimum
joue-t-il quand la transcription (Flux) décide des tours ? Joué sur la VRAIE stratégie de Pipecat que
`GreetingController` installe pendant l'accueil, avec les trames dans l'ordre d'un accueil sous Flux.

| Test | Ce qu'il prouve |
|---|---|
| un mot | l'agent parle, Flux propose un début de tour, un mot final : l'accueil n'est PAS coupé |
| deux mots | témoin : deux mots coupent l'accueil (le réglage fait ce qu'il annonce) |
| écho provisoire | une transcription provisoire de 3 mots coupe, même si la finale n'en garde qu'un : c'est la cause probable du 909 (l'écho de l'agent au navigateur), pas un défaut du mécanisme |

⚠️ Tient aussi une montée de Pipecat : si la stratégie changeait de nom ou de comportement, ces tests rougissent.
"""

import pytest
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    InterimTranscriptionFrame,
    ProposedUserStartedSpeakingFrame,
    TranscriptionFrame,
)
from pipecat.turns.user_start import MinWordsUserTurnStartStrategy


def _transcription(texte: str, provisoire: bool = False):
    classe = InterimTranscriptionFrame if provisoire else TranscriptionFrame
    return classe(text=texte, user_id="appelant", timestamp="0")


async def _accueil_coupe(trames) -> bool:
    """La stratégie de l'accueil (2 mots), installée comme le fait `GreetingController` : elle apprend d'abord que
    l'agent parle, puis reçoit les trames de l'appelant."""
    strategie = MinWordsUserTurnStartStrategy(min_words=2)
    debuts = []

    async def debut(*_args, **_kwargs):
        debuts.append(True)

    async def rien(*_args, **_kwargs):
        return None

    strategie.add_event_handler("on_user_turn_started", debut)
    strategie.add_event_handler("on_reset_aggregation", rien)
    await strategie.process_frame(BotStartedSpeakingFrame())
    for trame in trames:
        await strategie.process_frame(trame)
    return bool(debuts)


@pytest.mark.asyncio
async def test_un_seul_mot_ne_coupe_pas_l_accueil_sous_flux():
    assert not await _accueil_coupe([ProposedUserStartedSpeakingFrame(), _transcription("De")])


@pytest.mark.asyncio
async def test_temoin_deux_mots_coupent_l_accueil():
    assert await _accueil_coupe([ProposedUserStartedSpeakingFrame(), _transcription("Allô bonjour")])


@pytest.mark.asyncio
async def test_une_transcription_provisoire_de_trois_mots_coupe_l_accueil():
    assert await _accueil_coupe(
        [ProposedUserStartedSpeakingFrame(), _transcription("De Feu bonjour", provisoire=True), _transcription("De")]
    )
