"""[.mark] SQL of the client's database: its state on screen and its retention (B2, B6)."""

from __future__ import annotations

from datetime import datetime

import asyncpg

from api.db.bases_clients.connexion import version_de
from api.schemas.base_client import Conservation


async def lire_etat(
    connexion: asyncpg.Connection,
) -> tuple[int | None, datetime | None, list[Conservation]]:
    """(schema version, last write in the journal, retention policy)."""
    version = await version_de(connexion)
    if not version:
        return None, None, []
    derniere = await connexion.fetchval("SELECT max(le) FROM mark.journal_modif")
    conservation = [
        Conservation(
            table_nom=r["table_nom"],
            duree_jours=int(r["jours"]),
            colonne_date=r["colonne_date"],
            source=r["source"],
        )
        for r in await connexion.fetch(
            "SELECT table_nom, extract(epoch FROM duree) / 86400 AS jours, colonne_date, source "
            "FROM mark.politique_conservation ORDER BY table_nom"
        )
    ]
    return version, derniere, conservation


async def regler_conservation(
    connexion: asyncpg.Connection, lignes: list[Conservation], auteur: str
) -> None:
    """Durations only, each change written to ``journal_modif``. ``ValueError``: a table
    without a policy in this database (nothing written)."""
    async with connexion.transaction():
        await connexion.execute(
            "SELECT set_config('mark.auteur', $1, true)", auteur[:200]
        )
        connues = {
            r["table_nom"]
            for r in await connexion.fetch(
                "SELECT table_nom FROM mark.politique_conservation"
            )
        }
        for ligne in lignes:
            if ligne.table_nom not in connues:
                raise ValueError(
                    f"« {ligne.table_nom} » has no retention policy in this database."
                )
            avant = await connexion.fetchval(
                "SELECT extract(epoch FROM duree) / 86400 FROM mark.politique_conservation WHERE table_nom = $1",
                ligne.table_nom,
            )
            if int(avant) == ligne.duree_jours:
                continue
            await connexion.execute(
                "UPDATE mark.politique_conservation SET duree = make_interval(days => $2), "
                "decidee_le = current_date, source = $3 WHERE table_nom = $1",
                ligne.table_nom,
                ligne.duree_jours,
                f"Dograh, {auteur}",
            )
            await connexion.execute(
                "INSERT INTO mark.journal_modif (table_nom, ligne_id, champ, avant, apres, auteur) "
                "VALUES ('politique_conservation', $1, 'duree', to_jsonb($2::int), to_jsonb($3::int), $4)",
                ligne.table_nom,
                int(avant),
                ligne.duree_jours,
                auteur,
            )
