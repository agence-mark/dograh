"""[.mark] The organization's price table (chantier langwatch-et-fenetre-du-run, lot 2, decision L5).

The cost of a call is its consumption times these prices, declared by provider model and dated:
prices change, so the run window says « estimated at the rate of DD/MM ». Edited on the
organization screen (modal), never in a file. No price is written in the code: an empty table
means « cost not captured », never a guessed cost.

One row of ``organization_configurations``, key ``TABLE_DES_PRIX`` (no migration).
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


class TableDesPrix(BaseModel):
    format: Literal["table-des-prix-mark"] = "table-des-prix-mark"
    version: Literal[1] = 1
    devise: Literal["USD", "EUR"] = "USD"
    lignes: list[LignePrix] = Field(default_factory=list, max_length=MAX_LIGNES)

    @model_validator(mode="after")
    def _une_ligne_par_modele(self) -> TableDesPrix:
        vues: set[tuple[str, str]] = set()
        for ligne in self.lignes:
            cle = (ligne.brique, ligne.modele.strip())
            if cle in vues:
                raise ValueError(f"{ligne.brique} {ligne.modele}: declared twice")
            vues.add(cle)
        return self
