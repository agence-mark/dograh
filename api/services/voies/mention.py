"""[.mark] The note on the street added to the caller's message.

🔑 The instruction to the agent lives HERE, in the note, and in no agent's
prompt — same decision as the town check (2026-09-16).

The wording, word for word (plan adresses-et-epellation, Q4):

- sure:
  ``[Vérification de la rue : « rue d'antan » correspond à Rue Danton.
  Utilise ce nom sans le faire répéter.]``
- to confirm (one to three proposals):
  ``[Vérification de la rue : « rue de bray » peut être Rue de Bray ou Rue du
  Bray. Demande d'abord si c'est Rue de Bray ; si ce n'est pas elle, propose
  Rue du Bray. Si aucune ne convient, fais épeler le nom de la rue une seule
  fois, puis note ce qui a été épelé.]``
- not found:
  ``[Vérification de la rue : « rue du Lavoira » ne correspond à aucune rue de
  la commune. Fais épeler le nom de la rue une seule fois, puis note ce qui a
  été épelé.]``

⚠️ **One single spelling, never a loop** (Q4, Evan 2026-09-22): once spelled,
the street is never questioned again, even absent from the base. A base is
never complete, and making a caller repeat their own address is worse than
recording a street the base does not know.

⛔ Q5: the note says NOTHING about the number. A number missing from the base
must not make the caller repeat it — it is only recorded in the call's trace.

⛔ ``MARQUE`` makes the note idempotent.
"""

from __future__ import annotations

from api.services.voies.analyse import SURE, Detection

MARQUE = "[Vérification de la rue"

# Q4, word for word: what the agent does when the street is not settled.
EPELLATION = (
    "fais épeler le nom de la rue une seule fois, puis note ce qui a été épelé.]"
)


def _enumerer(noms: list[str]) -> str:
    if len(noms) == 1:
        return noms[0]
    return ", ".join(noms[:-1]) + " ou " + noms[-1]


def phrase_de_mention(detection: Detection) -> str:
    if detection.statut == SURE:
        return (
            f"{MARQUE} : « {detection.entendu} » correspond à {detection.retenue}. "
            "Utilise ce nom sans le faire répéter.]"
        )
    if not detection.propositions:
        return (
            f"{MARQUE} : « {detection.entendu} » ne correspond à aucune rue de la commune. "
            f"{EPELLATION[0].upper()}{EPELLATION[1:]}"
        )
    noms = [proposition.nom for proposition in detection.propositions]
    if len(noms) == 1:
        demande = f"Demande si c'est {noms[0]}. Si ce n'est pas elle, {EPELLATION}"
    else:
        demande = (
            f"Demande d'abord si c'est {noms[0]} ; si ce n'est pas elle, "
            f"propose {', puis '.join(noms[1:])}. Si aucune ne convient, {EPELLATION}"
        )
    return f"{MARQUE} : « {detection.entendu} » peut être {_enumerer(noms)}. {demande}"


def mentionner_voie(texte: str, detection: Detection | None) -> str:
    """``texte`` followed by the street note, or ``texte`` unchanged."""
    if detection is None or not detection.entendu:
        return texte
    return f"{texte} {phrase_de_mention(detection)}"


def deja_mentionne(texte: str) -> bool:
    return MARQUE in texte
