"""[.mark] Lot F3 : les cases des listes de valeurs de la base du client.

Une valeur de liste (``liste_valeur``) porte trois cases que la migration 015 a ajoutées et que personne ne
coche dans le code : « compte comme réglé seul » (une issue d'appel), « opportunité » (un motif),
« urgent » (un degré d'urgence). Les indicateurs du portail les lisent. Elles se cochent ici, sur une route,
avec l'auteur réel au journal.

Dograh n'y décide de rien : n'importe quelle case peut être posée sur n'importe quelle valeur existante
(``CASES_PAR_LISTE`` ne sert qu'à dire à l'écran quelle colonne montrer pour quelle liste).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Case = Literal["regle_seul", "opportunite", "urgent"]

# Les listes que les indicateurs lisent (identifiants techniques de la base, voir `v_portail_kpi` et
# `v_portail_motifs`) et la case que chacune porte. Une liste absente de la base est rendue vide.
CASES_PAR_LISTE: dict[str, tuple[Case, ...]] = {
    "issue_appel": ("regle_seul",),
    "motif_appel": ("opportunite",),
    "degre_urgence": ("urgent",),
}


class ValeurDeListe(BaseModel):
    code: str
    libelle: str
    ordre: int = 0
    actif: bool = True
    regle_seul: bool = False
    opportunite: bool = False
    urgent: bool = False


class ListeDeValeurs(BaseModel):
    liste: str = Field(description="Technical name of the list, as the database holds it.")
    cases: list[Case] = Field(description="The boxes this list carries (the ones the screen shows).")
    valeurs: list[ValeurDeListe] = Field(default_factory=list)


class ListesValeurs(BaseModel):
    listes: list[ListeDeValeurs] = Field(default_factory=list)


class CasesDUneValeur(BaseModel):
    """The boxes to set on ONE value. A box left out keeps its state."""

    model_config = ConfigDict(extra="forbid")

    liste: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=100)
    regle_seul: bool | None = None
    opportunite: bool | None = None
    urgent: bool | None = None


class ModificationListesValeurs(BaseModel):
    """Only the values named change, and only the boxes sent on each. An unknown value refuses the whole request."""

    model_config = ConfigDict(extra="forbid")

    valeurs: list[CasesDUneValeur] = Field(default_factory=list, max_length=500)
