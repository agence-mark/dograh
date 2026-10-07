"""[.mark] The caller's verification before any record is read (chantier l-agent-collegue, L6, V1 to V7).

The organization declares (theme « Caller verification »):

- the FACTORS it accepts (V2): the number calling matches the record (``numero``); a control
  question on fields it chooses (``question``); a one-time code sent by SMS to the record's
  number (``code_sms``, V5: wired, off, never configured nor tried for real in this chantier);
- the control fields of the question (``champs_controle``), a closed list;
- for each kind of readable data, the LEVEL required (how many distinct factors passed) and
  the fields the agent may read (``lisibles``);
- where the record is read (``logiciel``): the client's database (the hub, V4) by default, or
  the translator of a software that holds the records (V3).

The agent switch ``verification_appelant`` (agent settings, off by default) turns it on agent
by agent (V7). Two attempts at most (V6), fixed. Stored under ``VERIFICATION_APPELANT`` in
``organization_configurations`` (no migration of Dograh, X3).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator, model_validator

FACTEURS = ("numero", "question", "code_sms")
CHAMPS_CONTROLE = ("reference", "nom", "code_postal", "commune", "mail")
# What the agent may read, kind by kind, and the fields of each (common format of the hub).
TYPES_LISIBLES: dict[str, tuple[str, ...]] = {
    "demandes": ("reference", "type", "statut", "creee_le", "resume"),
    "rendez_vous": ("debut", "fin", "libelle", "statut"),
}
TENTATIVES_MAX = 2  # V6
CODE_LONGUEUR = 6
CODE_VALIDITE_S = 600
_SYSTEME = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


class NiveauLecture(BaseModel):
    facteurs_requis: int = Field(
        default=2, ge=1, le=3, description="How many distinct factors must have passed."
    )
    champs: list[str] = Field(default_factory=list, description="The fields the agent may read.")


def _defauts_lisibles() -> dict[str, NiveauLecture]:
    return {
        "demandes": NiveauLecture(facteurs_requis=2, champs=["reference", "type", "statut", "creee_le"]),
        "rendez_vous": NiveauLecture(facteurs_requis=2, champs=["debut", "libelle", "statut"]),
    }


class ReglagesVerification(BaseModel):
    numero: bool = Field(default=True, description="The number calling matches the record.")
    question: bool = Field(default=True, description="A control question on the fields chosen.")
    code_sms: bool = Field(
        default=False,
        description="A one-time code sent by SMS to the record's mobile, through the client's Twilio.",
    )
    champs_controle: list[str] = Field(default_factory=lambda: ["nom", "code_postal"])
    lisibles: dict[str, NiveauLecture] = Field(default_factory=_defauts_lisibles)
    logiciel: str | None = Field(
        default=None,
        description="A translator of the domain « dossier » that holds the records. None: the client database.",
    )

    @field_validator("champs_controle")
    @classmethod
    def _champs(cls, valeurs: list[str]) -> list[str]:
        inconnus = [v for v in valeurs if v not in CHAMPS_CONTROLE]
        if inconnus:
            raise ValueError(f"Unknown control field(s): {', '.join(inconnus)}.")
        return list(dict.fromkeys(valeurs))

    @field_validator("logiciel")
    @classmethod
    def _logiciel(cls, value):
        if value is None or not str(value).strip():
            return None
        if not _SYSTEME.match(str(value)):
            raise ValueError("A translator's name takes lower case letters, digits and underscores.")
        return str(value)

    @model_validator(mode="after")
    def _coherence(self):
        if self.question and not self.champs_controle:
            raise ValueError("The control question needs at least one field.")
        for type_, niveau in self.lisibles.items():
            if type_ not in TYPES_LISIBLES:
                raise ValueError(f"« {type_} » is not a kind of readable data.")
            inconnus = [c for c in niveau.champs if c not in TYPES_LISIBLES[type_]]
            if inconnus:
                raise ValueError(f"{type_}: unknown field(s) {', '.join(inconnus)}.")
            niveau.champs = list(dict.fromkeys(niveau.champs))
        return self

    def facteurs_actifs(self) -> list[str]:
        return [f for f in FACTEURS if getattr(self, f)]
