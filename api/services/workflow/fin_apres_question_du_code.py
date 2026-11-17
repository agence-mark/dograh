"""[.mark] M108 (appels 2592, 2593) : la fin de l'appel attend la réponse à une question que le code vient de poser.

Un garde-fou au sens du registre (``reference/29-garde-fous.md``, section B) : il détecte un **mécanisme**, sans comprendre l'agent ni parler
un mot de métier.

- **Il détecte** : dans la même réponse, le modèle appelle un outil dont le texte dit par le code finit par une question (la confirmation d'un
  enregistrement suivie de « autre chose ? »), ET la fin de l'appel. La question rend la parole (M92) mais la fin, lancée dans la même réponse,
  partait quand même : « … Au revoir. » sans attendre la réponse.
- **Il fait** : la fin attend d'abord les autres appels d'outil de la même réponse (bornée), puis, si le code a posé une question dans le tour
  en cours et que la personne n'a pas encore parlé, elle est refusée sans relancer le modèle : la parole est à la personne. Sa réponse ouvre un
  nouveau tour : la fin passe de nouveau (jamais un appel coincé).

⛔ Zéro vocabulaire métier. ⛔ Ne lève jamais : dans le doute, la fin passe (comme avant).
"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

STATUT_REFUS = "attente_de_reponse"
MESSAGE_REFUS = (
    "La fin de l'appel n'est pas faite : le code vient de poser une question à la personne. Attends sa réponse avant de finir l'appel."
)
# Le plus long qu'on attend les autres appels d'outil de la même réponse (au-delà, la fin est jugée sur ce qui est su).
ATTENTE_MAX_S = 10.0


async def attendre_les_autres_appels(params: Any, delai_s: float = ATTENTE_MAX_S) -> None:
    """Attend la fin des autres appels d'outil en cours du même service de conversation (la même réponse, en parallèle). En séquentiel, il n'y en
    a pas : ceux d'avant sont finis, ceux d'après attendent celui-ci. ⛔ Ne lève jamais."""
    try:
        service = getattr(params, "llm", None)
        taches = getattr(service, "_function_call_tasks", None)
        if not isinstance(taches, dict):
            return
        moi = asyncio.current_task()
        autres = [t for t in list(taches.keys()) if t is not None and t is not moi and not t.done()]
        if autres:
            await asyncio.wait(autres, timeout=delai_s)
    except Exception as erreur:  # noqa: BLE001
        logger.debug(f"[fin] autres appels non attendus : {erreur!r}")


async def refus_de_fin_si_question_en_attente(moteur: Any, params: Any) -> dict | None:
    """La fin de l'appel est demandée : le résultat de refus à rendre au modèle (sans le relancer), ou ``None`` : la fin passe. ⛔ Ne lève jamais."""
    try:
        from api.services.outils_mark.pour_la_voix import question_du_code_en_attente

        await attendre_les_autres_appels(params)
        if not question_du_code_en_attente(moteur):
            return None
        logger.info("[fin] fin refusée : le code vient de poser une question, la personne n'a pas encore répondu")
        return {"status": STATUT_REFUS, "message": MESSAGE_REFUS}
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[fin] fin non contrôlée (question du code) : {erreur!r}")
        return None
