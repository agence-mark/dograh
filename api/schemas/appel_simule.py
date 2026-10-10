"""[.mark] The simulated caller's settings and scenario library (chantier langwatch-et-fenetre-du-run,
lot 3, decisions L10, L13, L18, L19, Q1 to Q3).

Everything here is edited on screen, in modals (L18), never in a file or an environment variable.
Keys are never stored here: only the id of a credential saved in Dograh, picked in a list.

- ``ReglagesAppelantSimule`` (organization): the simulated caller's and the judge's model, prompt
  and key; the caller's voice; how many calls at once (1 by default, L13); the size of a series
  and its spending cap (5 by default, in the price table's currency, Q3). One row of ``organization_configurations``, key
  ``APPELANT_SIMULE``.
- ``BibliothequeScenarios`` (organization, filed by agent, L10): a scenario is a declaration (who
  calls and why, behaviours, the judge's criteria, an optional latency threshold). Zero trade
  vocabulary in the code: the words of a trade live in the scenarios written on screen. One row,
  key ``SCENARIOS_SIMULES``.

No migration: free-text keys of the existing table.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# The models the simulated caller and the judge can use (L18: a drop-down list). Mistral only for
# now (Q1); the « mistral/ » prefix is the one LangWatch Scenario (litellm) expects.
MODELES_SIMULATEUR = (
    "mistral/mistral-small-latest",
    "mistral/mistral-medium-latest",
    "mistral/mistral-large-latest",
)
ModeleSimulateur = Literal[
    "mistral/mistral-small-latest",
    "mistral/mistral-medium-latest",
    "mistral/mistral-large-latest",
]

# Generic prompts: how to play a caller on the phone, how to judge a call. Nothing of a trade.
CONSIGNE_APPELANT = (
    "Tu joues une personne qui appelle une entreprise au téléphone. Tu parles français, en phrases "
    "courtes et naturelles, comme à l'oral. Tu ne sais que ce que ton rôle dit ; si l'on te demande "
    "un détail que ton rôle ne donne pas, invente-le plausible et garde-le cohérent jusqu'au bout. "
    "Tu ne joues jamais l'agent. Quand ton objectif est atteint, ou que l'agent conclut, dis au "
    "revoir."
)
CONSIGNE_JUGE = (
    "Tu évalues un appel téléphonique entre un agent vocal et un appelant. Juge chaque critère "
    "uniquement sur ce qui a été réellement dit dans l'appel. Un critère non vérifiable dans la "
    "conversation est un échec. Explique ton verdict en français, en quelques phrases."
)

PLAFOND_SIMULTANES = 3
MAX_SCENARIOS = 300
MAX_CRITERES = 12
MAX_CHAMPS_ATTENDUS = 40


class RoleSimule(BaseModel):
    modele: ModeleSimulateur = Field(
        default="mistral/mistral-small-latest", description="Model, from the list."
    )
    identifiant: str | None = Field(
        default=None,
        max_length=36,
        description="UUID of the Dograh credential holding the model's key (an organization other than the agent's, Q1).",
    )
    consigne: str = Field(min_length=1, max_length=6000, description="Prompt.")
    temperature: float = Field(default=0.3, ge=0, le=1)


class VoixSimulee(BaseModel):
    voix: str = Field(
        default="",
        max_length=80,
        description="ElevenLabs voice id of the simulated caller (Q2: a French voice).",
    )
    identifiant: str | None = Field(
        default=None,
        max_length=36,
        description="UUID of the Dograh credential holding the ElevenLabs key (voice and transcription of the agent).",
    )


class ReglagesAppelantSimule(BaseModel):
    format: Literal["appelant-simule-mark"] = "appelant-simule-mark"
    version: Literal[1] = 1
    appelant: RoleSimule = Field(
        default_factory=lambda: RoleSimule(consigne=CONSIGNE_APPELANT, temperature=0.5)
    )
    juge: RoleSimule = Field(
        default_factory=lambda: RoleSimule(consigne=CONSIGNE_JUGE, temperature=0.0)
    )
    voix: VoixSimulee = Field(default_factory=VoixSimulee)
    simultanes: int = Field(
        default=1,
        ge=1,
        le=PLAFOND_SIMULTANES,
        description="Calls played at once in a series (L13: 1 by default, the Mistral limit).",
    )
    taille_max_serie: int = Field(default=10, ge=1, le=50)
    plafond: float = Field(
        default=5.0,
        gt=0,
        le=200,
        description="Spending cap of one series (Q3), in the price table's currency (USD by default).",
    )


class Comportements(BaseModel):
    presse: bool = False
    coupe_la_parole: bool = False
    hesite: bool = False
    se_tait: bool = False


class ScenarioSimule(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    workflow_id: int = Field(ge=1, description="The agent the scenario is filed with.")
    nom: str = Field(min_length=1, max_length=120)
    role: str = Field(
        min_length=1,
        max_length=4000,
        description="Who calls and why: what the simulated caller knows and wants.",
    )
    consigne: str = Field(
        default="", max_length=4000, description="Extra instructions to the caller."
    )
    comportements: Comportements = Field(default_factory=Comportements)
    criteres: list[str] = Field(min_length=1, max_length=MAX_CRITERES)
    tours_max: int = Field(default=12, ge=2, le=40)
    renvoi: Literal["refuse", "accepte", "sans_reponse"] = Field(
        default="refuse",
        description="What the simulated transfer answers if the agent transfers the call.",
    )
    latence_max_s: float | None = Field(
        default=None,
        ge=0.5,
        le=30,
        description="If set, a turn slower than this fails the scenario.",
    )
    # D7 (réparation globale, L8): lives in the scenario's JSON, no migration.
    fiche_attendue: dict[str, str | None] | None = Field(
        default=None,
        max_length=MAX_CHAMPS_ATTENDUS,
        description=(
            "The call record the scenario expects, field -> value (null: the field must stay empty). "
            "Rated by the code at the end of the run: juste_sur, juste_a_confirmer, vide, faux."
        ),
    )

    @model_validator(mode="after")
    def _criteres_non_vides(self) -> ScenarioSimule:
        self.criteres = [c.strip() for c in self.criteres if c.strip()]
        if not self.criteres:
            raise ValueError("A scenario needs at least one criterion.")
        if any(len(c) > 500 for c in self.criteres):
            raise ValueError("A criterion is 500 characters at most.")
        if self.fiche_attendue is not None:
            nettoyee = {
                champ.strip(): (valeur.strip() if isinstance(valeur, str) and valeur.strip() else None)
                for champ, valeur in self.fiche_attendue.items()
                if champ.strip()
            }
            if any(len(champ) > 80 for champ in nettoyee) or any(len(v or "") > 500 for v in nettoyee.values()):
                raise ValueError("An expected field is 80 characters at most, its value 500.")
            self.fiche_attendue = nettoyee or None
        return self


class BibliothequeScenarios(BaseModel):
    format: Literal["scenarios-simules-mark"] = "scenarios-simules-mark"
    version: Literal[1] = 1
    scenarios: list[ScenarioSimule] = Field(
        default_factory=list, max_length=MAX_SCENARIOS
    )

    @model_validator(mode="after")
    def _uniques(self) -> BibliothequeScenarios:
        ids = [s.id for s in self.scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("Two scenarios share the same id.")
        noms = [(s.workflow_id, s.nom.strip().casefold()) for s in self.scenarios]
        if len(noms) != len(set(noms)):
            raise ValueError("Two scenarios of the same agent share the same name.")
        return self
