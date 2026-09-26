"""[.mark] Accueil non interruptible (E1 éteint) : le rappel du moteur protège toujours l'accueil.

Remise à niveau sur l'amont `4e6cb22b`, relecture indépendante du 26/09/2026. L'amont
(`7ca8d946`, titre « tts caching for MiniMax », cas R6) fait rendre `False` à
`PipecatEngine.should_mute_user` pendant TOUT l'accueil, pour laisser son contrôleur
d'accueil décider. Chez nous ce contrôleur est éteint par défaut (décision E1 d'Evan) :
sans garde, un agent dont le réglage « couper le micro pendant la première phrase » est
faux et dont le premier nœud n'est pas interruptible verrait son accueil coupé au
premier bruit, alors qu'en production (`6233a258`) le rappel du moteur le protégeait.

Joué sur la vraie méthode du moteur et le vrai contrôleur d'accueil.
"""

from types import SimpleNamespace

import pytest
from pipecat.frames.frames import BotStartedSpeakingFrame

from api.services.pipecat.greeting import GreetingController
from api.services.workflow.pipecat_engine import PipecatEngine


def _moteur_pendant_l_accueil(*, interruptible: bool) -> PipecatEngine:
    moteur = PipecatEngine.__new__(PipecatEngine)
    moteur._bot_is_speaking = False
    moteur._mute_pipeline = False
    moteur.answer_supervisor = None
    moteur.speech_playback = SimpleNamespace(mutes_user=False, greeting_pending=True)
    accueil = GreetingController.__new__(GreetingController)
    accueil._playback = SimpleNamespace(greeting=None)
    accueil._turn_text = None
    accueil.regler(interruptible=interruptible, mots_minimum=2)
    moteur.greeting = accueil
    moteur._active_agent = SimpleNamespace(
        current_node=SimpleNamespace(allow_interrupt=False)
    )
    return moteur


@pytest.mark.asyncio
async def test_accueil_eteint_le_micro_reste_coupe_pendant_l_accueil():
    moteur = _moteur_pendant_l_accueil(interruptible=False)
    assert await moteur.should_mute_user(BotStartedSpeakingFrame()) is True


@pytest.mark.asyncio
async def test_accueil_allume_le_controleur_de_l_amont_decide():
    moteur = _moteur_pendant_l_accueil(interruptible=True)
    assert await moteur.should_mute_user(BotStartedSpeakingFrame()) is False
