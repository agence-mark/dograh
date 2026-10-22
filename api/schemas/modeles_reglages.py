"""[.mark] Settings templates (chantier cloture-code-avant-migration, lot 5; plan modeles-de-reglages, M1 to M11).

A template freezes, under a name, the settings of an agent that are *behaviour* (not the client's data,
not a prompt, never a key) so that another agent receives them in one gesture. Applying is a COPY (M4):
changing or deleting a template changes no agent already set.

Stored as one row of ``organization_configurations`` under ``MODELES_REGLAGES`` (no migration): the
templates of the organization and, per agent, the mention of the last template applied (M4). A template
is never read from another organization (M1); the file exported from one organization and imported into
another is the only way a template travels.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

FORMAT_DU_FICHIER = "modele-de-reglages-mark"
VERSION_DU_FORMAT = 1
MAX_MODELES = 100
MAX_LONGUEUR_NOM = 80
# A template holds behaviour settings, a few kilobytes: past this, the file is not one of ours.
MAX_OCTETS_DES_VALEURS = 200_000


def _nom_valide(valeur: str) -> str:
    nom = (valeur or "").strip()
    if not nom:
        raise ValueError("The name of a template cannot be empty.")
    if len(nom) > MAX_LONGUEUR_NOM:
        raise ValueError(f"The name of a template holds {MAX_LONGUEUR_NOM} characters at most.")
    return nom


class OrigineDuModele(BaseModel):
    """Where a template was frozen from (M7): the agent and the version it was read on."""

    workflow_id: int | None = None
    agent_nom: str | None = None
    version_number: int | None = None
    version_status: str | None = Field(default=None, description="draft or published.")


class ModeleDeReglages(BaseModel):
    id: str
    nom: str
    cree_le: datetime
    origine: OrigineDuModele | None = None
    commit: str | None = Field(default=None, description="The commit of the fork that produced it, when known.")
    sections: list[str] = Field(default_factory=list, description="The sections that hold at least one setting.")
    valeurs: dict[str, Any] = Field(default_factory=dict)


class MentionApplication(BaseModel):
    """What an agent keeps of the last template applied to it (M4): a copy of the name, never a link."""

    modele_id: str | None = None
    nom: str
    applique_le: datetime
    sections: list[str] = Field(default_factory=list)


class StockModeles(BaseModel):
    version: int = 1
    modeles: list[ModeleDeReglages] = Field(default_factory=list)
    # Keyed by the agent's id (a string: JSON keys are strings).
    applications: dict[str, MentionApplication] = Field(default_factory=dict)


class ResumeDuModele(BaseModel):
    id: str
    nom: str
    cree_le: datetime
    origine: OrigineDuModele | None = None
    sections: list[str]
    nombre_de_reglages: int


class ListeDesModeles(BaseModel):
    modeles: list[ResumeDuModele]
    sections: list[str] = Field(description="Every section a template can be applied by, in screen order.")


class DemandeCreation(BaseModel):
    nom: str
    workflow_id: int = Field(description="The agent whose active settings are frozen.")

    @field_validator("nom")
    @classmethod
    def _verifier_le_nom(cls, valeur: str) -> str:
        return _nom_valide(valeur)


class DemandeRenommer(BaseModel):
    nom: str

    @field_validator("nom")
    @classmethod
    def _verifier_le_nom(cls, valeur: str) -> str:
        return _nom_valide(valeur)


class DemandeApplication(BaseModel):
    workflow_id: int
    sections: list[str] = Field(description="The sections to take. Every section is ticked by default on screen.")
    a_blanc: bool = Field(
        default=False,
        description="True: say what would happen (including the providers with no key) and write nothing.",
    )


class ReglageNonApplique(BaseModel):
    cle: str
    raison: str = Field(description="cle-manquante | invalide.")
    detail: str | None = None


class ResultatApplication(BaseModel):
    ecrit: bool
    sections: list[str]
    posees: list[str] = Field(description="Settings that now hold the template's value.")
    retirees: list[str] = Field(description="Settings the template does not set: back to their default.")
    non_appliquees: list[ReglageNonApplique]
    fournisseurs_sans_cle: list[str] = Field(
        description="Providers the template brings for which the agent and its organization have no key."
    )


class FichierDeModele(BaseModel):
    """The exported file. No key, no reference to a key, ever (M3)."""

    format: str = FORMAT_DU_FICHIER
    version_du_format: int = VERSION_DU_FORMAT
    commit: str | None = None
    nom: str
    cree_le: datetime | None = None
    origine: OrigineDuModele | None = None
    valeurs: dict[str, Any]

    @field_validator("nom")
    @classmethod
    def _verifier_le_nom(cls, valeur: str) -> str:
        return _nom_valide(valeur)


class MentionDeLagent(BaseModel):
    mention: MentionApplication | None = None
