"""[.mark] S1 / D177 / D185 : le plafond par mois d'un jeton de widget, en conversations ET en minutes.

La réservation est une requête atomique sur la table d'usage (jeton, mois). Le premier plafond atteint arrête.
Les secondes parlées sont versées à la fin de la conversation (``verser_la_duree``) ; le total à vie reste sur
``embed_tokens.usage_count`` (inchangé). Un mois nouveau repart de zéro sans aucune tâche de nuit : c'est une
autre ligne.
"""

from __future__ import annotations

from datetime import datetime

from api.db import db_client
from api.db.site_client import mois_de
from api.services.site_mark.reglages import ReglagesMark


async def reserver(embed_token_id: int, reglages: ReglagesMark, maintenant: datetime | None = None) -> bool:
    return await db_client.reserver_une_conversation(
        embed_token_id,
        mois_de(maintenant),
        reglages.plafond_conversations_mois,
        reglages.plafond_minutes_mois * 60,
    )


async def rendre(embed_token_id: int, maintenant: datetime | None = None) -> None:
    await db_client.rendre_une_conversation(embed_token_id, mois_de(maintenant))


async def verser_la_duree(embed_token_id: int, secondes: int, maintenant: datetime | None = None) -> None:
    await db_client.ajouter_secondes(embed_token_id, mois_de(maintenant), int(secondes))
