"""[.mark] The client's database on screen: its attachment, its state, its team (L3).

- ``RattachementBaseClient``: the NAME of the database (B4). Stored in
  ``organization_configurations`` under ``BASE_CLIENT``; the server, user and password
  are the installation's (environment variable), never here.
- ``EtatBaseClient``: what the « Client data » theme shows.
- ``Equipe``: the people and the routing (subject -> people), written in the client's
  database (B2), read by the after-call (L4).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_CLE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_CODE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_SYSTEME = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


class RattachementBaseClient(BaseModel):
    format: Literal["base-client-mark"] = "base-client-mark"
    version: Literal[1] = 1
    nom_base: str | None = Field(
        default=None,
        description="Name of the database on the clients' Postgres. None: not attached.",
    )
    rattachee_le: datetime | None = None


class DemandeRattachement(BaseModel):
    nom_base: str | None = Field(default=None, max_length=63)


class Conservation(BaseModel):
    table_nom: str
    duree_jours: int = Field(ge=1, le=3650)
    colonne_date: str | None = None
    source: str | None = None


class EtatBaseClient(BaseModel):
    serveur_configure: bool
    nom_base: str | None = None
    joignable: bool = False
    erreur: str | None = None
    version: int | None = None
    version_attendue: int
    a_mettre_a_niveau: bool = Field(
        default=False,
        description="The connection account has no rights in this database yet: « Upgrade » gives them.",
    )
    derniere_ecriture: datetime | None = None
    conservation: list[Conservation] = Field(default_factory=list)
    refus: list[str] = Field(
        default_factory=list,
        description="Values written in the database that Dograh refused.",
    )


class Personne(BaseModel):
    cle: str = Field(description="Stable identifier (lower case, digits, hyphens).")
    prenom: str = Field(min_length=1, max_length=100)
    nom: str | None = Field(default=None, max_length=100)
    role: str | None = Field(default=None, max_length=100)
    mail: str | None = Field(default=None, max_length=200)
    telephone: str | None = Field(default=None, max_length=20)
    etablissement: str | None = Field(
        default=None,
        description="Identifier of its establishment; None: the whole company.",
    )
    destinataire_defaut: bool = False
    actif: bool = True
    # [.mark] l-agent-collegue, L1 (C1): what the agent knows of this person during a call.
    description: str | None = Field(
        default=None,
        max_length=300,
        description="What this person takes care of, in plain words (the agent reads it).",
    )
    divulguer_telephone: bool = Field(
        default=False,
        description="The agent may give this person's phone number to a caller.",
    )
    divulguer_mail: bool = Field(
        default=False,
        description="The agent may give this person's e-mail address to a caller.",
    )
    joignable_par_transfert: bool = Field(
        default=False,
        description="The agent may transfer a call to this person (a phone number is needed).",
    )
    # [.mark] l-agent-collegue, L4 (H7): this person's agenda in each calendar software
    # (translator name -> the software's identifier of her agenda). Kept in ``lien_externe``
    # (objet_type = personne). None on a save: left as it is.
    agendas: dict[str, str] | None = Field(
        default=None,
        description="Her agenda in each calendar software: translator -> agenda identifier.",
    )

    @field_validator("agendas")
    @classmethod
    def _agendas(cls, value):
        if value is None:
            return None
        propres = {}
        for systeme, agenda in dict(value).items():
            if not _SYSTEME.match(str(systeme)):
                raise ValueError(f"« {systeme} » is not a translator's name.")
            texte = str(agenda or "").strip()
            if not texte:
                continue
            if len(texte) > 200 or any(c.isspace() for c in texte):
                raise ValueError(f"« {texte[:40]} » is not an agenda identifier.")
            propres[str(systeme)] = texte
        return propres

    @field_validator("description")
    @classmethod
    def _description(cls, value):
        if value is None:
            return None
        texte = " ".join(str(value).split())
        return texte or None

    @field_validator("cle")
    @classmethod
    def _cle(cls, value: str) -> str:
        if not _CLE.match(value):
            raise ValueError(
                "The identifier takes lower case letters, digits and hyphens only."
            )
        return value

    @field_validator("mail")
    @classmethod
    def _mail(cls, value):
        if value is None or not str(value).strip():
            return None
        value = str(value).strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError(f"« {value} » is not an e-mail address.")
        return value

    @field_validator("telephone")
    @classmethod
    def _telephone(cls, value):
        if value is None or not str(value).strip():
            return None
        texte = re.sub(r"[\s.\-()]", "", str(value))
        if not re.fullmatch(r"\+[1-9]\d{7,14}", texte):
            raise ValueError(
                f"« {value} » is not a phone number in international format (+33…)."
            )
        return texte


class Sujet(BaseModel):
    code: str
    libelle: str = Field(min_length=1, max_length=100)
    mots_declencheurs: list[str] = Field(default_factory=list, max_length=50)
    urgent: bool = False
    actif: bool = True
    destinataires: list[str] = Field(
        default_factory=list,
        description="Identifiers of the people, in order of priority.",
    )

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if not _CODE.match(value):
            raise ValueError(
                "A subject code takes lower case letters, digits and underscores."
            )
        return value


class Equipe(BaseModel):
    personnes: list[Personne] = Field(default_factory=list, max_length=200)
    sujets: list[Sujet] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _coherente(self):
        cles = [p.cle for p in self.personnes]
        if len(set(cles)) != len(cles):
            raise ValueError("Two people share the same identifier.")
        # H7: one agenda belongs to one person in a software (``lien_externe`` is unique).
        vus: dict[tuple[str, str], str] = {}
        for p in self.personnes:
            for systeme, agenda in (p.agendas or {}).items():
                autre = vus.setdefault((systeme, agenda.casefold()), p.cle)
                if autre != p.cle:
                    raise ValueError(
                        f"{p.prenom} and another person share the same agenda « {agenda} »."
                    )
        codes = [s.code for s in self.sujets]
        if len(set(codes)) != len(codes):
            raise ValueError("Two subjects share the same code.")
        for sujet in self.sujets:
            for cle in sujet.destinataires:
                if cle not in cles:
                    raise ValueError(
                        f"The subject « {sujet.libelle} » routes to an unknown person ({cle})."
                    )
        return self
