"""[.mark] The catalogue of deterministic sentences of an organization (E5).

Chantier ``l-agent-travaille`` (L2, 06/10/2026), decision E5: per client, a catalogue
of sentences, each with its variable name, a description, its content and its level
(organization or establishment). .mark creates, changes and places them, only on
Dograh's screen; the client will see them read-only. Each sentence is given to the
agents as ``{{variable}}`` in the call context, the establishment's content first when
the sentence is placed at the establishment's level.

The two pick-up announcements are two fiches of this catalogue, shown on screen with
the others but kept where they already live (the announcement settings and each
establishment's sentences): their variable names are reserved here, so no other
sentence can take them.

Stored as one row of ``organization_configurations`` under ``PHRASES`` (no migration).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_PHRASES = 100
MAX_LONGUEUR_CONTENU = 1000
MAX_LONGUEUR_DESCRIPTION = 200

_VARIABLE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")

# What Dograh or the fork already puts in the call context: a sentence named like one
# of them would be silently overwritten, or would overwrite it.
VARIABLES_RESERVEES = frozenset(
    {
        "annonce_fermeture",
        "annonce_pause",
        "annonce_ouverture",
        "etat_ouverture",
        "reouverture",
        "horaires_ouverture",
        "date_appel",
        "heure_appel",
        "adresse_etablissement",
        "etablissement",
        "etablissement_id",
        "numero_transfert",
        "lexique_propose",
        "lexique_a_ecouter",
        "caller_number",
        "called_number",
        "direction",
        "provider",
        "call_id",
        "workflow_run_id",
        "telephony_configuration_id",
        "runtime_configuration",
        "initial_context",
        "gathered_context",
        # l-agent-collegue (C4, C7): the team known to the agent and its closed list.
        "equipe",
        "equipe_cles",
    }
)

Niveau = Literal["organisation", "etablissement"]


class Phrase(BaseModel):
    variable: str = Field(description="Given to the agents as {{variable}}: lower case, digits, underscores.")
    description: str = Field(default="", max_length=MAX_LONGUEUR_DESCRIPTION, description="What it is for.")
    contenu: str = Field(default="", max_length=MAX_LONGUEUR_CONTENU, description="Said word for word. Empty: nothing given.")
    niveau: Niveau = Field(
        default="organisation",
        description="organisation: the same for every establishment. etablissement: each establishment may have its own.",
    )

    @field_validator("variable")
    @classmethod
    def _variable(cls, value: str) -> str:
        if not _VARIABLE.match(value):
            raise ValueError(
                f"« {value} »: a variable takes lower case letters, digits and underscores, 2 to 40 characters."
            )
        if value in VARIABLES_RESERVEES:
            raise ValueError(f"« {value} » is already given to the agents by Dograh: choose another name.")
        return value

    @field_validator("description", "contenu", mode="before")
    @classmethod
    def _propre(cls, value):
        return value.strip() if isinstance(value, str) else value


class CataloguePhrases(BaseModel):
    format: Literal["phrases-mark"] = "phrases-mark"
    version: Literal[1] = 1
    phrases: list[Phrase] = Field(default_factory=list, max_length=MAX_PHRASES)

    @model_validator(mode="after")
    def _uniques(self):
        vues: set[str] = set()
        for phrase in self.phrases:
            if phrase.variable in vues:
                raise ValueError(f"Two sentences share the variable « {phrase.variable} ».")
            vues.add(phrase.variable)
        return self
