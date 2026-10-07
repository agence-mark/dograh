"""[.mark] SQL of the client's database for the after-call (chantier l-agent-travaille, L4, A2, A8).

Every write goes through a function of the client's schema (migration ``004``):
``mark.recevoir_appel`` (the call, its contact, its request, its record, its turns,
its transcript; a replay creates nothing), ``mark.ecrire_synthese``, ``mark.nuit``
(purge table by table, the day's counters, the proof kept in ``execution_tache``).
The ``action`` rows say what was sent for a request (mail, SMS, webhook…) and how it went.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import asyncpg


async def recevoir_appel(connexion: asyncpg.Connection, envoi: dict) -> dict:
    """``{appel_id, demande_id, contact_id, doublon, autre_demande_ouverte_id}``."""
    brut = await connexion.fetchval(
        "SELECT mark.recevoir_appel($1::jsonb)", json.dumps(envoi, default=str)
    )
    return json.loads(brut) if isinstance(brut, str) else dict(brut)


async def ecrire_synthese(
    connexion: asyncpg.Connection, appel_id: int, texte: str
) -> None:
    await connexion.execute("SELECT mark.ecrire_synthese($1, $2)", appel_id, texte)


async def destinataires_de(
    connexion: asyncpg.Connection, sujet: str | None, etablissement: str | None
) -> list[dict]:
    """Who receives the mail of a request (A4): the people routed to its subject, in
    their order; if none (no subject, or no one routed), the default recipients of its
    establishment, then those of the whole company. Active people with a mail only."""
    if sujet:
        lignes = await connexion.fetch(
            """
            SELECT p.cle, p.prenom, p.nom, p.mail
            FROM mark.sujet s
            JOIN mark.personne_sujet ps ON ps.sujet_id = s.id
            JOIN mark.personne p ON p.id = ps.personne_id
            WHERE s.code = $1 AND s.actif AND p.actif AND coalesce(p.mail, '') <> ''
            ORDER BY ps.priorite, p.id
            """,
            sujet,
        )
        if lignes:
            return [dict(r) for r in lignes]
    lignes = await connexion.fetch(
        """
        SELECT p.cle, p.prenom, p.nom, p.mail
        FROM mark.personne p
        LEFT JOIN mark.site s ON s.id = p.site_id
        WHERE p.actif AND p.destinataire_defaut AND coalesce(p.mail, '') <> ''
          AND (p.site_id IS NULL OR s.cle = $1)
        ORDER BY (p.site_id IS NULL), p.id
        """,
        etablissement,
    )
    return [dict(r) for r in lignes]


async def sujets_actifs(connexion: asyncpg.Connection) -> list[dict]:
    """The active subjects and their trigger words: the routing of a request (A4)."""
    return [
        dict(r)
        for r in await connexion.fetch(
            "SELECT code, libelle, mots_declencheurs, urgent FROM mark.sujet WHERE actif ORDER BY id"
        )
    ]


async def noter_action(
    connexion: asyncpg.Connection,
    *,
    appel_id: int | None,
    demande_id: int | None,
    canal: str,
    destinataire: str | None,
    statut: str,
    erreur: str | None = None,
    reessais: int = 0,
) -> int:
    """One row per sending (A9): what was sent, to whom, and how it went."""
    envoyee = datetime.now().astimezone() if statut in ("envoyee", "delivree") else None
    return await connexion.fetchval(
        """
        INSERT INTO mark.action (appel_id, demande_id, canal, destinataire, statut, envoyee_le, reessais, erreur)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id
        """,
        appel_id,
        demande_id,
        canal,
        destinataire,
        statut,
        envoyee,
        reessais,
        (erreur or None) and erreur[:2000],
    )


async def a_rappeler(
    connexion: asyncpg.Connection, etablissement: str | None = None
) -> list[dict]:
    """What still waits for a call-back (``v_a_rappeler``), for the recap mail (A4)."""
    lignes = await connexion.fetch(
        """
        SELECT v.id, v.creee_le, v.type, v.priorite, v.degre_urgence, v.resume, v.site,
               v.assignee, v.contact_nom, v.telephone, v.autre_demande_ouverte_id
        FROM mark.v_a_rappeler v
        LEFT JOIN mark.site s ON s.nom = v.site
        WHERE $1::text IS NULL OR s.cle = $1
        """,
        etablissement,
    )
    return [dict(r) for r in lignes]


async def nuit(connexion: asyncpg.Connection) -> dict[str, Any]:
    """The night task (A8): ``{execution_id, purge: {table: rows deleted}}``. The proof
    stays in ``mark.execution_tache``."""
    brut = await connexion.fetchval("SELECT mark.nuit()")
    return json.loads(brut) if isinstance(brut, str) else dict(brut)


async def derniere_nuit(connexion: asyncpg.Connection) -> dict | None:
    ligne = await connexion.fetchrow(
        "SELECT id, debut, fin, statut, resultat FROM mark.execution_tache "
        "WHERE tache = 'nuit' ORDER BY debut DESC LIMIT 1"
    )
    if ligne is None:
        return None
    sortie = dict(ligne)
    if isinstance(sortie.get("resultat"), str):
        sortie["resultat"] = json.loads(sortie["resultat"])
    return sortie
