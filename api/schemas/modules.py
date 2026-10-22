"""[.mark] Lot F8 : les modules de l'agent (D120 à D122, M1 à M8), tels que le fork les déclare.

Un module est une brique standard, sans vocabulaire métier (M1) : il dit ses BESOINS (M2), le traducteur
qui remplit chacun pour une organisation (M3), son interrupteur, ses réglages de construction (.mark) et
ses réglages terrain (le client, M5). La déclaration vit dans ``api/services/modules/registre.py`` ; ces
schémas sont ce que rendent ``GET /organizations/modules`` et ``GET /agents/{id}/modules`` au portail.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from api.schemas.objets_agent import AgentUtilisateur

# Les quatre blocs des réglages terrain du planificateur (D124) ; un autre module peut n'en avoir aucun.
BlocTerrain = Literal["quand", "quoi", "ou", "qui"]


class TexteModule(BaseModel):
    en: str
    fr: str


class TraducteurBranche(BaseModel):
    """The translator that fills a need for this organization (« se branche sur », M4)."""

    systeme: str
    libelle: str


class BesoinModule(BaseModel):
    """What a module needs (M2). ``domaine``: a translator domain (``agenda``, ``dossier``) filled by the
    organization's choice ; ``None``: a source of the fork itself, named by ``source_interne``.
    ``traducteur``: the translator chosen for the organization, ``None`` when none is."""

    code: str
    libelle: TexteModule
    domaine: str | None = None
    source_interne: TexteModule | None = None
    traducteur: TraducteurBranche | None = None


class ReglageModule(BaseModel):
    """One declared setting of a module: its key and where it lives (``workflow_configurations`` for an
    agent's key, a table of the client's database otherwise). ``bloc``: the terrain block (D124)."""

    cle: str
    lieu: str
    bloc: BlocTerrain | None = None
    modifiable: bool = True


class ModuleVue(BaseModel):
    code: str
    libelle: TexteModule
    # The agent's key that switches it on ; ``None``: on when a step carries one of its tools.
    interrupteur: str | None = None
    connecteurs: list[str] = []
    besoins: list[BesoinModule] = []
    reglages_construction: list[ReglageModule] = []
    reglages_terrain: list[ReglageModule] = []
    # The active agents of the organization on which it is on (their published version, D118).
    utilise_par: list[AgentUtilisateur] = []


class ModulesOrganisation(BaseModel):
    modules: list[ModuleVue]


class ModuleDeLAgent(ModuleVue):
    actif: bool = False


class ModulesAgent(BaseModel):
    agent_id: int
    modules: list[ModuleDeLAgent]
