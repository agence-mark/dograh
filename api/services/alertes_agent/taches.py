"""[.mark] Sous-lot 6 : les deux tâches de fond (ARQ, ``tasks/arq.py``).

* ``evaluer_les_alertes`` : chaque nuit, les alertes d'agent de toutes les organisations (lecture seule des chiffres déjà rangés) ;
* ``rejouer_les_suites_planifiees`` : chaque heure, les rejeux planifiés DUS (éteints par défaut ; au plus ``PAR_PASSAGE_MAX`` par passage).

Une organisation en échec n'arrête pas les autres. Rien ici ne publie ni ne change un agent.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.db import db_client
from api.services.alertes_agent import planifie, service
from api.services.builder import stock


async def evaluer_les_alertes(_ctx: Any = None) -> dict[int, int]:
    """Le nombre d'alertes NOUVELLES levées par organisation."""
    from api.services.boucle import qualite

    sortie: dict[int, int] = {}
    for organisation_id in await db_client.lister_ids_organisations():
        try:
            # Une lecture pour toute l'organisation ; on n'évalue que les agents qui ont eu au moins deux versions en ligne.
            donnees = await qualite.calculer(organisation_id, jours=30)
            agents = sorted({v["workflow_id"] for v in donnees["versions"]})
            nouvelles = 0
            for workflow_id in agents:
                rendu = await service.evaluer_un_agent(organisation_id, workflow_id)
                nouvelles += sum(1 for a in rendu["alertes"] if a["statut"] == "levee")
            sortie[organisation_id] = nouvelles
        except Exception as erreur:  # noqa: BLE001
            logger.error(f"[alertes-agent] organisation {organisation_id} : {type(erreur).__name__}")
    return sortie


async def rejouer_les_suites_planifiees(_ctx: Any = None, *, rejouer: planifie.Rejouer | None = None) -> list[dict[str, Any]]:
    """Les rejeux joués à ce passage : ``[{organisation, agent, statut, ...}]``."""
    joues: list[dict[str, Any]] = []
    for organisation_id in await db_client.lister_ids_organisations():
        if len(joues) >= planifie.PAR_PASSAGE_MAX:
            break
        try:
            for cle, ligne in await stock.lister(organisation_id, planifie.PREFIXE):
                if len(joues) >= planifie.PAR_PASSAGE_MAX:
                    break
                if not planifie.propres(ligne)["actif"]:
                    continue
                workflow_id = int(cle.removeprefix(planifie.PREFIXE))
                rendu = await planifie.jouer_si_du(organisation_id, workflow_id, rejouer=rejouer)
                if rendu["statut"] != "pas_du":
                    joues.append({"organisation": organisation_id, "agent": workflow_id, **rendu})
        except Exception as erreur:  # noqa: BLE001
            logger.error(f"[rejeu-planifie] organisation {organisation_id} : {type(erreur).__name__}")
    return joues
