"""[.mark] Lot F8 : les modules de l'agent dans la base du client (migration 020).

Dograh écrit ici ce que son registre déclare (``module``) et sur quels agents chaque module est allumé
(``module_agent``, calculé) : c'est ce que lit ``v_portail_modules`` (D121). Le magasin commun des réglages
terrain (``module_reglage``) n'a encore aucune clé déclarée (aucun réglage terrain inventé) : la base refuse
toute valeur qu'un module ne déclare pas. Avant la 020 : rien, jamais une erreur.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

import asyncpg


async def modules_presents(connexion: asyncpg.Connection) -> bool:
    """A database before the 020 has no modules (and is not an error)."""
    return bool(await connexion.fetchval("SELECT to_regclass('mark.module') IS NOT NULL"))


async def ecrire_catalogue(
    connexion: asyncpg.Connection, modules: Iterable[tuple[str, str, list[dict]]]
) -> None:
    """The registry's modules: (code, label, declared terrain settings). Written as the fork declares them;
    a module the fork no longer declares is removed unless values were stored under it (they stay)."""
    if not await modules_presents(connexion):
        return
    liste = list(modules)
    async with connexion.transaction():
        for code, libelle, terrain in liste:
            await connexion.execute(
                "INSERT INTO mark.module AS m (code, libelle, reglages_terrain) VALUES ($1, $2, $3::jsonb) "
                "ON CONFLICT (code) DO UPDATE SET libelle = EXCLUDED.libelle, "
                "reglages_terrain = EXCLUDED.reglages_terrain, modifie_le = now() "
                "WHERE m.libelle IS DISTINCT FROM EXCLUDED.libelle "
                "OR m.reglages_terrain IS DISTINCT FROM EXCLUDED.reglages_terrain",
                code, libelle, json.dumps(terrain, ensure_ascii=False),
            )
        await connexion.execute(
            "DELETE FROM mark.module m WHERE NOT (m.code = ANY($1::text[])) "
            "AND NOT EXISTS (SELECT 1 FROM mark.module_reglage r WHERE r.module_code = m.code)",
            [code for code, _, _ in liste],
        )


async def ecrire_agents_des_modules(
    connexion: asyncpg.Connection, agents: dict[str, Iterable[int]]
) -> None:
    """On which agents each module is on (agents by their Dograh identifier). Computed by Dograh, never
    typed. An agent the database does not know yet is left out, as for the objects (019)."""
    if not await modules_presents(connexion):
        return
    async with connexion.transaction():
        await connexion.execute("DELETE FROM mark.module_agent")
        for code, ids in agents.items():
            liste = sorted({int(a) for a in ids})
            if not liste:
                continue
            await connexion.execute(
                "INSERT INTO mark.module_agent (module_code, agent_id) "
                "SELECT m.code, a.id FROM mark.module m JOIN mark.agent a ON a.dograh_workflow_id = ANY($2::integer[]) "
                "WHERE m.code = $1 ON CONFLICT DO NOTHING",
                code, liste,
            )
