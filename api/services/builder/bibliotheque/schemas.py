"""[.mark] Bibliothèque : la forme du contenu d'un élément, par famille (E49).

Une famille dont un mécanisme LIT le contenu a ses champs fixés ici et validés à l'écriture : un contenu hors schéma est
refusé avec la raison. Une famille créée à l'écran ne porte que ``{"texte": ...}``. Les autres familles du code gardent un
objet libre (le code ne connaît pas leur métier).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from api.services.builder.bibliotheque.familles import FAMILLES


class _Forme(BaseModel):
    # Ce qu'un mécanisme ne lit pas peut accompagner le contenu (licence, notes) : pas de refus des champs en plus.
    model_config = ConfigDict(extra="allow")


class Personnage(_Forme):
    description: str = Field(min_length=1, max_length=1500)
    but: str = Field(default="", max_length=1000)
    fin: str = Field(default="", max_length=600)
    comportements: list[str] = Field(default_factory=list, max_length=12)


class ScenarioType(_Forme):
    but: str = Field(min_length=1, max_length=2000)
    personnage: str | None = Field(default=None, max_length=64)
    ouverture: str = Field(default="", max_length=500)
    tours_max: int | None = Field(default=None, ge=1, le=60)
    criteres: list[dict[str, Any]] = Field(default_factory=list, max_length=12)
    questions_juge: list[str] = Field(default_factory=list, max_length=5)


class CritereType(_Forme):
    critere: dict[str, Any]
    explication: str = Field(default="", max_length=600)

    @field_validator("critere")
    @classmethod
    def _type(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not str(v.get("type") or "").strip():
            raise ValueError("a criterion has a type")
        return v


class PhrasesDuCode(_Forme):
    regles: list[dict[str, Any]] = Field(min_length=1, max_length=40)


class Lexique(_Forme):
    termes: list[dict[str, Any]] = Field(min_length=1, max_length=400)


class ModeleDeReglages(_Forme):
    valeurs: dict[str, Any] = Field(min_length=1)


class Texte(_Forme):
    texte: str = Field(min_length=1)


SCHEMAS: dict[str, type[BaseModel]] = {
    "personnages-appelant": Personnage,
    "scenarios-test": ScenarioType,
    "criteres-types": CritereType,
    "phrases-du-code": PhrasesDuCode,
    "lexiques": Lexique,
    "modeles-reglages": ModeleDeReglages,
}


def verifier(famille: str, contenu: dict[str, Any]) -> dict[str, Any]:
    """Le contenu tel quel s'il respecte la forme de sa famille ; ``ValueError`` avec la raison sinon."""
    forme = SCHEMAS.get(famille)
    if forme is None and famille not in FAMILLES:
        forme = Texte  # famille créée à l'écran
    if forme is None:
        return contenu
    try:
        forme.model_validate(contenu)
    except ValidationError as erreur:
        premier = erreur.errors()[0]
        champ = ".".join(str(p) for p in premier.get("loc", ())) or "content"
        raise ValueError(f"{famille}: field « {champ} » {premier.get('msg', 'is invalid')}.") from None
    return contenu
