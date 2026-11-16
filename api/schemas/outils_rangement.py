"""[.mark] Lot 11 du chantier module : les formes des routes de rangement des outils (dossiers) et des kits d'outils."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


def _nom(valeur: str) -> str:
    valeur = valeur.strip()
    if not valeur:
        raise ValueError("The name cannot be empty")
    return valeur


class DossierOutilsReponse(BaseModel):
    id: int
    name: str
    parent_id: int | None = None
    created_at: datetime | None = None
    tool_count: int = 0


class DossierOutilsCreation(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: int | None = None

    _n = field_validator("name")(_nom)


class DossierOutilsRenommer(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    _n = field_validator("name")(_nom)


class DossierOutilsDeplacer(BaseModel):
    parent_id: int | None = None


class RangerUnOutil(BaseModel):
    """``dossier_id`` ``None`` : l'outil sort de son dossier."""

    dossier_id: int | None = None


class OutilDeKit(BaseModel):
    id: int
    name: str
    description: str | None = None
    category: str
    icon: str | None = None
    icon_color: str | None = None
    definition: dict[str, Any]
    version: int


class KitReponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    items: list[OutilDeKit] = Field(default_factory=list)


class KitCreation(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)

    _n = field_validator("name")(_nom)


class KitModification(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def _n(cls, v):
        return _nom(v) if v is not None else v


class AjouterUnOutilAuKit(BaseModel):
    """Depuis la ligne d'un outil : le kit en prend une copie sans ce qui appartient à l'organisation."""

    tool_uuid: str = Field(min_length=1, max_length=64)


class ModifierUnOutilDuKit(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    definition: dict[str, Any] | None = None


class AppliquerUnKit(BaseModel):
    dossier_id: int | None = None


class ApplicationDuKit(BaseModel):
    kit_id: int
    crees: list[str]
    deja_presents: int


class PropositionDeKit(BaseModel):
    tool_uuid: str
    tool_name: str
    kit_id: int
    kit_name: str
    version_recue: int
    version_du_kit: int


class AgentDuKit(BaseModel):
    """Un agent de l'organisation qui porte au moins un outil reçu du kit : sa version la plus ancienne reçue et celle du kit (la plus haute)."""

    agent_id: int
    agent: str
    outils: int
    version_recue: int
    version_du_kit: int
    a_jour: bool


class AccepterUneProposition(BaseModel):
    tool_uuid: str = Field(min_length=1, max_length=64)
