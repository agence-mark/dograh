"""[.mark] The planner's rules (chantier l-agent-collegue, L5, P2, P3, P7, P8, P10).

Data of the CLIENT's database (migration 010; 013 adds ``fenetre_equite_jours``), edited on screen (theme « Appointments »), by hand
(``PUT /organizations/planificateur`` or a row of ``reglage_planificateur``) and later by the
client in Metabase.

- ``TypeRendezVous``: one kind of appointment. ``etablissement`` None = the organization's (the
  starting types of a new establishment, and the types of a call that serves no establishment);
  with an establishment = one of ITS types.
- ``ReglagesPlanificateur``: every field optional; None = the common default (``DEFAUTS``, the code's).
  The organization's row: the starting values of a new establishment, and the rules of a call that
  serves no establishment. Each establishment's row: its own complete rules.

[.mark] cloture-code, F-8 (Evan, 22/10): an establishment inherits NOTHING from the organization;
the organization's values are copied into a new establishment when it is created (migration 021,
``mark.preremplir_etablissement``), then each one lives its own life.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_CODE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_INSEE = re.compile(r"^[0-9][0-9AB][0-9]{3}$")

Repartition = Literal["premier_libre", "tour_de_role", "charge", "zone"]
Repli = Literal["humain_puis_rappel", "toujours_rappel"]
JoursFeries = Literal["metropole", "alsace_moselle"]


class TypeRendezVous(BaseModel):
    code: str
    etablissement: str | None = Field(
        default=None,
        description=(
            "Establishment it belongs to; None: the organization's (starting types of a new "
            "establishment, and the types of a call that serves no establishment)."
        ),
    )
    libelle: str = Field(min_length=1, max_length=100)
    duree_min: int = Field(ge=5, le=1440, description="Length of the appointment, in minutes.")
    sujet: str | None = Field(
        default=None,
        description="Code of the subject whose people do it (« Team and routing »); None: the whole team.",
    )
    marge_avant_min: int = Field(default=0, ge=0, le=480)
    marge_apres_min: int = Field(default=0, ge=0, le=480)
    actif: bool = True

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if not _CODE.match(value):
            raise ValueError("A code takes lower case letters, digits and underscores.")
        return value


class ReglagesPlanificateur(BaseModel):
    nombre_creneaux: int | None = Field(default=None, ge=1, le=6)
    delai_minimal_h: float | None = Field(default=None, ge=0, le=720)
    horizon_jours: int | None = Field(default=None, ge=1, le=90)
    pas_min: int | None = Field(default=None, ge=5, le=240)
    plages: str | None = Field(
        default=None,
        max_length=4000,
        description="Booking ranges in the readable hours format; None: the establishment's hours.",
    )
    zone_rayon_km: float | None = Field(default=None, ge=1, le=1000)
    zone_communes: list[str] | None = Field(default=None, max_length=500)
    trajets_comptes: bool | None = None
    coefficient_trajet: float | None = Field(default=None, ge=1, le=3)
    vitesse_kmh: float | None = Field(default=None, ge=5, le=130)
    repartition: Repartition | None = None
    repli: Repli | None = None
    personne_visible: bool | None = None
    jours_feries: JoursFeries | None = None
    fenetre_equite_jours: int | None = Field(
        default=None,
        ge=1,
        le=365,
        description="Days over which « tour_de_role » counts the appointments given (R-7, migration 013).",
    )

    @field_validator("plages")
    @classmethod
    def _plages(cls, value):
        texte = (value or "").strip()
        return texte or None

    @field_validator("zone_communes")
    @classmethod
    def _communes(cls, value):
        if value is None:
            return None
        codes = [str(c).strip().upper() for c in value if str(c).strip()]
        for code in codes:
            if not _INSEE.match(code):
                raise ValueError(f"« {code} » is not an INSEE code of a commune.")
        return codes or None


# The common defaults (G2): set by the code, a new client starts with them.
DEFAUTS = ReglagesPlanificateur(
    nombre_creneaux=3,
    delai_minimal_h=24,
    horizon_jours=14,
    pas_min=30,
    plages=None,
    zone_rayon_km=None,
    zone_communes=None,
    trajets_comptes=False,
    coefficient_trajet=1.3,
    vitesse_kmh=50,
    repartition="premier_libre",
    repli="humain_puis_rappel",
    personne_visible=False,
    jours_feries="metropole",
    fenetre_equite_jours=30,
)


def effectifs(*niveaux: ReglagesPlanificateur | None) -> ReglagesPlanificateur:
    """The defaults, then each level in order: the last value set wins.

    [.mark] F-8: a call passes ONE level (the establishment served, or the organization when it
    serves none); never the organization under an establishment."""
    valeurs = DEFAUTS.model_dump()
    for niveau in niveaux:
        if niveau is None:
            continue
        for cle, valeur in niveau.model_dump().items():
            if valeur is not None:
                valeurs[cle] = valeur
    return ReglagesPlanificateur.model_validate(valeurs)


class Planificateur(BaseModel):
    """What the theme « Appointments » shows and saves."""

    reglages: ReglagesPlanificateur = Field(default_factory=ReglagesPlanificateur)
    par_etablissement: dict[str, ReglagesPlanificateur] = Field(
        default_factory=dict, description="Establishment id -> its own complete rules (empty: the default)."
    )
    types: list[TypeRendezVous] = Field(default_factory=list, max_length=100)
    defauts: ReglagesPlanificateur = Field(
        default_factory=lambda: DEFAUTS.model_copy(),
        description="The common defaults (read only, shown as placeholders).",
    )

    @model_validator(mode="after")
    def _types_uniques(self):
        vus = set()
        for t in self.types:
            cle = (t.code, t.etablissement)
            if cle in vus:
                raise ValueError(f"The appointment type « {t.code} » is declared twice at the same level.")
            vus.add(cle)
        return self


# --------------------------------------------------------------------------- #
# [.mark] Lot F4 : l'écriture par élément (mise à jour partielle)
# --------------------------------------------------------------------------- #


class CleTypeRendezVous(BaseModel):
    """Which appointment type: its code, and the establishment it is proper to (None: the organization's)."""

    model_config = ConfigDict(extra="forbid")

    code: str
    etablissement: str | None = None


class ReglagesEnvoyes(ReglagesPlanificateur):
    """The settings of a partial update: the same fields and bounds, a misspelt setting is refused."""

    model_config = ConfigDict(extra="forbid")


class ModificationPlanificateur(BaseModel):
    """A partial update of the planner, ONE level at a time.

    ``etablissement`` None: the organization's settings (starting values); an establishment id: that
    establishment's own. Inside ``reglages`` only the settings SENT change (an absent one keeps its value;
    one sent ``null`` goes back to the common default). ``types`` creates or replaces the types listed, ``types_retires``
    removes the ones named; every other type, and every other level, stays as it is."""

    model_config = ConfigDict(extra="forbid")

    etablissement: str | None = Field(
        default=None, description="The establishment whose rules change; None: the organization's (starting values)."
    )
    reglages: ReglagesEnvoyes = Field(
        default_factory=ReglagesEnvoyes,
        description="Only the settings sent are written.",
    )
    types: list[TypeRendezVous] = Field(default_factory=list, max_length=100)
    types_retires: list[CleTypeRendezVous] = Field(default_factory=list, max_length=100)
