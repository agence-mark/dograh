"""[.mark] Le journal des copies d'agents et le verrou : une copie rejouée ne se refait pas.

Une ligne par copie dans ``organization_configurations`` DU LABO (aucune migration), jamais dans l'organisation d'un client :

    ``MARK_COPIE:<sens>:<empreinte>``  ->  ``{"agent_id": <id de la copie>, "cible": <organisation de la copie>, "le": "<date>"}``

L'empreinte (SHA-256 tronqué) porte ``sens``, l'organisation d'origine, l'agent d'origine et l'organisation de la copie : le Labo n'écrit
donc l'identifiant d'aucun client en clair dans sa propre clé. Le verrou est un verrou consultatif de transaction par empreinte.
"""

from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from api.db import db_client
from api.services.builder import stock

PREFIXE = "MARK_COPIE:"


def empreinte(sens: str, source_org: int, agent_id: int, cible_org: int) -> str:
    brut = f"{sens}|{source_org}|{agent_id}|{cible_org}".encode()
    return hashlib.sha256(brut).hexdigest()[:32]


def cle(sens: str, source_org: int, agent_id: int, cible_org: int) -> str:
    return f"{PREFIXE}{sens}:{empreinte(sens, source_org, agent_id, cible_org)}"


async def lire(labo_id: int, sens: str, source_org: int, agent_id: int, cible_org: int) -> dict | None:
    return await stock.lire(labo_id, cle(sens, source_org, agent_id, cible_org))


async def noter(labo_id: int, sens: str, source_org: int, agent_id: int, cible_org: int, copie_id: int) -> None:
    await stock.ecrire(
        labo_id,
        cle(sens, source_org, agent_id, cible_org),
        {"agent_id": copie_id, "cible": cible_org, "le": datetime.now(UTC).isoformat()},
    )


async def oublier(labo_id: int, sens: str, source_org: int, agent_id: int, cible_org: int) -> None:
    await stock.supprimer(labo_id, cle(sens, source_org, agent_id, cible_org))


@asynccontextmanager
async def verrou(sens: str, source_org: int, agent_id: int, cible_org: int):
    """Deux copies simultanées du même agent vers la même cible s'attendent : la seconde trouve la première dans le journal."""
    async with db_client.verrou_de_copie_d_agent(empreinte(sens, source_org, agent_id, cible_org)):
        yield
