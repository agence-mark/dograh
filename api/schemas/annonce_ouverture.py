"""[.mark] What the agent says at pick-up when the business is closed, and the
state forced by hand: the format of the organization's setting and its bounds.

Why this schema exists
----------------------
The chantier ``corrections-appels-agent-6`` (18/09/2026) made the closing
announcement computed by the code instead of asked of the model, which fixed 12
missing announcements out of 21 calls. But the two sentences were written IN THE
CODE. Evan, the same day: *« nous devons avoir des champs configurables dans les
settings afin de pouvoir modifier les phrases et les états du magasin »*. A
setting that changes what a caller hears is seen and changed on screen.

Decisions of 2026-09-18, referenced as A to F in the plan
``_AUTONOMIE/plans/en-cours/reglages-annonce-ouverture/``:

- A: one sentence per state that speaks, two in all (closed, on a break).
  OUVERT and SUR_RENDEZ_VOUS announce nothing and stay that way.
- B: ``{reouverture}`` is the spoken reopening, and what is in brackets
  disappears when it is unknown.
- C: the end of a forced state is a date and a time, never free text; the code
  puts it in words, with the rules of the automatic computation.
- D: an empty sentence announces nothing.
- E/F: these settings live on the ORGANIZATION (the opening hours stay on each
  agent, they describe a place), with no per-agent override for now.

Stored as one row of ``organization_configurations`` under ``ANNONCE_OUVERTURE``:
a free-text key of an existing table, so no migration (same as the trade
vocabulary).

⛔ The bounds are checked when the setting is SAVED, never when a call reads it:
a refusal must never cost a call (same rule as the address and the vocabulary).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator

# ⛔ The neutral module, never the service one: a schema that imports a service
# is the wrong way round, and it only held because that service imports nothing
# from ``api.*`` at load time (review of 2026-09-18, S5).
from api.services.annonce.constantes import (
    ANNONCE_FERMETURE_DEFAUT,
    ANNONCE_PAUSE_DEFAUT,
    ETATS,
    JETON_REOUVERTURE,
)

MAX_LONGUEUR_ANNONCE = 300

# ⛔ Duplicated on purpose: pydantic needs a static Literal to generate the
# screen's types. ``test_annonce_ouverture_stockage`` asserts it still matches
# ``ETATS``, so the two can never drift apart in silence.
EtatForce = Literal["OUVERT", "PAUSE", "FERME", "SUR_RENDEZ_VOUS"]

_AUTRE_JETON = re.compile(r"\{([^}]*)\}")


def verifier_modele_annonce(texte: str) -> str:
    """Refuse what would be heard wrong, and say why.

    ⚠️ In English, like every other refusal shown on this screen (the trade
    vocabulary's are too): the settings page is in English throughout.

    Three things are checked, because each of them is a silent defect at the
    other end of a phone line:

    - brackets that do not close: the whole optional part would be dropped when
      the reopening is unknown, final full stop included;
    - a placeholder that is not ``{reouverture}``: a typo such as
      ``{reouvertue}`` would be said out loud, braces and all;
    - a lone brace: ``_AUTRE_JETON`` needs a closing one to see a placeholder at
      all, so ``« Fermé { en ce moment »`` used to pass and the brace reached the
      voice (independent review of 2026-09-18, Mineur 3).
    """
    profondeur = 0
    for caractere in texte:
        if caractere == "[":
            if profondeur:
                raise ValueError("Brackets do not nest: « [ … [ … ] ] ».")
            profondeur += 1
        elif caractere == "]":
            if not profondeur:
                raise ValueError("A « ] » with no « [ » before it.")
            profondeur -= 1
    if profondeur:
        raise ValueError("A « [ » that is never closed.")

    for jeton in _AUTRE_JETON.findall(texte):
        if jeton != JETON_REOUVERTURE:
            raise ValueError(
                f"« {{{jeton}}} » does not exist: the only variable is "
                f"« {{{JETON_REOUVERTURE}}} », the spoken reopening."
            )
    reste = texte.replace("{" + JETON_REOUVERTURE + "}", "")
    if "{" in reste or "}" in reste:
        raise ValueError(
            "A lone « { » or « } »: it would be said out loud. The only variable "
            f"is « {{{JETON_REOUVERTURE}}} »."
        )
    return texte


class ReglagesAnnonceOuverture(BaseModel):
    """The organization's announcement sentences and its forced state."""

    format: Literal["annonce-ouverture-mark"] = "annonce-ouverture-mark"
    version: Literal[1] = 1

    annonce_fermeture: str = Field(
        default=ANNONCE_FERMETURE_DEFAUT,
        max_length=MAX_LONGUEUR_ANNONCE,
        description=(
            "Said at pick-up when the business is closed. « {reouverture} » is the "
            "spoken reopening; what is in brackets disappears when it is unknown. "
            "Empty announces nothing."
        ),
    )
    annonce_pause: str = Field(
        default=ANNONCE_PAUSE_DEFAUT,
        max_length=MAX_LONGUEUR_ANNONCE,
        description=(
            "Said at pick-up when the business is on a break (already open today "
            "and reopening today). Same rules as the closing sentence."
        ),
    )
    etat_force: EtatForce | None = Field(
        default=None,
        description=(
            "The state every agent of this organization is in, whatever the hours "
            "say. None: computed from the hours. ⚠️ A forced state closes ALL the "
            "agents of the organization."
        ),
    )
    etat_force_jusqu_a: datetime | None = Field(
        default=None,
        description=(
            "When the forced state lifts itself, Paris time. It is also the "
            "reopening the agent announces. None: the forcing holds until someone "
            "goes back to « computed »."
        ),
    )

    @field_validator("etat_force_jusqu_a")
    @classmethod
    def _en_heure_de_paris(cls, value: datetime | None) -> datetime | None:
        """Stored as a Paris wall clock, with no offset -- which is what it means.

        The screen's ``datetime-local`` field only ever produces a naive value.
        A row written elsewhere (MCP, curl) may carry an offset; converting it
        here means the screen shows the right local time and the next save does
        not shift it by an hour or two in silence (independent review of
        2026-09-18, Mineur 5).
        """
        if value is None or value.tzinfo is None:
            return value
        return value.astimezone(ZoneInfo("Europe/Paris")).replace(tzinfo=None)

    @field_validator("annonce_fermeture", "annonce_pause", mode="before")
    @classmethod
    def _nettoyer(cls, value):
        if isinstance(value, str):
            return re.sub(r"[ \t]+", " ", value).strip()
        return value

    @field_validator("annonce_fermeture", "annonce_pause")
    @classmethod
    def _modele_lisible(cls, value: str) -> str:
        return verifier_modele_annonce(value)

    @model_validator(mode="after")
    def _une_date_de_fin_suppose_un_forcage(self):
        """An end date without a forced state means nothing, and reads as a plan.

        Refused rather than ignored: someone who typed a date and left the state
        on « computed » believes the business will close on that date.
        """
        if self.etat_force_jusqu_a is not None and self.etat_force is None:
            raise ValueError(
                "An end date means nothing without a forced state: choose a state, "
                "or clear the date."
            )
        return self
