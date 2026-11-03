"""[.mark] U8 (lot D) : la version estampillée d'un appel.

Chaque appel porte la version de l'agent qui l'a mené (``definition_id`` existait déjà, on y ajoute son numéro) et les versions des
recettes que l'agent utilisait. Rangé dans ``annotations['boucle']['version']`` par l'après-appel : lu ensuite pour comparer avant et
après une publication (page Qualité), jamais recalculé.

Les recettes viennent des lignes d'usage de la bibliothèque (``enregistrer_utilisation``) : on garde, pour CET agent, la version de
chaque élément appliqué. Elles sont lues au moment de l'après-appel, proche de l'appel : c'est l'état de l'agent à ce moment-là.
⛔ Ne lève jamais.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.services.builder import stock
from api.services.builder.constantes import PREFIXE_USAGE

RECETTES_MAX = 40


async def recettes_de_l_agent(organisation_id: int, workflow_id: int) -> list[dict[str, Any]]:
    """Les éléments de bibliothèque appliqués à cet agent : ``[{famille, slug, version}]``, au plus ``RECETTES_MAX``."""
    from api.services.builder.bibliotheque import service

    biblio = service.organisation_bibliotheque()
    if biblio is None:
        return []
    cle = f"{organisation_id}:{workflow_id}"
    trouvees = []
    for ligne, valeur in await stock.lister(biblio, PREFIXE_USAGE):
        agent = (valeur.get("agents") or {}).get(cle)
        if isinstance(agent, dict):
            famille, _, slug = ligne.removeprefix(PREFIXE_USAGE).partition(":")
            trouvees.append({"famille": famille, "slug": slug, "version": agent.get("version")})
    return trouvees[:RECETTES_MAX]


async def estampiller(run: Any, organisation_id: int) -> dict[str, Any]:
    """``{definition_id, version, recettes}`` d'un appel."""
    try:
        definition = getattr(run, "definition", None)
        return {
            "definition_id": getattr(run, "definition_id", None),
            "version": getattr(definition, "version_number", None),
            "recettes": await recettes_de_l_agent(organisation_id, run.workflow_id),
        }
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[boucle] version non estampillée : {type(erreur).__name__}")
        return {"definition_id": getattr(run, "definition_id", None), "version": None, "recettes": []}
