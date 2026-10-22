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
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator, model_validator

from api.schemas.lexique_metier import TermeLexique
from api.schemas.organization_preferences import AdresseEtablissement

MAX_ETABLISSEMENTS = 50
MAX_NUMEROS = 10
MAX_LONGUEUR_HORAIRES = 4000
MAX_LONGUEUR_ANNONCE = 300
MAX_TERMES_ETABLISSEMENT = 200
MAX_LONGUEUR_PHRASE = 1000

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
        description="Stable identifier, lower case, digits and hyphens (« site-nord »).",
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
    # [.mark] Chantier agents-specialises, lot 1 (F4, C5) : la fermeture immédiate de la
    # fiche, même forme que celle de l'organisation. Elle l'emporte pour les agents de
    # la fiche ; sinon celle de l'organisation (« tout fermer ») s'applique.
    etat_force: Literal["OUVERT", "PAUSE", "FERME", "SUR_RENDEZ_VOUS"] | None = Field(
        default=None,
        description=(
            "The state every agent of this fiche is in, whatever the hours say "
            "(OUVERT, PAUSE, FERME, SUR_RENDEZ_VOUS). None: the organization's, else the hours."
        ),
    )
    etat_force_jusqu_a: datetime | None = Field(
        default=None,
        description="When this fiche's forced state lifts itself, Paris time. None: until changed.",
    )

    phrases: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "This establishment's content for the sentences placed at the establishment's level "
            "(variable -> content). Absent: the organization's content."
        ),
    )
    termes_lexique: list[TermeLexique] = Field(
        default_factory=list,
        max_length=MAX_TERMES_ETABLISSEMENT,
        description="Terms this establishment adds to the organization's trade vocabulary (E6).",
    )

    @field_validator("phrases", mode="before")
    @classmethod
    def _phrases(cls, value):
        """Empty content = inherited: the key goes away."""
        if not isinstance(value, dict):
            return value
        propres = {}
        for cle, contenu in value.items():
            if isinstance(contenu, str) and contenu.strip():
                if len(contenu) > MAX_LONGUEUR_PHRASE:
                    raise ValueError(f"The sentence « {cle} » is longer than {MAX_LONGUEUR_PHRASE} characters.")
                propres[cle] = contenu.strip()
        return propres

    @field_validator("etat_force_jusqu_a")
    @classmethod
    def _fin_en_heure_de_paris(cls, value: datetime | None) -> datetime | None:
        """[.mark] Lot 1 : comme la fermeture de l'organisation, une heure de Paris sans décalage."""
        if value is None or value.tzinfo is None:
            return value
        return value.astimezone(ZoneInfo("Europe/Paris")).replace(tzinfo=None)

    @model_validator(mode="after")
    def _une_fin_suppose_une_fermeture(self):
        """[.mark] Lot 1 : une date de fin sans état forcé ne veut rien dire (refusée)."""
        if self.etat_force_jusqu_a is not None and self.etat_force is None:
            raise ValueError(
                "An end date means nothing without a forced state: choose a state, or clear the date."
            )
        return self

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


OrigineValeur = Literal["agent", "etablissement", "organisation", "aucune", "fiche"]


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
    # [.mark] Chantier agents-specialises, lot 1 (F1) : la fiche choisie par l'agent.
    fiche_de_lagent: str | None = Field(
        default=None,
        description=(
            "The fiche this agent chose (its establishment_id). Set: its calls read this "
            "fiche alone (no inheritance); the list then holds that fiche only."
        ),
    )
    fiche_introuvable: bool = Field(
        default=False,
        description="The chosen fiche no longer exists: the agent's calls read no establishment.",
    )
    # [.mark] Chantier agents-specialises, lot 11 (C4) : les numéros appartiennent à l'agent, la
    # fiche au lieu. L'écran les montre en lecture sous le choix de la fiche.
    numeros_de_lagent: list[str] = Field(
        default_factory=list,
        description="Every number of the organization's Telephony that leads to this agent (read only).",
    )


