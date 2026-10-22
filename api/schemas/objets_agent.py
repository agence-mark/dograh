"""[.mark] Lot F7 : les objets de l'agent (D106 à D119), dans la base du client (migration 019).

Un objet est une donnée métier que l'agent reçoit en ``{{nom}}`` et que le client tient à jour : une
VALEUR simple (un type, une valeur) ou une LISTE (des colonnes typées, des lignes), un tableur miniature.
Aucun vocabulaire métier ici : les noms, les libellés, les descriptions et les valeurs sont des données.

Dans l'API, les cellules d'une ligne sont rangées par LIBELLÉ de colonne (unique dans un objet) : une
colonne créée dans la même demande n'a pas encore d'identifiant. La base, elle, les range par identifiant.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TypeObjet = Literal["texte", "nombre", "montant", "oui_non", "date"]
FormeObjet = Literal["valeur", "liste"]
PosePar = Literal["mark", "client"]

# Le nom technique, celui des prompts : le même motif que la contrainte SQL de la 019.
MOTIF_NOM = r"^[a-z][a-z0-9_]{0,62}$"
PLAFOND_PAR_DEFAUT = 3000


class ColonneObjet(BaseModel):
    """A column of a list. ``id`` absent: a new column. ``pose_par`` = who set it (D108)."""

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    libelle: str = Field(min_length=1, max_length=100)
    type: TypeObjet = "texte"
    ordre: int = 0
    pose_par: PosePar = "mark"


class LigneObjet(BaseModel):
    """A line of a list: its cells, by column label. ``id`` absent: a new line."""

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    ordre: int = 0
    valeurs: dict[str, str] = Field(default_factory=dict)


class AgentUtilisateur(BaseModel):
    id: int
    nom: str


class ObjetEnvoye(BaseModel):
    """An object as .mark creates or rewrites it (the whole object; the others are untouched).
    ``etablissement``: the fiche's identifier (D110), absent = all establishments."""

    model_config = ConfigDict(extra="forbid")

    nom: str = Field(pattern=MOTIF_NOM)
    libelle: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    forme: FormeObjet
    type: TypeObjet | None = None
    valeur: str | None = None
    etablissement: str | None = None
    colonnes: list[ColonneObjet] = Field(default_factory=list, max_length=50)
    lignes: list[LigneObjet] = Field(default_factory=list, max_length=2000)


class ObjetAgent(ObjetEnvoye):
    """An object as the client's database holds it, with its rendering's size and its readers."""

    model_config = ConfigDict(extra="ignore")

    id: int
    modifie_le: datetime | None = None
    taille: int = Field(default=0, description="Characters of the text the agent receives (D112).")
    utilise_par: list[AgentUtilisateur] = Field(
        default_factory=list, description="Agents whose published texts hold {{nom}} (D118), computed."
    )


class ReglagesObjets(BaseModel):
    """The organization's ceiling on one object's rendering (D112), adjusted at the bench."""

    model_config = ConfigDict(extra="forbid")

    plafond_caracteres: int = Field(default=PLAFOND_PAR_DEFAUT, ge=100, le=50000)


class ObjetsAgent(BaseModel):
    objets: list[ObjetAgent] = Field(default_factory=list)
    plafond_caracteres: int = PLAFOND_PAR_DEFAUT


class UtilisationObjets(BaseModel):
    """``{{nom}}`` looked for in every agent's published texts, at the time of asking (D118)."""

    utilisation: dict[str, list[AgentUtilisateur]] = Field(default_factory=dict)
