"""[.mark] Builder : les actions du dialogue avec la personne (U5, E26) : la carte « plan » et la carte « question ».

* ``plan_mettre_a_jour`` : le builder range son plan en cases (fait, en cours, à venir) ; le CODE dessine la carte, le modèle
  ne fait que cocher. Le plan courant est gardé dans la conversation (``plan``) pour que le builder le relise.
* ``question_poser`` : UNE question à la fois, sur une carte, avec la réponse qu'il propose ; la personne répond
  « autre » (saisie libre) ou « passer ». Le builder attend la réponse avant de continuer.

Actions de l'écran seulement (``mcp=False``) : une carte n'a pas de sens dans Claude Code. Aucune n'écrit dans un agent.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from api.services.builder.actions.registre import Action, Contexte, ErreurAction, enregistrer

ETAPES_MAX = 20


class _Etape(BaseModel):
    libelle: str = Field(min_length=1, max_length=200)
    etat: Literal["fait", "en_cours", "a_venir"] = "a_venir"


class _Plan(BaseModel):
    etapes: list[_Etape] = Field(min_length=1, max_length=ETAPES_MAX)


async def _plan(contexte: Contexte, parametres: _Plan) -> dict[str, Any]:
    if sum(1 for e in parametres.etapes if e.etat == "en_cours") > 1:
        raise ErreurAction("Only one step is in progress at a time.")
    etapes = [e.model_dump() for e in parametres.etapes]
    if contexte.conversation is not None:
        contexte.conversation["plan"] = etapes
    faites = sum(1 for e in etapes if e["etat"] == "fait")
    return {"ok": True, "faites": faites, "total": len(etapes), "carte": {"type": "plan", "etapes": etapes}}


class _Question(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    reponse_proposee: str = Field(min_length=1, max_length=500)
    choix: list[str] = Field(default_factory=list, max_length=6)


async def _question(contexte: Contexte, parametres: _Question) -> dict[str, Any]:
    return {
        "ok": True,
        "attente": "Wait for the person's answer before going further: do not ask another question now.",
        "carte": {
            "type": "question",
            "question": parametres.question,
            "reponse_proposee": parametres.reponse_proposee,
            "choix": parametres.choix,
        },
    }


enregistrer(
    Action(
        nom="plan_mettre_a_jour",
        description=(
            "Keep the plan card up to date: the full list of steps, each fait / en_cours / a_venir. Send it when the plan is "
            "set and each time a step is crossed. One step at most is en_cours."
        ),
        parametres=_Plan,
        fonction=_plan,
        ecriture=False,
        mcp=False,
        groupe="dialogue",
    )
)
enregistrer(
    Action(
        nom="question_poser",
        description=(
            "Ask the person ONE question on a card, with the answer you propose (and optional choices). Then stop and wait for "
            "the answer: never chain questions. The person can answer, choose « autre » or pass."
        ),
        parametres=_Question,
        fonction=_question,
        ecriture=False,
        mcp=False,
        groupe="dialogue",
    )
)
