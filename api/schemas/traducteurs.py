"""[.mark] The translators chosen by an organization (chantier l-agent-collegue, L4).

``agenda``: the calendar software the planner books in (``google_agenda``, ``outlook_agenda``…,
the ``systeme`` of a declared translator). None: no calendar software, the planner is off.
The name is checked against the declared translators when SAVED (route), never when read.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

_SYSTEME = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


class ChoixTraducteurs(BaseModel):
    agenda: str | None = Field(
        default=None,
        description="The calendar software the agent books in (a translator's name). None: none.",
    )

    @field_validator("agenda")
    @classmethod
    def _systeme(cls, value):
        if value is None or not str(value).strip():
            return None
        if not _SYSTEME.match(str(value)):
            raise ValueError(
                "A translator's name takes lower case letters, digits and underscores."
            )
        return str(value)


class TraducteurVue(BaseModel):
    systeme: str
    libelle: str
    domaine: str
    integration: str
    reference_agenda: dict[str, str] = Field(
        default_factory=dict, description="What identifies a person's agenda, {en, fr}."
    )
    operations: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Object of the hub -> operations this translator does.",
    )
