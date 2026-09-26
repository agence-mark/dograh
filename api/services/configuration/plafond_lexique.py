"""[.mark] How long a list of terms each transcription provider accepts to listen for.

Why this module exists
----------------------
On 2026-09-18 a list of terms too long was refused by Deepgram when the call
connected, and every agent of the organization fell silent. The budget was
then written inside the vocabulary module, in terms and characters
(120 / 1 600). Decisions of Evan, 2026-09-26 (plan « le lexique », Q1):

- the ceiling is DECLARED WITH THE PROVIDER, here, next to the declaration of
  the transcription providers, and nowhere else (not editable on screen);
- a provider with no declared ceiling receives NO list at all: an unknown
  limit is a risk of refusal, and a refusal costs the call its transcription;
- the value of a provider is the limit measured on it, minus a written margin.

What the probe of 2026-09-26 measured (connections without audio, Europe
endpoint, the 181 real terms of a vocabulary, in two orders)
--------------------------------------------------------------------------
- ``flux-general-*``: a limit in NUMBER of terms, 100, whatever their length
  (« Received 101 keyterms, which is more than the limit of 100. »). No token
  limit was reached up to 100 terms of 1 241 characters.
- ``nova-3``: 500 tokens across all terms (« Keyterm limit exceeded. The
  maximum number of tokens across all keyterms is 500. »).

⛔ Never write a ceiling anywhere else: the vocabulary module, the call and the
screen all read it from ``plafond_du_lexique``. A test searches the code for a
second one.

How the tokens are counted (a prudent estimate, not the provider's tokenizer)
-----------------------------------------------------------------------------
Each term costs ``ceil(bytes / octets_par_jeton) + jetons_par_terme``. Fitted on
the two frontiers the probe measured on nova-3: 539 estimated for the last
list accepted, 544 for the first refused, in BOTH orders -- about 8 % above
the real count. That 8 % (about 40 real tokens under 500) is the written
margin: the list sent is never longer than the one measured to pass.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from api.services.configuration.registry import ServiceProviders


@dataclass(frozen=True)
class PlafondLexique:
    """The ceiling of the list of terms, for one provider (or one family of its models)."""

    # The provider's name as the screen shows it: « 81 / 100 terms (Deepgram) ».
    fournisseur: str
    # The ceiling in tokens, None when the provider counts no tokens.
    jetons: int | None
    # The ceiling in number of terms, None when the provider does not count them.
    termes: int | None
    # The estimate of one term's tokens (see the module).
    octets_par_jeton: float
    jetons_par_terme: int
    # Where the value comes from, read by whoever changes it.
    source: str


_SONDE = "sonde du 26/09/2026 (connexions sans audio, point Europe, 181 termes réels, deux ordres)"

# Margin: none. A count does not vary, and Deepgram states the exact rule.
_DEEPGRAM_FLUX = PlafondLexique(
    fournisseur="Deepgram",
    jetons=None,
    termes=100,
    octets_par_jeton=3.5,
    jetons_par_terme=2,
    source=_SONDE + " : 101 termes refusés, 100 acceptés jusqu'à 1 241 caractères",
)
# Margin: the estimate's own (≈ 8 %, see the module).
_DEEPGRAM_JETONS = PlafondLexique(
    fournisseur="Deepgram",
    jetons=500,
    termes=None,
    octets_par_jeton=3.5,
    jetons_par_terme=2,
    source=_SONDE + " : nova-3 refuse au-delà de 500 jetons",
)

# Provider -> (model prefix, ceiling), the first matching prefix wins; "" matches
# every other model of the provider. A provider absent from this table has no ceiling.
# ⚠️ Deepgram's models other than Flux get the nova-3 rule, the one measured in tokens.
PLAFONDS: dict[str, tuple[tuple[str, PlafondLexique], ...]] = {
    ServiceProviders.DEEPGRAM.value: (("flux", _DEEPGRAM_FLUX), ("", _DEEPGRAM_JETONS)),
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
    return math.ceil(len(terme.encode("utf-8")) / plafond.octets_par_jeton) + plafond.jetons_par_terme
