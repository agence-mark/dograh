"""[.mark] The note on spelled letters added to the caller's message.

🔑 The instruction to the agent lives HERE, in the note, and in no agent's
prompt — same decision as the town check (2026-09-16): every agent gets the
behaviour without anyone editing its prompt.

The wording, word for word (plan adresses-et-epellation, N1):

- one spelling:
  ``[Épellation : la personne a épelé « FLAMANT ». Note exactement ces lettres,
  sans les corriger et sans les faire répéter.]``
- several in the same turn: one note each, in the order they were said.

⚠️ The note does NOT say "do not say it out loud". The other session's filter
(``filtre_nom_civilite.py``) decided on purpose that a spelled name may be
spoken: spelling confirms in both directions. We do not contradict that choice.

⛔ ``MARQUE`` makes the note idempotent: a message that already carries one is
never annotated twice.
"""

from __future__ import annotations

from api.services.epellation.lecture import Epellation

MARQUE = "[Épellation"


def phrase_de_mention(epellation: Epellation) -> str:
    return (
        f"{MARQUE} : la personne a épelé « {epellation.epele} ». "
        "Note exactement ces lettres, sans les corriger et sans les faire répéter.]"
    )


def mentionner_epellations(texte: str, epellations: list[Epellation]) -> str:
    """``texte`` followed by one note per spelling, or ``texte`` unchanged."""
    if not epellations:
        return texte
    return " ".join([texte, *(phrase_de_mention(e) for e in epellations)])


def deja_mentionne(texte: str) -> bool:
    return MARQUE in texte
