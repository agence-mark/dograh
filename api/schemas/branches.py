"""[.mark] Partie 3, SA-L3b (05 § 12) : ce que les routes des branches reçoivent et rendent."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NouvelleBranche(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nom: str = Field(min_length=1, max_length=60, description="The branch name, unique for the agent.")
    depuis_version: int | None = Field(
        default=None, ge=1, description="The version number to start from (default: the agent's live version)."
    )
    protegee: bool = Field(default=False, description="A protected branch is entered only by a reviewed merge.")


class RepartitionDemandee(BaseModel):
    """Les parts de TOUTES les branches actives (total 100) ; la clé est l'identifiant de la branche."""

    model_config = ConfigDict(extra="forbid")

    parts: dict[int, int] = Field(description="Branch id -> share of the calls, whole numbers adding up to 100.")


class EpinglerLaPrincipale(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int | None = Field(default=None, ge=1, description="Version number to serve; none: follow the agent's live version.")


class ProtectionDemandee(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protegee: bool = Field(description="Protect the main branch (entered only by a reviewed merge) or lift the flag.")


class VersionDeBranche(BaseModel):
    id: int
    numero: int | None
    publiee_le: datetime | None = None


class BrouillonDeBranche(BaseModel):
    id: int
    numero: int | None
    a_moi: bool


class BrancheVue(BaseModel):
    id: int
    nom: str
    principale: bool
    protegee: bool
    protegee_par_defaut: bool = False
    part: int
    version_en_ligne: int | None
    versions: list[VersionDeBranche]
    brouillons: list[BrouillonDeBranche]


class BranchesVue(BaseModel):
    repartition_active: bool
    branches: list[BrancheVue]
