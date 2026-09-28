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
from api.services.lexique.epellation import terme_epele

MARQUE = "[Épellation"


def phrase_de_mention(epellation: Epellation, terme: str | None = None) -> str:
    """🆕 Q6 (plan « le lexique », 26/09): letters that spell a term of the
    vocabulary are that term -- a brand, never the person's name (run 803)."""
    if terme:
        return (
            f"{MARQUE} : la personne a épelé « {epellation.epele} », c'est « {terme} » "
            "(lexique de l'entreprise) : ce n'est jamais le nom de la personne.]"
        )
    return (
        f"{MARQUE} : la personne a épelé « {epellation.epele} ». "
        "Note exactement ces lettres, sans les corriger et sans les faire répéter.]"
    )


def mentionner_epellations(
    texte: str, epellations: list[Epellation], termes: dict[str, str] | None = None
) -> str:
    """``texte`` followed by one note per spelling, or ``texte`` unchanged.

    ``termes``: the vocabulary's spellings (normalised -> official), to say when
    the letters spell one of its terms (Q6)."""
    if not epellations:
        return texte
    return " ".join(
        [texte, *(phrase_de_mention(e, terme_epele(e.epele, termes)) for e in epellations)]
    )


def deja_mentionne(texte: str) -> bool:
    return MARQUE in texte
