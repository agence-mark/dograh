"""[.mark] Builder : le document de conception, écrit et approuvé AVANT toute construction (B36).

Rangé dans ``MARK_BUILDER:<agent>:conception``, dans l'organisation du client. Le builder l'écrit (état
``propose``) ; seule une PERSONNE l'approuve ou le renvoie avec une note (route ``/builder``). Toute nouvelle
écriture du builder remet l'état à ``propose`` : ce qui est approuvé n'est jamais modifié en silence.

Le contenu suit B36 : objectif et réussite ; hypothèses à confirmer (un trou peut devenir une hypothèse
écrite, jamais une invention) ; pour chaque donnée, que faire si la personne ne peut pas la donner ; pour chaque
outil, ses réponses possibles dont « système indisponible » ; des exemples d'appels.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from api.services.builder import stock
from api.services.builder.bibliotheque.modele import maintenant
from api.services.builder.constantes import cle_builder


class Donnee(BaseModel):
    nom: str = Field(min_length=1, max_length=200)
    si_absente: str = Field(min_length=1, max_length=500, description="What to do if the caller cannot give it.")


class OutilPrevu(BaseModel):
    nom: str = Field(min_length=1, max_length=200)
    reponses: list[str] = Field(min_length=1, max_length=20, description="The answers the tool can give.")
    si_indisponible: str = Field(min_length=1, max_length=500, description="What the agent does when the system is unavailable.")


class Conception(BaseModel):
    objectif: str = Field(min_length=1, max_length=2000)
    reussite: str = Field(min_length=1, max_length=2000, description="What counts as a success.")
    hypotheses: list[str] = Field(default_factory=list, max_length=30)
    donnees: list[Donnee] = Field(default_factory=list, max_length=40)
    outils: list[OutilPrevu] = Field(default_factory=list, max_length=20)
    exemples_appels: list[str] = Field(default_factory=list, max_length=20)


class EtatConception(BaseModel):
    conception: Conception
    etat: Literal["propose", "approuve", "renvoye"] = "propose"
    revision: int = 1
    note: str | None = None
    decide_par: str | None = None
    decide_le: datetime | None = None


class ErreurConception(Exception):
    pass


def cle(workflow_id: int) -> str:
    return cle_builder(workflow_id, "conception")


async def lire(organization_id: int, workflow_id: int) -> EtatConception | None:
    brut = await stock.lire(organization_id, cle(workflow_id))
    return EtatConception.model_validate(brut) if brut else None


async def ecrire(organization_id: int, workflow_id: int, conception: Conception) -> EtatConception:
    """Écrit (ou réécrit) le document : toujours à l'état ``propose``, avec une révision de plus."""
    rendu: list[EtatConception] = []

    def transformer(brut):
        avant = EtatConception.model_validate(brut) if brut else None
        etat = EtatConception(conception=conception, revision=(avant.revision + 1) if avant else 1)
        rendu[:] = [etat]
        return etat.model_dump(mode="json")

    await stock.modifier(organization_id, cle(workflow_id), transformer)
    return rendu[0]


async def decider(
    organization_id: int, workflow_id: int, approuve: bool, auteur: str, note: str | None = None
) -> EtatConception:
    """Le geste d'une personne : approuver, ou renvoyer avec une note (obligatoire pour renvoyer)."""
    if not approuve and not (note or "").strip():
        raise ErreurConception("Sending the document back needs a note.")
    rendu: list[EtatConception] = []
    le = maintenant()

    def transformer(brut):
        if not brut:
            raise ErreurConception("No design document to decide on.")
        decide = EtatConception.model_validate(brut).model_copy(
            update={
                "etat": "approuve" if approuve else "renvoye",
                "note": (note or "").strip() or None,
                "decide_par": auteur,
                "decide_le": le,
            }
        )
        rendu[:] = [decide]
        return decide.model_dump(mode="json")

    await stock.modifier(organization_id, cle(workflow_id), transformer)
    return rendu[0]


async def exiger_approuvee(organization_id: int, workflow_id: int) -> None:
    """Garde de la construction : pas de document approuvé, pas de changement de l'agent."""
    etat = await lire(organization_id, workflow_id)
    if etat is None:
        raise ErreurConception("Write the design document first: nothing is built before it is approved.")
    if etat.etat != "approuve":
        raise ErreurConception(
            "The design document is not approved yet"
            + (f" (sent back: {etat.note})" if etat.etat == "renvoye" and etat.note else "")
            + ": nothing is built before a person approves it."
        )


def resume(etat: EtatConception | None) -> dict[str, Any] | None:
    return etat.model_dump(mode="json") if etat else None