class NumeroDeLorganisation(BaseModel):
    """A Telephony number of the organization, for the establishment's choice list."""

    numero: str
    libelle: str | None = None
    agent: str | None = None


# --------------------------------------------------------------------------- #
# [.mark] Chantier agents-specialises, lot 4 (= lot 2 du plan fiche-etablissement)
# --------------------------------------------------------------------------- #


class DemandeCopieEtablissement(BaseModel):
    """F2: a new fiche made from an existing one."""

    source: str = Field(min_length=1, max_length=40, description="Identifier of the fiche to copy.")
    id: str = Field(min_length=1, max_length=40, description="Identifier of the new fiche.")
    nom: str = Field(min_length=1, max_length=100, description="Name of the new fiche.")


class ResultatCopieEtablissement(BaseModel):
    """What the copy made, and what it left for the person to fill."""

    etablissement: Etablissement
    reglages_rendez_vous_copies: bool = Field(
        default=False,
        description="The source's appointment settings and types were copied (needs a client database).",
    )
    types_rendez_vous_copies: int = 0
    non_copie: list[str] = Field(
        default_factory=list,
        description="What a copy never takes: numbers and the immediate closure (to fill on the new fiche).",
    )


class DemandeReprise(BaseModel):
    """The takeover of an organization's fiches and agents. Trial run unless ``ecrire``."""

    ecrire: bool = Field(
        default=False,
        description="False (default): lists what would be written, writes nothing. True: writes it.",
    )


class ActionReprise(BaseModel):
    """One value the takeover writes (or would write)."""

    sujet: Literal["fiche", "rendez_vous", "agent"]
    cible: str = Field(description="The fiche id or the agent's name and id.")
    champ: str
    avant: str | None = None
    apres: str | None = None


class ResultatReprise(BaseModel):
    ecrit: bool = Field(description="True when the changes were written; False for a trial run.")
    actions: list[ActionReprise] = Field(default_factory=list)
    a_decider: list[str] = Field(
        default_factory=list,
        description="What the takeover will not decide alone: an agent whose numbers lead to several "
        "fiches (or to none besides one), hours or address that disagree. Nothing was written for these.",
    )
    deja_a_jour: int = Field(default=0, description="Values already as the takeover would write them.")


# --------------------------------------------------------------------------- #
# [.mark] Lot F4 : l'écriture par élément (mise à jour partielle d'une fiche)
# --------------------------------------------------------------------------- #

_CHAMPS_MODIFIABLES = {
    nom: (
        champ.annotation | None,
        Field(default=None, description=champ.description),
    )
    for nom, champ in Etablissement.model_fields.items()
    if nom != "id"
}

ModificationEtablissement = create_model(
    "ModificationEtablissement",
    __config__=ConfigDict(extra="forbid"),
    __doc__=(
        "A partial update of ONE fiche: only the fields SENT change, the others stay as they are "
        "(an absent field is never read as « empty »). Every field of the fiche but its identifier. "
        "A field sent empty (``null``, ``\"\"``) goes back to inherited. ``phrases`` is merged "
        "sentence by sentence (a sentence sent empty is removed); ``numeros`` and "
        "``termes_lexique`` are replaced as a whole when sent. The same bounds as a save apply to "
        "what is sent."
    ),
    **_CHAMPS_MODIFIABLES,
)


class DemandeEtatFiche(BaseModel):
    """Close or reopen ONE fiche (the forced state), nothing else touched."""

    model_config = ConfigDict(extra="forbid")

    etat_force: Literal["OUVERT", "PAUSE", "FERME", "SUR_RENDEZ_VOUS"] | None = Field(
        description="The state to force (FERME to close). ``null``: reopen, back to the hours.",
    )
    etat_force_jusqu_a: datetime | None = Field(
        default=None,
        description="When the forced state lifts itself, Paris time. ``null``: until changed.",
    )
