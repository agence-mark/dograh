"""[.mark] Module Restauration, lot 10 : l'HEURE changée par la caisse (temps de préparation allongé).

Quand la caisse confirme une autre heure que celle de notre commande, le classeur la reprend (source « caisse », journal), l'événement ``commande.heure`` part (le Rush
et Commandes l'affichent sans recharger), et l'appelant est PRÉVENU si l'envoi « heure changée » de l'établissement est allumé (éteint par défaut, E-18). Rejouable : la
même heure relue ne change rien et n'émet rien.

L'envoi du message lui-même appartient au module des envois (SMS, mail), qui n'existe pas encore dans le fork : ``ENVOYEUR`` est la prise où il se branche. Tant qu'il
n'est pas branché, un envoi allumé est DIT au journal (jamais simulé, jamais avalé) et le résultat de ``prevenir_l_appelant`` est faux.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime

import asyncpg
from loguru import logger

from api.db.bases_clients import restauration_liaison as liaison_db
from api.services.restauration import flux

DECLENCHEUR = "heure_changee"
# ``ENVOYEUR(connexion, etablissement_id, numero, envoi, heure)`` : posé par le module des envois quand il existe.
Envoyeur = Callable[[asyncpg.Connection, int, str, dict, datetime], Awaitable[None]]
ENVOYEUR: Envoyeur | None = None


async def prevenir_l_appelant(connexion: asyncpg.Connection, etablissement_id: int, numero: str, heure: datetime) -> bool:
    """Vrai si l'appelant a été prévenu. Faux : l'envoi est éteint (par défaut), ou le module d'envoi n'est pas branché (dit au journal)."""
    envoi = await liaison_db.envoi_actif(connexion, etablissement_id, "sms", DECLENCHEUR)
    if envoi is None:
        return False
    if ENVOYEUR is None:
        logger.warning(f"[.mark] Order {numero}: the 'time changed' message is on but no sending module is plugged: caller not told")
        return False
    try:
        await ENVOYEUR(connexion, etablissement_id, numero, envoi, heure)
    except Exception as erreur:  # noqa: BLE001 -- ne casse jamais la reprise de l'heure
        logger.error(f"[.mark] Order {numero}: the 'time changed' message failed: {type(erreur).__name__}")
        return False
    return True


async def appliquer_l_heure(
    connexion: asyncpg.Connection, organization_id: int | None, etablissement_id: int, numero: str | uuid.UUID, heure: datetime | None
) -> bool:
    """Reprend l'heure confirmée par la caisse pour CETTE commande de CET établissement. Rend ``True`` si elle a changé (``commande.heure`` émis)."""
    if heure is None or heure.tzinfo is None:
        return False
    if not await liaison_db.poser_l_heure_annoncee(connexion, etablissement_id, numero, heure, "caisse"):
        return False
    if organization_id is not None:
        await flux.emettre(organization_id, etablissement_id, "commande.heure", {"numero": str(numero), "heure_annoncee": heure})
    await prevenir_l_appelant(connexion, etablissement_id, str(numero), heure)
    return True
