"""[.mark] Les formes échangées par les routes de copie d'agent (relevé, demande, compte rendu)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Sens = Literal["exporter", "ramener"]
TypeElement = Literal["agent", "outil", "document", "cle", "enregistrement", "etablissement"]
Action = Literal["copier", "relier", "vide"]


class ErreurCopie(Exception):
    """Un refus normal de la copie : le message est sûr à montrer, le code HTTP est celui de la route."""

    def __init__(self, message: str, statut: int = 422):
        super().__init__(message)
        self.statut = statut


class Cible(BaseModel):
    ref: str
    nom: str


class ElementReleve(BaseModel):
    type: TypeElement
    ref: str
    nom: str
    detail: str | None = None
    choix: list[Action]
    defaut: Action
    cibles: list[Cible] = Field(default_factory=list, description="Équivalents chez la cible, pour « relier »")
    cible_par_defaut: str | None = None
    code: str | None = Field(default=None, description="Code court que l'écran traduit (jamais une phrase)")


class DejaCopie(BaseModel):
    agent_id: int
    nom: str


class DossierPropose(BaseModel):
    id: int
    nom: str


class Releve(BaseModel):
    sens: Sens
    source_organization_id: int
    cible_organization_id: int
    agent_id: int
    agent_nom: str
    elements: list[ElementReleve]
    nb_tests: int
    deja_copie: DejaCopie | None = None
    # SE-9 (A-7) : pour « ramener », les dossiers du Labo où poser la copie (vide : « Copies de clients », créé au besoin).
    dossiers: list[DossierPropose] = Field(default_factory=list)


class ChoixElement(BaseModel):
    type: TypeElement
    ref: str = Field(max_length=200)
    action: Action
    cible: str | None = Field(default=None, max_length=200)


class DemandeCopie(BaseModel):
    sens: Sens
    cible_organization_id: int
    choix: list[ChoixElement] = Field(default_factory=list, max_length=500)
    avec_tests: bool = True
    # SE-9 (A-7) : pour « ramener », le nom de la copie (vide : « nom (client) ») et le dossier du Labo (vide : « Copies de clients »).
    nom: str | None = Field(default=None, max_length=200)
    dossier_id: int | None = None


class LigneCompte(BaseModel):
    type: TypeElement
    nom: str
    action: Action
    code: str | None = None


class AgentCopie(BaseModel):
    id: int
    nom: str


class CompteRendu(BaseModel):
    sens: Sens
    deja_copie: bool
    cible_organization_id: int
    agent_id: int
    agents: list[AgentCopie]
    dossier_id: int | None
    lignes: list[LigneCompte]
    tests_copies: int
    secrets_retires: int


class CibleProposee(BaseModel):
    id: int
    nom: str
    deja_copie: DejaCopie | None = None


class CiblesResponse(BaseModel):
    sens: Sens
    cibles: list[CibleProposee]
