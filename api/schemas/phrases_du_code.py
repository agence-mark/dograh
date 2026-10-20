"""[.mark] Chantier fiabilite-orchestration (F15, F18, F23) : une règle de phrase dite par le code.

Une règle = un **motif** (une attente ou un problème que le code sait détecter, pris dans le
catalogue ``api.services.phrases.catalogue``) + un **endroit** (le groupe, l'agent, ou une étape de
l'agent) + **une à trois variantes** de phrase (tournées dans l'appel) + un **délai** (si le motif
en a un) + **activée**. Rangée dans la configuration de l'agent (clé ``phrases_regles``) : aucune
migration de base. ⛔ Aucun mot de métier ici : le texte est une donnée réglée à l'écran.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_VARIANTES = 3
MAX_LONGUEUR_PHRASE = 300
MAX_REGLES = 60
DELAI_MIN_S = 0.5
DELAI_MAX_S = 120.0

PORTEE_GROUPE = "groupe"
PORTEE_AGENT = "agent"
PORTEE_ETAPE = "etape"


class ReglePhrase(BaseModel):
    motif: str = Field(
        ...,
        pattern=r"^[a-z][a-z_]{0,63}$",
        description="The cause or problem that makes the code speak (from the catalogue).",
    )
    portee: Literal["groupe", "agent", "etape"] = Field(
        default=PORTEE_AGENT,
        description=(
            "Where the rule applies: the whole group (set on the main agent), this agent, "
            "or one step of this agent."
        ),
    )
    etape: str | None = Field(
        default=None,
        max_length=200,
        description="The step name, for a step rule only.",
    )
    variantes: list[str] = Field(
        default_factory=list,
        max_length=MAX_VARIANTES,
        description=(
            "One to three sentences said by the voice, without the model. The code rotates "
            "them and never says the same one twice in a call while another is left."
        ),
    )
    delai_s: float | None = Field(
        default=None,
        ge=DELAI_MIN_S,
        le=DELAI_MAX_S,
        description="After how long the sentence is said, for a cause that has a delay.",
    )
    active: bool = Field(default=True, description="Off: the code says nothing for this cause.")

    @field_validator("variantes")
    @classmethod
    def _variantes_propres(cls, variantes: list[str]) -> list[str]:
        propres: list[str] = []
        for brute in variantes or []:
            texte = " ".join(str(brute or "").split())
            if not texte:
                continue
            if len(texte) > MAX_LONGUEUR_PHRASE:
                raise ValueError(
                    f"a sentence is longer than {MAX_LONGUEUR_PHRASE} characters"
                )
            if texte not in propres:
                propres.append(texte)
        return propres

    @model_validator(mode="after")
    def _endroit_coherent(self) -> ReglePhrase:
        from api.services.phrases.catalogue import MOTIFS

        if self.motif not in MOTIFS:
            raise ValueError(f"unknown cause: {self.motif}")
        if self.portee == PORTEE_ETAPE:
            if not (self.etape or "").strip():
                raise ValueError("a step rule needs its step name")
            self.etape = self.etape.strip()
        else:
            self.etape = None
        if self.active and not self.variantes:
            raise ValueError("an active rule needs at least one sentence")
        if not MOTIFS[self.motif].a_un_delai:
            self.delai_s = None
        return self

    @property
    def cle(self) -> tuple[str, str, str | None]:
        return (self.motif, self.portee, self.etape)


def verifier_regles(regles: list[ReglePhrase]) -> list[ReglePhrase]:
    """Deux règles du même motif au même endroit sont refusées (F23)."""
    vues: set[tuple[str, str, str | None]] = set()
    for regle in regles:
        if regle.cle in vues:
            endroit = regle.etape or regle.portee
            raise ValueError(f"two rules for the cause '{regle.motif}' at '{endroit}'")
        vues.add(regle.cle)
    return regles
