"""[.mark] SQL of the client's database for what the portal reads next to a call (chantier
agents-specialises, lots 8 and 9): the incidents, the outcome of each transfer, which agent
serves which establishment, which agents are attached to the portal.

Every function here is safe on a database still at version 14 (a table or a function of the 015
missing): it does nothing and says so, because a call is never worth an error (R1: the test
sees the empty result, the call goes on).
"""

from __future__ import annotations

from datetime import datetime

import asyncpg
from loguru import logger

CANAL_TRANSFERT = "transfert"
# Ce que dit l'issue d'un transfert : décroché = abouti ; tout le reste est un échec dont l'issue est la cause.
ISSUE_ABOUTIE = "decroche"


def _moment(valeur) -> datetime | None:
    if isinstance(valeur, datetime):
        return valeur
    if isinstance(valeur, str) and valeur.strip():
        try:
            return datetime.fromisoformat(valeur.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


async def noter_incident(
    connexion: asyncpg.Connection,
    *,
    appel_id: int | None,
    brique: str,
    cause: str,
    debut: datetime | str | None = None,
    fin: datetime | str | None = None,
    correctif: str | None = None,
) -> int | None:
    """One incident (a brick and a cause), linked to the call when there is one. The same brick
    and cause seen within 30 minutes is the SAME incident. Replayable. ``None``: not written."""
    try:
        return await connexion.fetchval(
            "SELECT mark.noter_incident($1, $2, $3, $4, $5, $6)",
            appel_id,
            (brique or "")[:200] or None,
            (cause or "")[:500] or None,
            _moment(debut) or datetime.now().astimezone(),
            _moment(fin),
            correctif,
        )
    except Exception as erreur:  # noqa: BLE001 -- an incident is never worth an error
        logger.warning(
            f"[.mark] Incident not written ({type(erreur).__name__}): {erreur}"
        )
        return None


async def ecrire_incidents(
    connexion: asyncpg.Connection, appel_id: int | None, incidents: list[dict]
) -> int:
    """The incidents the analysis found in a call. Returns how many were handled."""
    n = 0
    for incident in incidents or []:
        if not isinstance(incident, dict) or not incident.get("cause"):
            continue
        if await noter_incident(
            connexion,
            appel_id=appel_id,
            brique=incident.get("brique") or "",
            cause=incident["cause"],
            debut=incident.get("debut"),
            correctif=incident.get("correctif"),
        ):
            n += 1
    return n


async def ecrire_issues_de_transfert(
    connexion: asyncpg.Connection,
    appel_id: int | None,
    demande_id: int | None,
    transferts: list[dict],
    debut_de_l_appel: datetime | str | None = None,
) -> int:
    """D82: one ``action`` row per transfer attempt (a person, the establishment's number, a
    referral): the channel « transfert », the target, and how it ended. An answered transfer is
    delivered; every other outcome is a failure whose error is the outcome (``repondeur``,
    ``sans_reponse``, ``occupe``, ``echec``). Written ONCE: a replay finds the row (same call,
    target and moment). Returns how many rows were written."""
    if not appel_id or not transferts:
        return 0
    ecrites = 0
    repli = _moment(debut_de_l_appel)
    for t in transferts:
        if not isinstance(t, dict) or not t.get("issue"):
            continue
        quand = _moment(t.get("le")) or repli
        issue = str(t["issue"])[:40]
        abouti = issue == ISSUE_ABOUTIE
        cible = str(t["cible"])[:200] if t.get("cible") else None
        try:
            statut = await connexion.execute(
                """
                INSERT INTO mark.action (appel_id, demande_id, canal, destinataire, statut,
                                         envoyee_le, delivree_le, erreur)
                SELECT $1, $2, $3, $4, $5, $6, $7, $8
                WHERE NOT EXISTS (
                    SELECT 1 FROM mark.action
                    WHERE appel_id = $1 AND canal = $3 AND destinataire IS NOT DISTINCT FROM $4
                      AND envoyee_le IS NOT DISTINCT FROM $6::timestamptz
                )
                """,
                appel_id,
                demande_id,
                CANAL_TRANSFERT,
                cible,
                "delivree" if abouti else "echec",
                quand,
                quand if abouti else None,
                None if abouti else issue,
            )
        except Exception as erreur:  # noqa: BLE001 -- the outcome of a transfer is never worth an error
            logger.warning(
                f"[.mark] Transfer outcome not written ({type(erreur).__name__}): {erreur}"
            )
            continue
        ecrites += int(statut.split()[-1]) if statut else 0
    return ecrites


async def noms_des_agents_manquants(agents: list[dict], nom_de) -> list[dict]:
    """The agents of a call with the names Dograh knows (``nom_de(workflow_id)``, scoped to the
    organization by the caller). A name that cannot be read stays empty: the database keeps the
    one it already has, or « Agent »."""
    sortie = []
    for agent in agents or []:
        agent = dict(agent)
        if not agent.get("nom") and agent.get("dograh_workflow_id") is not None:
            try:
                agent["nom"] = await nom_de(agent["dograh_workflow_id"])
            except Exception:  # noqa: BLE001
                agent["nom"] = None
        sortie.append(agent)
    return sortie


async def ecrire_agent_site(
    connexion: asyncpg.Connection,
    *,
    dograh_workflow_id: int,
    nom: str | None,
    site_cle: str | None,
) -> bool:
    """``agent_site`` follows the agent's choice (M3, F1): the agent's row is made when it does not
    exist yet, and its establishment is exactly the fiche it chose (none = no row). Never a
    second establishment for one agent. ``False``: a fiche unknown to the database (the choice
    is kept by Dograh, the portal links nothing)."""
    async with connexion.transaction():
        agent_id = await connexion.fetchval(
            """
            INSERT INTO mark.agent (dograh_workflow_id, nom) VALUES ($1, coalesce(nullif($2, ''), 'Agent'))
            ON CONFLICT (dograh_workflow_id) DO UPDATE
                SET nom = CASE WHEN nullif($2, '') IS NOT NULL THEN EXCLUDED.nom ELSE mark.agent.nom END
            RETURNING id
            """,
            dograh_workflow_id,
            nom,
        )
        site_id = (
            await connexion.fetchval(
                "SELECT id FROM mark.site WHERE cle = $1", site_cle
            )
            if site_cle
            else None
        )
        if site_id is None:
            await connexion.execute(
                "DELETE FROM mark.agent_site WHERE agent_id = $1", agent_id
            )
            return site_cle is None
        await connexion.execute(
            "DELETE FROM mark.agent_site WHERE agent_id = $1 AND site_id <> $2",
            agent_id,
            site_id,
        )
        await connexion.execute(
            "INSERT INTO mark.agent_site (agent_id, site_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            agent_id,
            site_id,
        )
        return True


async def regler_rattachement(
    connexion: asyncpg.Connection, agents: dict[int, str | None], rattache: bool
) -> list[int]:
    """Attach (or detach) agents to the portal: ``agent.rattache_le`` (M9, D90). ``agents``: the
    Dograh id of each agent and its name. The row is made when missing. Returns the ids changed."""
    changes: list[int] = []
    async with connexion.transaction():
        for workflow_id, nom in agents.items():
            ligne = await connexion.fetchrow(
                """
                INSERT INTO mark.agent (dograh_workflow_id, nom) VALUES ($1, coalesce(nullif($2, ''), 'Agent'))
                ON CONFLICT (dograh_workflow_id) DO UPDATE
                    SET nom = CASE WHEN nullif($2, '') IS NOT NULL THEN EXCLUDED.nom ELSE mark.agent.nom END
                RETURNING id, rattache_le
                """,
                workflow_id,
                nom,
            )
            if rattache and ligne["rattache_le"] is None:
                await connexion.execute(
                    "UPDATE mark.agent SET rattache_le = now() WHERE id = $1",
                    ligne["id"],
                )
                changes.append(workflow_id)
            elif not rattache and ligne["rattache_le"] is not None:
                await connexion.execute(
                    "UPDATE mark.agent SET rattache_le = NULL WHERE id = $1",
                    ligne["id"],
                )
                changes.append(workflow_id)
    return changes


async def agents_rattaches(connexion: asyncpg.Connection) -> set[int]:
    """The Dograh ids of the agents attached to the portal (a database at version 14: none)."""
    try:
        lignes = await connexion.fetch(
            "SELECT dograh_workflow_id FROM mark.agent WHERE rattache_le IS NOT NULL"
        )
    except (asyncpg.UndefinedColumnError, asyncpg.UndefinedTableError):
        return set()
    return {r["dograh_workflow_id"] for r in lignes}
