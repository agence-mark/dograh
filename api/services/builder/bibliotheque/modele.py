"""[.mark] Bibliothèque : les formes d'un élément, d'une version, d'une proposition (pur, sans base)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from api.services.builder.constantes import CONTENU_MAX_OCTETS


class Statut(str, Enum):
    CANDIDAT = "candidat"  # non prouvé
    RECETTE = "recette"  # prouvée au banc, passée par un clic humain
    REJETE = "rejete"  # gardé avec la raison


def maintenant() -> datetime:
    return datetime.now(UTC)


class Banc(BaseModel):
    """Ce qui prouve une version : un texte court et, si on l'a, la référence du banc."""

    description: str = Field(min_length=1, max_length=500)
    reference: str | None = Field(default=None, max_length=200)
    date: datetime = Field(default_factory=maintenant)


class Origine(BaseModel):
    """D'où vient une importation (B35) : source, licence (ou « inconnue »), date."""

    source: str = Field(min_length=1, max_length=500)
    licence: str = Field(min_length=1, max_length=100)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


def verifier_contenu(contenu: Any) -> dict[str, Any]:
    if not isinstance(contenu, dict):
        raise ValueError("The content of an element is a JSON object.")
    taille = len(json.dumps(contenu, ensure_ascii=False).encode("utf-8"))
    if taille > CONTENU_MAX_OCTETS:
        raise ValueError(f"Content too large: {taille} bytes, at most {CONTENU_MAX_OCTETS}.")
    return contenu


class Version(BaseModel):
    numero: int = Field(ge=1)
    auteur: str = Field(min_length=1, max_length=200)
    date: datetime = Field(default_factory=maintenant)
    notes: str = Field(default="", max_length=2000)
    statut: Statut = Statut.CANDIDAT
    raison_rejet: str | None = Field(default=None, max_length=1000)
    banc: Banc | None = None
    origine: Origine | None = None
    # Numéro de la version dont celle-ci est la restauration (retour arrière).
    restaure_de: int | None = None
    contenu: dict[str, Any]

    @field_validator("contenu")
    @classmethod
    def _contenu(cls, valeur: Any) -> dict[str, Any]:
        return verifier_contenu(valeur)


class Element(BaseModel):
    famille: str
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    titre: str = Field(min_length=1, max_length=200)
    version_courante: int = Field(ge=1)
    versions: list[Version] = Field(min_length=1)

    @property
    def courante(self) -> Version:
        return next(v for v in self.versions if v.numero == self.version_courante)

    @property
    def statut(self) -> Statut:
        return self.courante.statut


class Resume(BaseModel):
    """Une ligne de la liste : jamais le contenu entier."""

    famille: str
    slug: str
    titre: str
    statut: Statut
    version_courante: int
    auteur: str
    date: datetime
    banc: Banc | None
    origine: Origine | None
    utilisee_par: int = 0


class Proposition(BaseModel):
    id: str
    type: Literal["version", "passage_recette", "rejet"]
    famille: str
    slug: str
    titre: str = Field(default="", max_length=200)
    contenu: dict[str, Any] | None = None
    # passage_recette / rejet : la version visée.
    version: int | None = None
    justification: str = Field(min_length=1, max_length=2000)
    banc: Banc | None = None
    auteur: str
    date: datetime = Field(default_factory=maintenant)
    etat: Literal["en_attente", "acceptee", "refusee"] = "en_attente"
    decide_par: str | None = None
    decide_le: datetime | None = None
    motif_refus: str | None = None

    @field_validator("contenu")
    @classmethod
    def _contenu(cls, valeur: Any) -> Any:
        return None if valeur is None else verifier_contenu(valeur)
