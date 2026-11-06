"""[.mark] Builder, lot M : les options de la construction, une ligne ``MARK_BUILDER_OPTIONS`` dans l'organisation des réglages.

Cinq options, toutes sans effet tant qu'on n'y touche pas :

* ``sauvegarde_avant_modification`` : éteinte par défaut ; allumée, le builder ne modifie pas un agent existant avant qu'un
  instantané ait été pris ou refusé (``sauvegarde.py``) ;
* ``builder_coupe`` · ``porte_ecran_coupee`` · ``porte_claude_code_coupee`` (K7) : l'interrupteur du builder et ses deux portes
  (``portes.py``). Elles sont écrites comme des RESTRICTIONS, éteintes par défaut : rien n'est coupé tant qu'on n'y touche pas ;
* ``recette_par_defaut`` : le nom (l'identifiant) de la recette d'agent proposée à la création. Vide : la recette que la
  bibliothèque marque comme défaut de départ (``recettes.py``). Le code ne connaît aucun nom de recette.

Une ligne à part de ``MARK_BUILDER_CERVEAU`` : enregistrer le cerveau n'efface jamais ces options.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from api.services.builder import stock
from api.services.builder.constantes import CLE_OPTIONS


class Options(BaseModel):
    sauvegarde_avant_modification: bool = False
    builder_coupe: bool = False
    porte_ecran_coupee: bool = False
    porte_claude_code_coupee: bool = False
    recette_par_defaut: str = Field(default="", max_length=64)


async def lire(organisation: int) -> Options:
    brut = await stock.lire(organisation, CLE_OPTIONS)
    return Options.model_validate(brut) if brut else Options()


async def ecrire(organisation: int, options: Options) -> None:
    await stock.ecrire(organisation, CLE_OPTIONS, options.model_dump(mode="json"))


async def organisation_des_options(user) -> int:
    from api.services.builder.cerveau import reglages

    return await reglages.organisation_des_reglages(user)


def organisation_pour(organisation_de_l_agent: int) -> int:
    """Là où vivent les options quand on n'a pas la personne sous la main : l'organisation .mark de la bibliothèque, sinon celle de l'agent."""
    from api.services.builder.constantes import organisation_bibliotheque

    return organisation_bibliotheque() or organisation_de_l_agent
