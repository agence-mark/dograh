"""[.mark] The trade vocabulary of an organization: its format and its bounds.

Why this schema exists
----------------------
On the 2026-09-15 and 16 benches "Edilkamin" was transcribed "édile camembert",
then "Edilcamin", and the voice mispronounced it. A dictionary typed by hand per
agent does not carry over, so each organization holds ONE vocabulary of its
trade (decisions L1 to L4 of 2026-09-16), used in three places: the terms the
transcription listens for, the correction of misheard names before the model
reads them, and the pronunciation of the text sent to the voice.

Stored as one row of ``organization_configurations`` under
``LEXIQUE_METIER``: no migration. The template files of the socle
(``socle-agent-vocal/dograh/lexiques/``) and the export use the SAME format.

⛔ The bounds are checked when the vocabulary is SAVED, never when a call reads
it: a refusal must never cost a call (same rule as the business address).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from api.services.communes.base import normaliser

MAX_TERMES = 2000
MAX_LONGUEUR_TERME = 80
MAX_VARIANTES = 10
MAX_LONGUEUR_PRONONCIATION = 120
MAX_LONGUEUR_CATEGORIE = 30
MAX_MODELES_IMPORTES = 50
MAX_LONGUEUR_NOM_MODELE = 100


def normaliser_terme(texte: str) -> str:
    """The form two spellings are compared on: « Jøtul » and « jotul » are one.

    The town normalisation (lower case, no accents, punctuation to spaces),
    after the letters and signs brand names carry and it does not: ``ø`` has no
    accent to strip, « Haas+Sohn » and « Arts & Feu » keep their words apart.
    """
    t = texte.lower().replace("ø", "o").replace("&", " et ").replace("+", " ")
    return normaliser(t)


def _texte_nettoye(value):
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    return value


class TermeLexique(BaseModel):
    """One name or word of the trade."""

    terme: str = Field(
        min_length=1,
        max_length=MAX_LONGUEUR_TERME,
        description="The official spelling, the one the model reads and the agent writes.",
    )
    variantes: list[str] = Field(
        default_factory=list,
        max_length=MAX_VARIANTES,
        description="Other spellings of the same name (« Jotul », « Godin »).",
    )
    prononciation: str | None = Field(
        default=None,
        max_length=MAX_LONGUEUR_PRONONCIATION,
        description="How the voice should say it, written as it sounds. Only the text sent to the voice changes.",
    )
    type: Literal["nom", "mot"] = Field(
        default="nom",
        description=(
            "nom: recognised and corrected before the model reads it. "
            "mot: a common word of the trade, only listened for by the transcription."
        ),
    )
    categorie: str | None = Field(default=None, max_length=MAX_LONGUEUR_CATEGORIE)
    a_ecouter: bool = Field(
        default=False,
        description="Sent to the transcription as a term to listen for (after the agent's Dictionary).",
    )
    # [.mark] Plan « le lexique », L3 / Q4 (2026-09-26): « listen for it » and
    # « the business offers it » are two questions. One box served both, and
    # unticking it to shorten the transcription's list made the agent say the
    # business sold brands it does not (question 182).
    propose: bool = Field(
        default=False,
        description=(
            "Offered by the business: given to the agent as {{lexique_propose}}, "
            "the list it answers « do you offer X? » from."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _propose_sans_migration(cls, value):
        """⛔ No migration: a term saved before the second box existed reads it
        from ``a_ecouter`` -- it WAS that box -- so the screen and the agent show
        exactly what they showed before."""
        if isinstance(value, dict) and value.get("propose") is None:
            return {**value, "propose": bool(value.get("a_ecouter") or False)}
        return value

    @field_validator("terme", "prononciation", "categorie", mode="before")
    @classmethod
    def _nettoyer(cls, value):
        value = _texte_nettoye(value)
        return value

    @field_validator("prononciation", "categorie")
    @classmethod
    def _vide_a_none(cls, value):
        return value or None

    @field_validator("variantes", mode="before")
    @classmethod
    def _nettoyer_variantes(cls, value):
        if value is None:
            return []
        if isinstance(value, list):
            return [v for v in (_texte_nettoye(x) for x in value) if v != ""]
        return value

    @field_validator("variantes")
    @classmethod
    def _longueur_variantes(cls, value: list[str]):
        for variante in value:
            if len(variante) > MAX_LONGUEUR_TERME:
                raise ValueError(
                    f"The spelling « {variante[:30]}… » is longer than {MAX_LONGUEUR_TERME} characters."
                )
        return value

    @model_validator(mode="after")
    def _formes_lisibles(self):
        for forme in self.formes():
            if not normaliser_terme(forme):
                raise ValueError(f"« {forme} » has no letter or digit to recognise.")
        return self

    def formes(self) -> list[str]:
        """The term and its other spellings, as typed."""
        return [self.terme, *self.variantes]

    def formes_normalisees(self) -> set[str]:
        return {normaliser_terme(f) for f in self.formes()}


class ModeleImporte(BaseModel):
    """A template of the socle imported into this vocabulary."""

    nom: str = Field(min_length=1, max_length=MAX_LONGUEUR_NOM_MODELE)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")


class LexiqueMetier(BaseModel):
    """The whole vocabulary of an organization (and of a template file)."""

    format: Literal["lexique-mark"] = "lexique-mark"
    version: Literal[1] = 1
    modeles_importes: list[ModeleImporte] = Field(default_factory=list, max_length=MAX_MODELES_IMPORTES)
    termes: list[TermeLexique] = Field(default_factory=list, max_length=MAX_TERMES)

    @model_validator(mode="after")
    def _aucune_forme_partagee(self):
        """Two terms never share a spelling: the correction would not know which to write."""
        proprietaire: dict[str, int] = {}
        for rang, terme in enumerate(self.termes):
            for forme in terme.formes_normalisees():
                autre = proprietaire.get(forme)
                if autre is not None:
                    raise ValueError(
                        f"« {terme.terme} » and « {self.termes[autre].terme} » share the spelling "
                        f"« {forme} »: keep it on one of them only."
                    )
            for forme in terme.formes_normalisees():
                proprietaire[forme] = rang
        return self


class ResultatImport(BaseModel):
    ajoutes: int = Field(description="Terms added to the vocabulary.")
    deja_presents: int = Field(description="Terms left untouched: one of their spellings was already there.")
