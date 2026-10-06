"""[.mark] The establishments of an organization, and what each one overrides.

Chantier ``l-agent-travaille`` (L1, 06/10/2026), decisions E1 to E4:

- E1: one Dograh organization = one client (one company). Its establishments
  (shops, sites, agencies) live inside it.
- E2: inheritance on three levels, organization -> establishment -> agent; the
  most precise value wins. Here, ``None`` on a field means « inherited ».
- E3: the establishment of a call is found from the CALLED number: each number
  of the organization's Telephony belongs to at most one establishment. An
  establishment may have no number yet (« to attach »).
- E4: the opening hours, the address and the announcement come down to the
  establishment. An agent whose calls match no establishment behaves exactly as
  before (zero loss).

Stored as one row of ``organization_configurations`` under ``ETABLISSEMENTS``:
a free-text key of an existing table, so no migration (rule B7 of the fork).

⛔ Same two sides as the hours and the address: the bounds below are the FORMAT,
checked whenever the model is read. That the hours parse, that the commune
exists at that postal code and that a called number is one of the
organization's own is checked by the SAVE route only: a refusal must never cost
a call.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from api.schemas.organization_preferences import AdresseEtablissement

MAX_ETABLISSEMENTS = 50
MAX_NUMEROS = 10
MAX_LONGUEUR_HORAIRES = 4000
MAX_LONGUEUR_ANNONCE = 300

# E.164: a plus sign and 8 to 15 digits. The screen offers the organization's
# own numbers; the second number and the transfer number are typed.
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


def _numero(valeur: str | None) -> str | None:
    if valeur is None:
        return None
    texte = re.sub(r"[\s.\-()]", "", str(valeur))
    if not texte:
        return None
    if not _E164.match(texte):
        raise ValueError(f"« {valeur} » is not a phone number in international format (+33…).")
    return texte


class Etablissement(BaseModel):
    """One establishment. Every optional field left empty is inherited."""

    id: str = Field(
        description="Stable identifier, lower case, digits and hyphens (« saint-maximin »).",
        min_length=1,
        max_length=40,
    )
    nom: str = Field(min_length=1, max_length=100, description="Name, as the team says it.")
    numeros: list[str] = Field(
        default_factory=list,
        max_length=MAX_NUMEROS,
        description=(
            "The numbers callers dial to reach this establishment, chosen among the "
            "organization's Telephony numbers. Empty: the establishment is not attached yet."
        ),
    )
    second_numero: str | None = Field(
        default=None,
        description="The number reached when the agent cannot answer (outage, chantier panne).",
    )
    numero_transfert: str | None = Field(
        default=None,
        description="Given to the agents as {{numero_transfert}}, for the transfer tool's destination.",
    )
    adresse: AdresseEtablissement | None = Field(
        default=None, description="None: the organization's address."
    )
    horaires_ouverture: str | None = Field(
        default=None,
        max_length=MAX_LONGUEUR_HORAIRES,
        description=(
            "Opening hours, readable format, closures as dated lines « 24/12/2026 : fermé ». "
            "None: the agent's own hours, if any."
        ),
    )
    annonce_fermeture: str | None = Field(
        default=None,
        max_length=MAX_LONGUEUR_ANNONCE,
        description="None: the organization's closing announcement.",
    )
    annonce_pause: str | None = Field(
        default=None,
        max_length=MAX_LONGUEUR_ANNONCE,
        description="None: the organization's break announcement.",
    )

    @field_validator("id")
    @classmethod
    def _identifiant(cls, value: str) -> str:
        if not _ID.match(value):
            raise ValueError("The identifier takes lower case letters, digits and hyphens only.")
        return value

    @field_validator("nom", mode="before")
    @classmethod
    def _nom_propre(cls, value):
        return re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else value

    @field_validator("numeros", mode="before")
    @classmethod
    def _numeros(cls, value):
        if not isinstance(value, list):
            return value
        vus: list[str] = []
        for brut in value:
            numero = _numero(brut)
            if numero and numero not in vus:
                vus.append(numero)
        return vus

    @field_validator("second_numero", "numero_transfert", mode="before")
    @classmethod
    def _numero_unique(cls, value):
        return _numero(value) if isinstance(value, str) or value is None else value

    @field_validator("horaires_ouverture", "annonce_fermeture", "annonce_pause", mode="before")
    @classmethod
    def _vide_a_none(cls, value):
        """An empty text is « inherited », never « nothing »: the screen clears a
        field to go back to the organization's value."""
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("annonce_fermeture", "annonce_pause")
    @classmethod
    def _modele_lisible(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from api.schemas.annonce_ouverture import verifier_modele_annonce

        return verifier_modele_annonce(re.sub(r"[ \t]+", " ", value))


class CatalogueEtablissements(BaseModel):
    """All the establishments of one organization, in the order of the screen."""

    format: Literal["etablissements-mark"] = "etablissements-mark"
    version: Literal[1] = 1
    etablissements: list[Etablissement] = Field(default_factory=list, max_length=MAX_ETABLISSEMENTS)

    @model_validator(mode="after")
    def _uniques(self):
        ids: set[str] = set()
        numeros: dict[str, str] = {}
        for etablissement in self.etablissements:
            if etablissement.id in ids:
                raise ValueError(f"Two establishments share the identifier « {etablissement.id} ».")
            ids.add(etablissement.id)
            for numero in etablissement.numeros:
                if numero in numeros:
                    raise ValueError(
                        f"{numero} belongs to « {numeros[numero]} » and « {etablissement.nom} »: "
                        "a called number leads to one establishment only."
                    )
                numeros[numero] = etablissement.nom
        return self


OrigineValeur = Literal["agent", "etablissement", "organisation", "aucune"]


class ValeurHeritee(BaseModel):
    """A value as the call will read it, and the level it comes from."""

    valeur: str | None = None
    origine: OrigineValeur = "aucune"


class EtablissementServi(BaseModel):
    """What the agent's screen shows: an establishment it serves, values resolved."""

    id: str
    nom: str
    numeros: list[str]
    horaires_ouverture: ValeurHeritee
    adresse: ValeurHeritee
    annonce_fermeture: ValeurHeritee
    annonce_pause: ValeurHeritee
    numero_transfert: ValeurHeritee


class EtablissementsDeLagent(BaseModel):
    """The establishments an agent serves through its numbers (E3)."""

    etablissements: list[EtablissementServi] = Field(default_factory=list)
    numeros_sans_etablissement: list[str] = Field(
        default_factory=list,
        description="Numbers of this agent attached to no establishment: their calls behave as before.",
    )


class NumeroDeLorganisation(BaseModel):
    """A Telephony number of the organization, for the establishment's choice list."""

    numero: str
    libelle: str | None = None
    agent: str | None = None
