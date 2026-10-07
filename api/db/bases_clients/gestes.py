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
    """``{assignee_id, transferts, mentions}``: what was written."""
    transferts = [g for g in gestes or [] if isinstance(g, dict) and g.get("geste") == "transfert"]
    ids = await ids_des_personnes(
        connexion, [g.get("personne") for g in transferts if g.get("personne")] + ([assignee] if assignee else [])
    )
    ecrit = {"assignee_id": None, "transferts": 0, "mentions": 0}
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
    # L3 (C11): each gesture is a certain mention of the person.
    ecrit["mentions"] = await ecrire_mentions(connexion, appel_id, mentions_des_gestes(gestes))
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


# --------------------------------------------------------------------------- #
# The mentions (L3, C11): every time a person of the team is concerned by a call
# --------------------------------------------------------------------------- #

async def ecrire_mentions(
    connexion: asyncpg.Connection, appel_id: int | None, mentions: list[dict]
) -> int:
    """``mentions``: ``{cle, source, certitude, extrait?}``. One row per call, person and
    source; a replay writes nothing twice, a surer finding replaces a less sure one.
    Returns how many rows were written or made surer."""
    if not appel_id or not mentions:
        return 0
    ids = await ids_des_personnes(connexion, [m.get("cle") for m in mentions if m.get("cle")])
    ecrites = 0
    for m in mentions:
        personne_id = ids.get(m.get("cle"))
        if personne_id is None:
            continue
        statut = await connexion.execute(
            """
            INSERT INTO mark.mention (appel_id, personne_id, source, certitude, extrait)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (appel_id, personne_id, source) DO UPDATE
                SET certitude = EXCLUDED.certitude, extrait = EXCLUDED.extrait
                WHERE (CASE mark.mention.certitude WHEN 'certaine' THEN 2 WHEN 'detectee' THEN 1 ELSE 0 END)
                    < (CASE EXCLUDED.certitude WHEN 'certaine' THEN 2 WHEN 'detectee' THEN 1 ELSE 0 END)
            """,
            appel_id,
            personne_id,
            m["source"],
            m["certitude"],
            (m.get("extrait") or None) and str(m["extrait"])[:200],
        )
        ecrites += int(statut.split()[-1]) if statut else 0
    return ecrites


def mentions_des_gestes(gestes: list[dict]) -> list[dict]:
    """C11: a gesture made by the code is a CERTAIN mention (transfer, passing on)."""
    sources = {"transfert": "transfert", "transmission": "transmission"}
    return [
        {"cle": g["personne"], "source": sources[g["geste"]], "certitude": "certaine",
         # R-3: a passing on after a failed transfer is a call-back to make, said in her mention.
         "extrait": (
             " : ".join(x for x in ("À rappeler", g.get("motif")) if x)
             if g.get("rappel")
             else g.get("motif")
         )}
        for g in gestes or []
        if isinstance(g, dict) and g.get("geste") in sources and g.get("personne")
    ]


# --------------------------------------------------------------------------- #
# The access of each employee (L3, C14, C15): the base is ready, the accounts come with
# Metabase (chantier Scaleway). With the OWNER's connection (it creates the roles).
# --------------------------------------------------------------------------- #


async def donner_acces(
    connexion_proprietaire: asyncpg.Connection,
    cle: str,
    mot_de_passe: str,
    sites: list[str] | None = None,
) -> str:
    """The employee's login role (``<base>_p_<id>``): her mentions and the calls of her
    establishment (and of ``sites``, keys). The password is never stored nor logged."""
    return await connexion_proprietaire.fetchval(
        "SELECT mark.donner_acces($1, $2, $3::text[])", cle, mot_de_passe, sites
    )


async def retirer_acces(connexion_proprietaire: asyncpg.Connection, cle: str) -> None:
    await connexion_proprietaire.execute("SELECT mark.retirer_acces($1)", cle)


async def personnes_de_la_base(connexion: asyncpg.Connection) -> list:
    """The people of the team (key, first name, name): labels of the run window."""
    return await connexion.fetch("SELECT cle, prenom, nom FROM mark.personne")


async def mentions_de_l_appel(connexion: asyncpg.Connection, appel_id: int) -> list:
    """The mentions of one call, the certain ones first."""
    return await connexion.fetch(
        """
        SELECT p.cle, m.source, m.certitude, m.extrait
        FROM mark.mention m JOIN mark.personne p ON p.id = m.personne_id
        WHERE m.appel_id = $1
        ORDER BY CASE m.certitude WHEN 'certaine' THEN 0 WHEN 'detectee' THEN 1 ELSE 2 END, m.id
        """,
        appel_id,
    )
