"""[.mark] Builder partie 3, SA-17c : les gestes des contacts du portail (fiche rendue, corps du geste « mémoriser »)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DoubleAvec(BaseModel):
    avec: int = Field(description="The contact this one may double.")
    raison: str | None = None


class ContactTraite(BaseModel):
    """The contact as it stands after the gesture."""

    id: int
    nom: str | None = None
    prenom: str | None = None
    mail: str | None = None
    mail_declare: bool
    nature: str
    telephones: list[str]
    doublon: DoubleAvec | None = None
    ne_pas_memoriser: bool
    nb_appels: int
    nb_commentaires: int


class ContactFusionne(ContactTraite):
    """The kept contact, plus what was merged into it. ``deja_fait``: the merge had already been done (a replay)."""

    fusionne_depuis: int
    deja_fait: bool


class MemoriserContact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memoriser: bool = Field(description="False: the agent reads no history of this person any more. True: it reads it again.")
