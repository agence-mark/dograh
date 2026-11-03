"""[.mark] U10 / S3 : ce que le widget public envoie après la conversation (avis), quand le plafond du mois est atteint
(demande de rappel) et pour compter l'affichage (événement anonyme). Tout est borné : cette surface est joignable
depuis n'importe quelle page.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_MAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s.]{2,24}$")


def telephone_propre(brut: str | None) -> str | None:
    """Un numéro lisible par la base (``+`` et chiffres), ou ``None`` ; un numéro français en 0 devient +33."""
    if brut is None:
        return None
    texte = str(brut).strip()
    if not texte:
        return None
    plus = texte.startswith("+")
    chiffres = re.sub(r"\D", "", texte)
    if plus:
        numero = "+" + chiffres
    elif chiffres.startswith("00"):
        numero = "+" + chiffres[2:]
    elif len(chiffres) == 10 and chiffres.startswith("0"):
        numero = "+33" + chiffres[1:]
    else:
        raise ValueError("invalid phone number")
    if not 8 <= len(numero) - 1 <= 15:
        raise ValueError("invalid phone number")
    return numero


class ContactVisiteur(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nom: str | None = Field(default=None, max_length=200)
    telephone: str | None = Field(default=None, max_length=40)
    mail: str | None = Field(default=None, max_length=254)

    @field_validator("telephone")
    @classmethod
    def _telephone(cls, valeur):
        return telephone_propre(valeur)

    @field_validator("mail")
    @classmethod
    def _mail(cls, valeur):
        if valeur is None or not valeur.strip():
            return None
        propre = valeur.strip().lower()
        if not _MAIL.match(propre):
            raise ValueError("invalid mail")
        return propre

    @field_validator("nom")
    @classmethod
    def _nom(cls, valeur):
        return valeur.strip() or None if valeur is not None else None

    def a_de_quoi_rappeler(self) -> bool:
        return bool(self.telephone or self.mail)


class AvisPublic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    etoiles: int = Field(ge=1, le=5)
    obtenu: Literal["oui", "en_partie", "non"] | None = None
    raisons: list[str] = Field(default_factory=list, max_length=10)
    commentaire: str | None = Field(default=None, max_length=2000)
    rappel_demande: bool = False
    publication_acceptee: bool = False
    contact: ContactVisiteur | None = None

    @field_validator("raisons")
    @classmethod
    def _raisons(cls, valeurs):
        return [v.strip()[:120] for v in valeurs if isinstance(v, str) and v.strip()]

    def en_dict(self) -> dict:
        return self.model_dump(mode="json", exclude_none=True)


class AvisRecu(BaseModel):
    ok: bool = True


class RappelPublic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chemin: str = Field(default="/", max_length=512)
    contact: ContactVisiteur
    message: str | None = Field(default=None, max_length=1000)


class EvenementPublic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cle: str | None = Field(default=None, max_length=80)
    token: str | None = Field(default=None, max_length=120)
    chemin: str = Field(default="/", max_length=512)
    evenement: Literal["affiche", "ouvert"]


class EvenementJour(BaseModel):
    workflow_id: int
    jour: str
    affiche: int
    ouvert: int
