"""[.mark] Builder : lire et écrire une ligne JSON de ``organization_configurations``.

Un seul point d'accès à la base pour tout le builder (les tests le remplacent par une mémoire).
"""

from __future__ import annotations

from typing import Any

from api.db import db_client


async def lire(organization_id: int, cle: str) -> dict[str, Any] | None:
    ligne = await db_client.get_configuration(organization_id, cle)
    if ligne is None or not isinstance(ligne.value, dict):
        return None
    return ligne.value


async def ecrire(organization_id: int, cle: str, valeur: dict[str, Any]) -> None:
    await db_client.upsert_configuration(organization_id, cle, valeur)


async def supprimer(organization_id: int, cle: str) -> bool:
    return bool(await db_client.delete_configuration(organization_id, cle))


async def lister(organization_id: int, prefixe: str) -> list[tuple[str, dict[str, Any]]]:
    """Les lignes dont la clé commence par ``prefixe`` (triées par clé)."""
    # Revue R4 : le filtre par préfixe est fait par la base (``key LIKE``), jamais en chargeant toutes les lignes de l'organisation.
    lignes = await db_client.get_configurations_by_prefix(organization_id, prefixe)
    trouvees = [
        (ligne.key, ligne.value)
        for ligne in lignes
        if isinstance(ligne.key, str) and ligne.key.startswith(prefixe) and isinstance(ligne.value, dict)
    ]
    return sorted(trouvees, key=lambda paire: paire[0])
