"""[.mark] Batterie du builder : les cas, écrits comme une demande d'utilisateur (fichiers ``cas/*.json``)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

DOSSIER = Path(__file__).resolve().parent / "cas"


class Correcteur(BaseModel):
    # appelee : l'action a été appelée · interdite : elle ne l'a jamais été · ordre : ces actions, dans cet ordre
    # motif : le texte (regex) se trouve dans la trace · juge : une rubrique lue par un juge à rubrique
    genre: str = Field(pattern="^(appelee|interdite|ordre|motif|juge)$")
    actions: list[str] = Field(default_factory=list, max_length=12)
    motif: str = ""
    rubrique: str = ""


class Cas(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    demande: str = Field(min_length=1, description="Écrite comme le ferait la personne : jamais le nom d'une action.")
    # La plateforme simulée : le résultat imposé de chaque action ; une action absente répond {"ok": true}.
    plateforme: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # Le cerveau scripté de ce dépôt : une liste de tours, chaque tour une liste de {"texte": ..} ou {"appel": nom, "arguments": {..}}.
    tours: list[list[dict[str, Any]]] = Field(default_factory=list)
    correcteurs: list[Correcteur] = Field(min_length=1)

    @property
    def empreinte(self) -> str:
        """Change dès que la demande, la plateforme ou un correcteur change : une référence ancienne ne vaut plus pour ce cas."""
        brut = json.dumps(
            {"demande": self.demande, "plateforme": self.plateforme, "correcteurs": [c.model_dump() for c in self.correcteurs]},
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(brut.encode("utf-8")).hexdigest()[:16]


def charger(dossier: Path = DOSSIER) -> list[Cas]:
    return [Cas.model_validate(json.loads(f.read_text(encoding="utf-8"))) for f in sorted(dossier.glob("*.json"))]
