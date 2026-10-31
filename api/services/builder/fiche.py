"""[.mark] Builder : la fiche client, le pivot (``05-architecture.md`` § 4). Lot 1 : lire et écrire ; le lot 3 la tire des documents.

Rangée dans ``MARK_BUILDER:<agent>:fiche`` (organisation du client, ≤ 100 Ko). Règles tenues ici :

* **chaque ligne cite sa source** (document, page) : sans source, la ligne n'entre pas (« rien n'est annoncé sans preuve ») ;
* un **trou** est une question avec, si on l'a, une réponse suggérée ; il reste ouvert tant qu'aucune ligne sourcée ne le comble ;
* le builder n'écrit que des lignes « propose » ; **la validation est le geste d'une personne**, refusée tant qu'un trou est ouvert,
  et toute écriture du builder qui change une ligne retire la validation.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from api.services.builder import stock
from api.services.builder.bibliotheque.modele import maintenant
from api.services.builder.constantes import FICHE_MAX_OCTETS, cle_builder
from api.services.builder.dossiers import classement as classement_des_faits


class ErreurFiche(Exception):
    pass


class ChampFiche(BaseModel):
    valeur: Any
    source: str = Field(min_length=1, max_length=500, description="Document and page, or site page, the line comes from.")
    classement: Literal["objet", "base", "regle"] | None = Field(
        default=None,
        description=(
            "Where the fact goes (B47): 'objet' = small, critical, may be quoted at any time, the client will edit it "
            "(hours, area, brands, prices, numbers); 'base' = large, rarely asked (FAQ, catalogue, conditions); "
            "'regle' = conduct rule that stays in the prompt. Empty: the standard field's default, else by size."
        ),
    )


class Trou(BaseModel):
    champ: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=500)
    reponse_suggeree: str | None = Field(default=None, max_length=500)


class Fiche(BaseModel):
    champs: dict[str, ChampFiche] = Field(default_factory=dict)
    trous: list[Trou] = Field(default_factory=list, max_length=100)
    valide_par: str | None = None
    valide_le: datetime | None = None
    revision: int = 0

    @property
    def validee(self) -> bool:
        return self.valide_par is not None


def cle(workflow_id: int) -> str:
    return cle_builder(workflow_id, "fiche")


async def lire(organization_id: int, workflow_id: int) -> Fiche:
    brut = await stock.lire(organization_id, cle(workflow_id))
    return Fiche.model_validate(brut) if brut else Fiche()


async def ecrire(
    organization_id: int,
    workflow_id: int,
    champs: dict[str, ChampFiche],
    trous: list[Trou] | None = None,
) -> Fiche:
    """Ajoute ou remplace des lignes sourcées et pose les trous demandés. Une ligne change = validation retirée."""
    for nom, champ in champs.items():
        refus = classement_des_faits.verifier(nom, champ.classement, champ.valeur)
        if refus:
            raise ErreurFiche(refus)

    def ajouter(brut: dict[str, Any] | None) -> dict[str, Any]:
        # Revue R6 : relue et réécrite sous condition (rejouée sur la valeur la plus récente si une autre écriture est passée).
        fiche = Fiche.model_validate(brut) if brut else Fiche()
        nouveaux = dict(fiche.champs)
        change = False
        for nom, champ in champs.items():
            if nouveaux.get(nom) != champ:
                change = True
            nouveaux[nom] = champ
        # Un trou comblé par une ligne sourcée se ferme ; les nouveaux s'ajoutent (un par champ).
        ouverts = {t.champ: t for t in fiche.trous if t.champ not in champs}
        for trou in trous or []:
            if trou.champ not in nouveaux:
                if trou.champ not in ouverts or ouverts[trou.champ] != trou:
                    change = True
                ouverts[trou.champ] = trou
        mise_a_jour = fiche.model_copy(
            update={
                "champs": nouveaux,
                "trous": list(ouverts.values()),
                "revision": fiche.revision + 1,
                **({"valide_par": None, "valide_le": None} if change else {}),
            }
        )
        donnees = mise_a_jour.model_dump(mode="json")
        if len(json.dumps(donnees, ensure_ascii=False).encode("utf-8")) > FICHE_MAX_OCTETS:
            raise ErreurFiche(f"The client sheet is too large (more than {FICHE_MAX_OCTETS} bytes).")
        return donnees

    ecrite = await stock.modifier(organization_id, cle(workflow_id), ajouter)
    return Fiche.model_validate(ecrite)


async def valider(organization_id: int, workflow_id: int, auteur: str) -> Fiche:
    """Le geste d'une personne. Refusé s'il reste un trou ouvert ou si la fiche est vide."""
    def valider_la_fiche(brut: dict[str, Any] | None) -> dict[str, Any]:
        fiche = Fiche.model_validate(brut) if brut else Fiche()
        if not fiche.champs:
            raise ErreurFiche("The client sheet is empty: nothing to validate.")
        if fiche.trous:
            raise ErreurFiche(f"{len(fiche.trous)} gap(s) are still open: answer them before validating.")
        return fiche.model_copy(update={"valide_par": auteur, "valide_le": maintenant()}).model_dump(mode="json")

    return Fiche.model_validate(await stock.modifier(organization_id, cle(workflow_id), valider_la_fiche))
