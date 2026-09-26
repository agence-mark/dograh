"""[.mark] How many terms each transcription provider accepts to listen for.

Why this module exists
----------------------
On 2026-09-18 a list of terms too long was refused by Deepgram when the call
connected, and every agent of the organization fell silent. The budget was
then written inside the vocabulary module, in terms and characters
(120 / 1 600), while Deepgram counts in TOKENS -- and another provider (Soniox)
accepts far more. Decisions of Evan, 2026-09-26 (plan « le lexique », Q1):

- the ceiling is DECLARED WITH THE PROVIDER, here, next to the declaration of
  the transcription providers, and nowhere else (not editable on screen);
- a provider with no declared ceiling receives NO list at all: an unknown
  limit is a risk of refusal, and a refusal costs the call its transcription;
- the value of a provider is the limit measured on it, minus a written margin.

⛔ Never write a ceiling anywhere else: the vocabulary module, the call and the
screen all read it from ``plafond_du_lexique``. A test searches the code for a
second one.

How the tokens are counted (a prudent estimate, not the provider's tokenizer)
-----------------------------------------------------------------------------
Each term costs ``ceil(bytes / octets_par_jeton) + 1``: its UTF-8 bytes (an
accent costs two, never less than the letter it carries) divided by what one
token holds for this provider, rounded UP, plus one for the term itself (its
boundary). Rounding up on every term, and counting bytes rather than
characters, can only overestimate: the list sent is never longer than the one
that was measured to pass.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from api.services.configuration.registry import ServiceProviders


@dataclass(frozen=True)
class PlafondLexique:
    """The ceiling of the list of terms, for one provider (or one family of its models)."""

    # The provider's name as the screen shows it: « 212 / 450 tokens (Deepgram) ».
    fournisseur: str
    # The ceiling retained, in tokens: the measured limit minus the margin.
    jetons: int
    # What one token holds, in UTF-8 bytes, for the estimate (see the module).
    octets_par_jeton: float
    # Where the value comes from, read by whoever changes it.
    source: str


# 🔴 PROVISIONAL until the probe of the plan (step 1) has measured the limit on
# the production models: 500 is the limit Deepgram documents for keyterm
# prompting, minus 10 %. The probe replaces this value and ``source``.
_DEEPGRAM = PlafondLexique(
    fournisseur="Deepgram",
    jetons=450,
    octets_par_jeton=3.0,
    source="PROVISOIRE : limite documentée de Deepgram (500 jetons) moins 10 %, en attente de la sonde",
)

# Provider -> (model prefix, ceiling), the first matching prefix wins; "" matches
# every model of the provider. A provider absent from this table has no ceiling.
PLAFONDS: dict[str, tuple[tuple[str, PlafondLexique], ...]] = {
    ServiceProviders.DEEPGRAM.value: (("", _DEEPGRAM),),
}


def plafond_du_lexique(fournisseur: str | None, modele: str | None) -> PlafondLexique | None:
    """The ceiling declared for this provider and model, or None: then no list is sent."""
    fournisseur = str(getattr(fournisseur, "value", fournisseur) or "")
    for prefixe, plafond in PLAFONDS.get(fournisseur, ()):
        if (modele or "").startswith(prefixe):
            return plafond
    return None


def jetons_du_terme(terme: str, plafond: PlafondLexique) -> int:
    """The prudent cost of one term, in tokens (rule in the module's docstring)."""
    return math.ceil(len(terme.encode("utf-8")) / plafond.octets_par_jeton) + 1
