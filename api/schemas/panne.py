"""[.mark] The outage fallback (chantier l-agent-travaille, L7; plan panne-vers-magasin P1 to P13,
decisions PN1 to PN8 of 06/10/2026).

When a part of the agent fails (voice, transcription, model, the whole chain), the caller is no
longer lost in silence: Twilio speaks with its own voice, hands the call to the establishment's
second number if it is open (20 s of ringing), else promises a call-back with the date and hangs
up; and always, a request « to call back » is written and an alert goes to the notification
addresses.

- ``PanneAgent``: switched on agent by agent, off by default (X2), with its thresholds. Stored in
  ``workflow_configurations["panne"]`` (no migration), checked at save, read without raising.
- ``ReglagesPanne``: the organization's emergency address (the TwiML Bin created once in its
  Twilio console, PN5), in ``organization_configurations`` under ``PANNE``.
- The two sentences are two fiches of the catalogue of sentences (PN7), with the establishment's
  content first; empty or absent: the defaults below, never silence.
"""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

CLE_AGENT = "panne"

# PN7: the variables of the two fiches of the catalogue, and their defaults.
VARIABLE_RENVOI = "phrase_renvoi_panne"
VARIABLE_RAPPEL = "phrase_rappel_panne"
VARIABLE_EXCUSE = "phrase_excuse_panne"
DEFAUT_RENVOI = (
    "Je rencontre un souci technique, je vous passe un collaborateur, ne quittez pas."
)
# {reouverture} and the square brackets work like the closing announcement: an unknown reopening
# removes the bracketed part.
DEFAUT_RAPPEL = "Je rencontre un souci technique. Nous vous rappelons [dès la réouverture, {reouverture}]. Merci et au revoir."
DEFAUT_EXCUSE = "Je rencontre un souci technique, je vous prie de m'excuser. Nous vous rappellerons. Au revoir."
# PN5: what the emergency instruction says when nobody answers (it knows no hours, so no date).
DEFAUT_RAPPEL_SANS_DATE = "Nous vous rappelons dès que possible. Merci et au revoir."

# P6: Twilio's own French voice, independent of our voice provider (maybe the part that failed).
VOIX_TWILIO = "Polly.Lea-Neural"
LANGUE_TWILIO = "fr-FR"


class PanneAgent(BaseModel):
    actif: bool = Field(
        default=False,
        description=(
            "When a part of this agent fails, Twilio hands the call to the establishment's second "
            "number if it is open, else promises a call-back; a request to call back is always "
            "written and an alert sent. Off: the agent behaves exactly as before."
        ),
    )
    delai_modele_s: float = Field(
        default=4.0,
        ge=0.1,
        le=30,
        description="PN2: past this delay without the model's answer, « Un instant », then a new try; the second time, the fallback.",
    )
    delai_voix_s: float = Field(
        default=3.0,
        ge=0.5,
        le=30,
        description="PN3: past this delay between the text sent to the voice and its first sound, the fallback.",
    )
    sonnerie_s: int = Field(
        default=20, ge=5, le=60, description="PN1: how long the second number rings."
    )


class ReglagesPanne(BaseModel):
    format: str = "panne-mark"
    version: int = 1
    url_secours: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "The address of the TwiML Bin « hand-over then promise » created once in the "
            "client's Twilio console (PN5). Empty: no instruction after the stream, the 40 s "
            "pause of before."
        ),
    )
    url_secours_promesse: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "Decision of Evan, 07/10: the second TwiML Bin, « promise only », for the "
            "establishments without a second number. Empty: they get the first Bin."
        ),
    )

    @field_validator("url_secours", "url_secours_promesse")
    @classmethod
    def _url(cls, valeur: str | None) -> str | None:
        valeur = (valeur or "").strip() or None
        if valeur is None:
            return None
        partie = urlparse(valeur)
        if (
            partie.scheme != "https"
            or not partie.netloc
            or "?" in valeur
            or "#" in valeur
        ):
            raise ValueError(
                "The emergency address is an https address of a TwiML Bin, without parameters."
            )
        return valeur


def panne_de_lagent(workflow_configurations: dict | None) -> PanneAgent:
    """What this agent switched on. Absent or unreadable: off (X2), never an error."""
    brut = (workflow_configurations or {}).get(CLE_AGENT)
    if not brut:
        return PanneAgent()
    try:
        return PanneAgent.model_validate(brut)
    except Exception:  # noqa: BLE001 -- read at call setup: never kill the call
        return PanneAgent()
