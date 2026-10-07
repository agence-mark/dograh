"""[.mark] SQL of what the agent did for the team (chantier l-agent-collegue, L2, C8 to C10).

After the call (step « write »), from the record's ``equipe_gestes`` and ``equipe_assignation``:

- the request is ASSIGNED to the person it was passed on to (``demande.assignee_id``), only
  when no one assigned it yet (a human's choice is never overwritten);
- every transfer is a row of ``mark.transfert``: the person, the number dialled, when,
  whether she answered and how long it took (C10). Until now no code wrote that table.

Idempotent: a replay of the after-call writes nothing twice (a call's transfers are written
once; the assignee only when empty).
"""

from __future__ import annotations

from datetime import datetime

import asyncpg


async def ids_des_personnes(connexion: asyncpg.Connection, cles: list[str]) -> dict[str, int]:
    if not cles:
        return {}
    return {
        r["cle"]: r["id"]
        for r in await connexion.fetch(
            "SELECT id, cle FROM mark.personne WHERE cle = ANY($1::text[])", list(set(cles))
        )
    }


def _moment(iso) -> datetime | None:
    try:
        return datetime.fromisoformat(iso) if isinstance(iso, str) else None
    except ValueError:
        return None


async def ecrire_gestes(
    connexion: asyncpg.Connection,
    appel_id: int | None,
    demande_id: int | None,
    assignee: str | None,
    gestes: list[dict],
) -> dict:
    """``{assignee_id, transferts}``: what was written."""
    transferts = [g for g in gestes or [] if isinstance(g, dict) and g.get("geste") == "transfert"]
    ids = await ids_des_personnes(
        connexion, [g.get("personne") for g in transferts if g.get("personne")] + ([assignee] if assignee else [])
    )
    ecrit = {"assignee_id": None, "transferts": 0}
    async with connexion.transaction():
        if demande_id and assignee and ids.get(assignee):
            ecrit["assignee_id"] = await connexion.fetchval(
                "UPDATE mark.demande SET assignee_id = $2 WHERE id = $1 AND assignee_id IS NULL RETURNING assignee_id",
                demande_id,
                ids[assignee],
            )
        if appel_id and transferts:
            deja = await connexion.fetchval(
                "SELECT count(*) FROM mark.transfert WHERE appel_id = $1", appel_id
            )
            if not deja:
                for g in transferts:
                    await connexion.execute(
                        "INSERT INTO mark.transfert (appel_id, personne_id, numero_compose, debut, decroche, duree_s) "
                        "VALUES ($1, $2, $3, $4, $5, $6)",
                        appel_id,
                        ids.get(g.get("personne")),
                        g.get("numero"),
                        _moment(g.get("le")),
                        g.get("decroche"),
                        g.get("duree_s") if isinstance(g.get("duree_s"), int) else None,
                    )
                    ecrit["transferts"] += 1
    return ecrit


async def destinataire_assigne(connexion: asyncpg.Connection, cle: str | None) -> list[dict]:
    """C8: the person the request was passed on to, when active with a mail."""
    if not cle:
        return []
    return [
        dict(r)
        for r in await connexion.fetch(
            "SELECT cle, prenom, nom, mail FROM mark.personne "
            "WHERE cle = $1 AND actif AND coalesce(mail, '') <> ''",
            cle,
        )
    ]
