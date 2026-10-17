"""[.mark] Lot 3 d'orchestrateur-trois-cerveaux (D7) : le banc de passation de l'amont AVEC la voix de l'appel.

Le banc ``TransferHarness`` de ``api/tests/test_agent_transfer.py`` (amont) monte l'appel SANS voix :
avant la voix unique, chaque agent portait la sienne. Ici on lui donne ce que ``run_pipeline`` monte en
production : UNE voix après le pont (``build_pipeline(voice=...)``) et la route locale de la parole
dictée (``engine.set_parole_locale``). Les tests .mark qui jouent une vraie passation (voix entendue,
phrase pont, accueil) passent par là, au lieu de recopier le banc.

Utilisation::

    with voix_de_l_appel() as banc:
        harness = TransferHarness()
        await harness.build(...)
        brancher_la_parole_locale(harness, banc)
        ...
    banc.voix.received_texts   # tout ce que la voix de l'appel a dit
"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import api.tests.test_agent_transfer as banc_amont
from pipecat.tests import MockTTSService


@contextmanager
def voix_de_l_appel():
    """Le banc de l'amont monte sa voix : une seule, après le pont, comme ``run_pipeline``."""
    banc = SimpleNamespace(voix=None, pont=None, pipeline=None)
    reel = banc_amont.build_pipeline

    def monte(*args, **kwargs):
        banc.voix = MockTTSService(mock_audio_duration_ms=20, frame_delay=0)
        banc.pont = args[6][0]  # le segment de génération : [AgentBridgeProcessor]
        kwargs["voice"] = banc.voix
        banc.pipeline = reel(*args, **kwargs)
        return banc.pipeline

    with patch.object(banc_amont, "build_pipeline", monte):
        yield banc


def brancher_la_parole_locale(harness, banc) -> None:
    """Ce que ``run_pipeline`` fait avec le pont : la parole dictée pendant l'attente passe par lui."""
    harness.engine.set_parole_locale(banc.pont.dire_en_local)
