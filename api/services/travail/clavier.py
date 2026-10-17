"""[.mark] Lot 4 d'orchestrateur-trois-cerveaux (D8) : le cerveau de fond au clavier.

Le clavier n'a ni circuit d'appel ni worker d'appel : chaque tour monte un moteur neuf, qui meurt à
la fin du tour. Le travail de fond y suit donc la même route qu'au téléphone (même worker, même
job, mêmes outils, mêmes jetons) sur un mini-bus local, avec deux différences :

- **le travail se termine dans le tour** : le clavier attend la fin de la tâche (au plus le délai
  réglé) avant de démonter le tour ;
- **le résultat n'est pas poussé** : il est gardé dans la trace (``travaux`` de la fiche, qui
  voyage dans le point de reprise du clavier) et **injecté au tour suivant**, juste avant la
  réplique tapée, sous la même forme ``[Résultat du travail : …]``. Le banc au clavier voit donc ce
  que la voix verrait, en différé d'un tour.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from loguru import logger
from pipecat.pipeline.job_context import JobParams
from pipecat.workers.base_worker import BaseWorker
from pipecat.workers.llm.backend_llm_worker import BACKEND_JOB_NAME

from api.services.pipecat.worker_runner import create_worker_runner
from api.services.travail.reglages import CLE_TRAVAUX

# Un travail fini attend d'être remis, ou a été remis au tour indiqué.
CLE_MESSAGE = "message"


async def executer_en_local(travail: Any, demande: str) -> str:
    """Le job du fond sur un mini-bus du tour : un demandeur, le worker de fond, un lanceur qui
    s'arrête à la fin du job. Lève en cas d'échec ou de délai (comme au téléphone)."""
    demandeur = BaseWorker(f"demandeur-{uuid.uuid4().hex[:8]}")
    lanceur = create_worker_runner()
    await lanceur.add_workers(demandeur, travail.worker)
    delai = float(travail.reglages.delai_max_s)
    params = JobParams(name=BACKEND_JOB_NAME, payload={"request": demande}, timeout=delai)

    async def corps() -> str:
        try:
            async with demandeur.job(travail.worker.name, params=params) as en_cours:
                async for _evenement in en_cours:
                    pass
            return str(en_cours.response.get("text", ""))
        finally:
            await lanceur.cancel()

    tache = asyncio.create_task(lanceur.run())
    try:
        resultat = await asyncio.wait_for(corps(), timeout=delai + 10.0)
    finally:
        await lanceur.cancel()
        await asyncio.gather(tache, return_exceptions=True)
    return resultat


async def remettre_au_tour_suivant(_moteur: Any, _message: str) -> bool:
    """Au clavier le résultat n'est pas poussé : il reste dans la trace, et le tour suivant le
    lit (``remettre_les_travaux_termines``)."""
    return False


def travaux_a_remettre(fiche: dict | None) -> list[dict]:
    """Les travaux terminés de la fiche dont le résultat n'a pas encore été remis, dans l'ordre."""
    return [
        entree
        for entree in (fiche or {}).get(CLE_TRAVAUX, []) or []
        if isinstance(entree, dict)
        and entree.get("statut") not in (None, "en_cours")
        and entree.get("remis") is not True
        and isinstance(entree.get(CLE_MESSAGE), str)
    ]


def remettre_les_travaux_termines(fiche: dict | None, contexte: Any) -> int:
    """Au début d'un tour tapé : injecte dans ``contexte`` le résultat de chaque travail terminé
    pas encore remis (message ``[Résultat du travail : …]``), et le marque remis. Rend leur
    nombre. ⛔ Ne lève jamais."""
    try:
        restants = travaux_a_remettre(fiche)
        for entree in restants:
            contexte.add_message({"role": "user", "content": entree[CLE_MESSAGE]})
            entree["remis"] = True
            entree["remis_au_tour"] = (fiche or {}).get("tour")
        if restants:
            logger.info(f"[travail] {len(restants)} résultat(s) remis au tour suivant (clavier)")
        return len(restants)
    except Exception as erreur:  # noqa: BLE001 -- un résultat non remis ne casse pas le tour
        logger.error(f"[travail] résultats du clavier non remis : {type(erreur).__name__}")
        return 0
