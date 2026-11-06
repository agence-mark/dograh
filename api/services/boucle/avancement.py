"""[.mark] U8 (B, F) : l'avancement d'un problème de « À améliorer » : test créé, correction dans le brouillon, suite rejouée, publication.

Rien n'est inventé : chaque temps se COCHE à partir d'un geste réel.

* test créé : la personne crée un test depuis la réplique fautive (même fonction que le bouton de la page d'un appel) ;
* correction dans le brouillon : calculé à la lecture (l'agent a un brouillon) ; ce n'est jamais un clic ;
* suite rejouée : la personne rejoue toute la suite (même fonction que l'onglet Tests) ; si tout est vert, le problème passe « Testée » ;
* publication : la publication de l'agent (par une personne) passe les problèmes « Testée » de cet agent à « Publiée ».

Un test qui réussit de nouveau fait passer SON problème (« test:echec:<test> ») à « Testée » ; un nouveau cas sur un problème « Testée » ou
« Publiée » le rouvre (voir ``db/boucle_client``). ⛔ Ne lève jamais depuis les crochets (publication, rejeu).
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.db import db_client

DEPUIS_A_FAIRE = ("a_trier", "en_cours")


async def apres_une_publication(organisation_id: int, workflow_id: int) -> int:
    """Crochet de la publication : les problèmes « Testée » de l'agent passent « Publiée ». Ne lève jamais."""
    try:
        return await db_client.faire_avancer_les_ameliorations(
            organisation_id, workflow_id, de=("testee",), vers="publiee", temps="publie"
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[boucle] publication non reportée à « À améliorer » : {type(erreur).__name__}")
        return 0


async def apres_une_suite_verte(organisation_id: int, workflow_id: int) -> int:
    """Crochet du rejeu complet et vert : les problèmes à faire de l'agent passent « Testée »."""
    try:
        return await db_client.faire_avancer_les_ameliorations(
            organisation_id, workflow_id, de=DEPUIS_A_FAIRE, vers="testee", temps="rejoue"
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[boucle] suite verte non reportée à « À améliorer » : {type(erreur).__name__}")
        return 0


async def un_test_reussit_de_nouveau(organisation_id: int, workflow_id: int, cle: str) -> bool:
    try:
        return bool(
            await db_client.faire_avancer_les_ameliorations(
                organisation_id, workflow_id, de=DEPUIS_A_FAIRE, vers="testee", temps="rejoue", cle=cle
            )
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[boucle] test de nouveau vert non reporté : {type(erreur).__name__}")
        return False


def temps_de_l_avancement(probleme: dict[str, Any], *, a_un_brouillon: bool) -> list[dict[str, Any]]:
    """Les quatre temps à l'écran, dans l'ordre, chacun fait ou non."""
    av = probleme.get("avancement") or {}
    return [
        {"temps": "test_cree", "fait": bool(av.get("test_cree"))},
        {"temps": "brouillon", "fait": bool(a_un_brouillon) or bool(av.get("brouillon"))},
        {"temps": "rejoue", "fait": bool(av.get("rejoue"))},
        {"temps": "publie", "fait": bool(av.get("publie"))},
    ]
