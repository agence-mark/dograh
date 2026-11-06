"""[.mark] Builder : la table de prix par modèle (constat C2, Evan 01/11).

Une ligne ``MARK_BUILDER_PRIX`` dans l'organisation des réglages : pour chaque modèle, son prix d'entrée et de sortie
en dollars par million de jetons. Elle sert au plafond en dollars de la conversation du builder, de l'appelant simulé et
du juge (un plafond en dollars sans prix connu ne coupe rien : seul le plafond en jetons tient alors).

Ordre de lecture d'un prix : la ligne du modèle dans la table, sinon les deux prix saisis dans les réglages du cerveau
(repli d'avant la table), sinon zéro. Aucun prix n'est écrit en dur : la table part vide et se règle à l'écran.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from api.services.builder import stock
from api.services.builder.constantes import CLE_PRIX

LIGNES_MAX = 100


class PrixDUnModele(BaseModel):
    modele: str = Field(min_length=1, max_length=200)
    entree_par_million: float = Field(default=0.0, ge=0, le=10_000)
    sortie_par_million: float = Field(default=0.0, ge=0, le=10_000)

    @field_validator("modele")
    @classmethod
    def _sans_blanc(cls, valeur: str) -> str:
        valeur = valeur.strip()
        if not valeur:
            raise ValueError("model name required")
        return valeur


class TableDesPrix(BaseModel):
    modeles: list[PrixDUnModele] = Field(default_factory=list, max_length=LIGNES_MAX)

    @field_validator("modeles")
    @classmethod
    def _uniques(cls, lignes: list[PrixDUnModele]) -> list[PrixDUnModele]:
        vus: set[str] = set()
        for ligne in lignes:
            if ligne.modele in vus:
                raise ValueError(f"model listed twice: {ligne.modele}")
            vus.add(ligne.modele)
        return lignes

    def prix_de(self, modele: str) -> PrixDUnModele | None:
        return next((ligne for ligne in self.modeles if ligne.modele == modele.strip()), None)


async def lire(organisation: int) -> TableDesPrix:
    brut = await stock.lire(organisation, CLE_PRIX)
    return TableDesPrix.model_validate(brut) if brut else TableDesPrix()


async def ecrire(organisation: int, table: TableDesPrix) -> None:
    await stock.ecrire(organisation, CLE_PRIX, table.model_dump(mode="json"))
