"""[.mark] Builder : lire et écrire une ligne JSON de ``organization_configurations``.

Un seul point d'accès à la base pour tout le builder (les tests le remplacent par une mémoire).
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from api.db import db_client


async def lire(organization_id: int, cle: str) -> dict[str, Any] | None:
    ligne = await db_client.get_configuration(organization_id, cle)
    if ligne is None or not isinstance(ligne.value, dict):
        return None
    return ligne.value


class ConflitDEcriture(Exception):
    """Trop d'écritures simultanées sur la même ligne : rien n'a été perdu en silence, l'appelant peut recommencer."""


ESSAIS_MAX = 8


async def modifier(
    organization_id: int, cle: str, transformer: Callable[[dict[str, Any] | None], dict[str, Any] | None]
) -> dict[str, Any] | None:
    """Lit la ligne, applique ``transformer`` (PURE et rapide : elle peut être rejouée) et écrit seulement si la ligne n'a pas bougé
    entre-temps (revue R6). Deux écritures simultanées ne se perdent plus : la seconde repart de la valeur de la première.
    ``transformer`` rend la nouvelle valeur, ou ``None`` pour ne rien écrire ; ce qu'elle lève (un refus normal) remonte tel quel.
    ``ConflitDEcriture`` si la ligne bouge sans cesse."""
    for _ in range(ESSAIS_MAX):
        ligne = await db_client.get_configuration(organization_id, cle)
        attendu = ligne.value if ligne is not None else None
        courant = attendu if isinstance(attendu, dict) else None
        nouveau = transformer(copy.deepcopy(courant))
        if nouveau is None:
            return courant
        if await db_client.compare_and_set_configuration(organization_id, cle, attendu, nouveau):
            return nouveau
    raise ConflitDEcriture(f"The line {cle!r} keeps changing: try again.")


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
