"""[.mark] Partie 3, SA-L3d (décision 21) : ce que les routes des versions d'outils reçoivent et rendent."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PassageDeVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_uuid: str = Field(min_length=1, max_length=64, description="The tool to move to another version.")
    version: int = Field(ge=1, le=100000, description="The version number the agent's draft should play.")
    suivre_l_en_tete: bool = Field(
        default=False,
        description="True: write into the draft of the branch the request opened (the agent's own editor). False: into the branch "
        "named by branche_id (the tool's own window, which has no branch open).",
    )
    branche_id: int | None = Field(default=None, ge=1, description="The branch to write into; none: the main branch.")


class VersionDOutil(BaseModel):
    version: int
    nom: str
    cree_le: datetime | None = None
    courante: bool


class UsageDOutil(BaseModel):
    workflow_id: int
    agent: str
    branche: str
    branche_id: int | None = None
    version_agent: int | None = None
    version_outil: int | None = None
    en_ligne: bool
    brouillon: bool


class VersionsDUnOutil(BaseModel):
    tool_uuid: str
    nom: str
    courante: int
    versions: list[VersionDOutil]
    usage: list[UsageDOutil]
    agents_en_retard: int


class OutilDeLAgent(BaseModel):
    tool_uuid: str
    nom: str
    epinglee: int
    courante: int
    figee: bool


class OutilsDeLAgent(BaseModel):
    source: str | None = None
    outils: list[OutilDeLAgent]
