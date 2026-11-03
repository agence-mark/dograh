"""[.mark] Builder, lot M (7) : lire une recette d'agent avec ses pièces (écran et Claude Code).

``recette_lire`` rend la fiche de la recette (nom, méthode de construction, capacités, scénarios) et le contenu de chacune de ses
pièces : le builder construit avec elles. Sans ``recette``, c'est celle de l'agent. Lecture seule ; aucun nom de recette ici.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from api.services.builder import recettes
from api.services.builder.actions.registre import Action, Contexte, ErreurAction, enregistrer


class _Recette(BaseModel):
    workflow_id: int | None = Field(default=None, description="The agent; defaults to the conversation's agent.")
    recette: str | None = Field(default=None, max_length=64, description="A recipe identifier; empty reads the recipe of the agent (or the default one).")


async def _lire(contexte: Contexte, parametres: _Recette) -> dict[str, Any]:
    slug = parametres.recette
    indiquee = True
    if not slug:
        identifiant = parametres.workflow_id if parametres.workflow_id is not None else contexte.workflow_id
        if identifiant is not None:
            from api.services.builder.actions._commun import agent_verifie

            await agent_verifie(contexte, identifiant)
            recette, indiquee = await recettes.de_l_agent(contexte.organisation_id, identifiant)
        else:
            recette, indiquee = await recettes.par_defaut(contexte.organisation_id), False
        if recette is None:
            raise ErreurAction("The library holds no agent recipe.", "recette")
        slug = recette.slug
    rendu = await recettes.lire_avec_les_pieces(slug)
    if rendu is None:
        raise ErreurAction("Unknown recipe.", "recette")
    return {"ok": True, "indiquee_sur_l_agent": indiquee, "recette": rendu}


enregistrer(
    Action(
        nom="recette_lire",
        description="Read an agent recipe with its pieces (general prompt, step moulds, conditions, tool and transfer models, rules). Without 'recette', the recipe of the agent. A Candidate recipe is not proven: say so.",
        parametres=_Recette,
        fonction=_lire,
        ecriture=False,
        groupe="bibliotheque",
    )
)
