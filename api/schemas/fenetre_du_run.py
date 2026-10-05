"""[.mark] The run window's settings of an organization (chantier langwatch-et-fenetre-du-run, lot 2,
decisions L5, L6, L18): the price table and the incident thresholds.

Price table (L5):

The cost of a call is its consumption times these prices, declared by provider model and dated:
prices change, so the run window says « estimated at the rate of DD/MM ». Edited on the
organization screen (modal), never in a file. No price is written in the code: an empty table
means « cost not captured », never a guessed cost.

Incident thresholds (L6): the silence after a tool result that makes an incident (5 s by default)
and the turn the window highlights as slow (3 s by default).

One row of ``organization_configurations``, key ``FENETRE_DU_RUN`` (no migration).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

MAX_LIGNES = 200

Brique = Literal["llm", "stt", "tts", "telephony"]

# Which price each component needs (a price of another component is refused, to keep the table
# readable: a model priced per token AND per minute is a typing error).
PRIX_PAR_BRIQUE: dict[str, tuple[str, ...]] = {
    "llm": ("entree_par_million", "sortie_par_million"),
    "stt": ("par_minute",),
    "tts": ("par_million_caracteres",),
    "telephony": ("par_minute",),
}
PRIX_PERMIS: dict[str, tuple[str, ...]] = {
    **PRIX_PAR_BRIQUE,
    "llm": ("entree_par_million", "cache_par_million", "sortie_par_million"),
}
TOUS_LES_PRIX = (
    "entree_par_million",
    "cache_par_million",
    "sortie_par_million",
    "par_minute",
    "par_million_caracteres",
)


class LignePrix(BaseModel):
    brique: Brique = Field(
        description="Component: model (llm), transcription (stt), voice (tts) or telephony."
    )
    modele: str = Field(
        min_length=1,
        max_length=120,
        description="The model id exactly as the run records it (e.g. mistral-large-2512), or the telephony provider (e.g. twilio).",
    )
    entree_par_million: float | None = Field(
        default=None, ge=0, le=10000, description="Price per million input tokens."
    )
    cache_par_million: float | None = Field(
        default=None,
        ge=0,
        le=10000,
        description="Price per million cached input tokens; empty = the input price.",
    )
    sortie_par_million: float | None = Field(
        default=None, ge=0, le=10000, description="Price per million output tokens."
    )
    par_minute: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Price per minute (transcription, telephony).",
    )
    par_million_caracteres: float | None = Field(
        default=None,
        ge=0,
        le=10000,
        description="Price per million characters spoken (voice).",
    )
    date_du_tarif: date = Field(
        description="The date of the provider's rate this price was read from."
    )

    @model_validator(mode="after")
    def _prix_de_sa_brique(self) -> LignePrix:
        manquants = [
            p for p in PRIX_PAR_BRIQUE[self.brique] if getattr(self, p) is None
        ]
        if manquants:
            raise ValueError(
                f"{self.brique} {self.modele}: missing {', '.join(manquants)}"
            )
        etrangers = [
            p
            for p in TOUS_LES_PRIX
            if p not in PRIX_PERMIS[self.brique] and getattr(self, p) is not None
        ]
        if etrangers:
            raise ValueError(
                f"{self.brique} {self.modele}: {', '.join(etrangers)} does not apply"
            )
        return self


class Seuils(BaseModel):
    silence_apres_outil_s: float = Field(
        default=5.0,
        ge=1,
        le=60,
        description="Seconds without any reply of the agent after a tool result, the caller silent, that make an incident.",
    )
    tour_lent_s: float = Field(
        default=3.0,
        ge=0.5,
        le=30,
        description="Silence of a turn above which the run window highlights it as slow.",
    )


class ReglagesFenetreDuRun(BaseModel):
    format: Literal["fenetre-du-run-mark"] = "fenetre-du-run-mark"
    version: Literal[1] = 1
    devise: Literal["USD", "EUR"] = "USD"
    lignes: list[LignePrix] = Field(default_factory=list, max_length=MAX_LIGNES)
    seuils: Seuils = Field(default_factory=Seuils)

    @model_validator(mode="after")
    def _une_ligne_par_modele(self) -> ReglagesFenetreDuRun:
        vues: set[tuple[str, str]] = set()
        for ligne in self.lignes:
            cle = (ligne.brique, ligne.modele.strip())
            if cle in vues:
                raise ValueError(f"{ligne.brique} {ligne.modele}: declared twice")
            vues.add(cle)
        return self
