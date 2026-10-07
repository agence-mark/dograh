"""[.mark] The hang-up that leaves a handed-over call alone (L7, constat C2).

Dograh hangs up actively: on ``EndFrame`` and ``CancelFrame`` the Twilio serializer sets the call
to ``completed`` through the API (F2). Once the outage guard has given the call a new instruction
(hand-over, call-back promise), that hang-up would cut the caller off in the middle of it. The
guard writes the call here BEFORE it updates Twilio; ``TwilioHangupStrategyMark`` (next to the
Twilio transport) then does nothing for it, and hangs up every other call exactly as before.

In memory: the guard and the serializer of a call live in the same process (the pipeline).
"""

from __future__ import annotations

import time

DUREE_S = 3600.0
_RENVOYES: dict[str, float] = {}


def marquer_renvoye(call_sid: str) -> None:
    maintenant = time.monotonic()
    for sid, quand in list(_RENVOYES.items()):
        if maintenant - quand > DUREE_S:
            _RENVOYES.pop(sid, None)
    _RENVOYES[call_sid] = maintenant


def oublier(call_sid: str) -> None:
    _RENVOYES.pop(call_sid, None)


def est_renvoye(call_sid: str | None) -> bool:
    return bool(call_sid) and call_sid in _RENVOYES
