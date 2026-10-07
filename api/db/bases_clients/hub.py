"""[.mark] SQL of the hub in the client's database (chantier l-agent-collegue, L4, H5 to H7).

- Each person's agenda in each calendar software is a row of ``lien_externe``
  (``objet_type = personne``, ``id_externe`` = the software's identifier of her agenda, H7).
- An appointment booked during a call is written AFTER the call, once the call and its
  request exist (``recevoir_appel``): a ``rendez_vous`` row, its ``lien_externe`` to the
  software's event, its address (with the position computed during the call, repli 7) and a
  CERTAIN mention of the person it was booked with (C11). Until this chantier no code wrote
  ``rendez_vous`` nor ``lien_externe`` (H6).

Idempotent: an appointment already linked to the software's event is never written twice
(a replay of the after-call writes nothing).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import asyncpg
from loguru import logger

OBJET_PERSONNE = "personne"
OBJET_RENDEZ_VOUS = "rendez_vous"


async def agendas_par_personne(
    connexion: asyncpg.Connection,
) -> dict[int, dict[str, str]]:
    """personne.id -> {software: agenda}."""
    sortie: dict[int, dict[str, str]] = {}
    for r in await connexion.fetch(
        "SELECT systeme, id_externe, objet_id FROM mark.lien_externe WHERE objet_type = $1 "
        "ORDER BY systeme",
        OBJET_PERSONNE,
    ):
        sortie.setdefault(r["objet_id"], {})[r["systeme"]] = r["id_externe"]
    return sortie


async def ecrire_agendas(
    connexion: asyncpg.Connection, par_personne: dict[int, dict[str, str]]
) -> None:
    """Replace the agendas of these people (personne.id -> {software: agenda}). Inside the
    caller's transaction (``ecrire_equipe``)."""
    if not par_personne:
        return
    await connexion.execute(
        "DELETE FROM mark.lien_externe WHERE objet_type = $1 AND objet_id = ANY($2::bigint[])",
        OBJET_PERSONNE,
        list(par_personne),
    )
    for personne_id, agendas in par_personne.items():
        for systeme, agenda in (agendas or {}).items():
            await connexion.execute(
                "INSERT INTO mark.lien_externe (systeme, id_externe, objet_type, objet_id) "
                "VALUES ($1, $2, $3, $4)",
                systeme,
                agenda,
                OBJET_PERSONNE,
                personne_id,
            )


async def agendas_des_personnes(
    connexion: asyncpg.Connection, systeme: str, cles: list[str] | None = None
) -> dict[str, str]:
    """person key -> her agenda in this software (active people only)."""
    lignes = await connexion.fetch(
        """
        SELECT p.cle, l.id_externe
        FROM mark.lien_externe l JOIN mark.personne p ON p.id = l.objet_id
        WHERE l.objet_type = $1 AND l.systeme = $2 AND p.actif AND p.cle IS NOT NULL
          AND ($3::text[] IS NULL OR p.cle = ANY($3::text[]))
        """,
        OBJET_PERSONNE,
        systeme,
        cles,
    )
    return {r["cle"]: r["id_externe"] for r in lignes}


def _moment(texte) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(texte))
        return moment if moment.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _cp(valeur) -> str | None:
    texte = str(valeur or "").strip()
    return texte if len(texte) == 5 and texte.isdigit() else None


def _coordonnee(valeur) -> Decimal | None:
    try:
        return Decimal(str(round(float(valeur), 6))) if valeur is not None else None
    except (TypeError, ValueError):
        return None


async def _intervenant(
    connexion: asyncpg.Connection, entree: dict
) -> tuple[int | None, str | None]:
    """The person the appointment is with: her key when the action named her, else the
    owner of the agenda it was booked in (H7)."""
    if entree.get("personne"):
        ligne = await connexion.fetchrow(
            "SELECT id, cle FROM mark.personne WHERE cle = $1", str(entree["personne"])
        )
        if ligne:
            return ligne["id"], ligne["cle"]
    if entree.get("agenda") and entree.get("systeme"):
        ligne = await connexion.fetchrow(
            """
            SELECT p.id, p.cle FROM mark.lien_externe l JOIN mark.personne p ON p.id = l.objet_id
            WHERE l.objet_type = $1 AND l.systeme = $2 AND l.id_externe = $3
            """,
            OBJET_PERSONNE,
            str(entree["systeme"]),
            str(entree["agenda"]),
        )
        if ligne:
            return ligne["id"], ligne["cle"]
    return None, None


async def ecrire_rendez_vous(
    connexion: asyncpg.Connection,
    appel_id: int | None,
    demande_id: int | None,
    contact_id: int | None,
    entrees: list[dict],
) -> dict:
    """The appointments booked during the call (``hub_rendez_vous`` of the record).
    ``{rendez_vous, deja, ignores, mentions, ids}``."""
    from api.db.bases_clients.gestes import ecrire_mentions

    bilan = {"rendez_vous": 0, "deja": 0, "ignores": 0, "mentions": 0, "ids": []}
    mentions = []
    for entree in entrees or []:
        if not isinstance(entree, dict):
            continue
        systeme, id_externe = entree.get("systeme"), entree.get("id_externe")
        debut, fin = _moment(entree.get("debut")), _moment(entree.get("fin"))
        if not (
            systeme and id_externe and debut and fin and fin > debut and demande_id
        ):
            bilan["ignores"] += 1
            logger.warning(
                f"[.mark] An appointment of call {appel_id} not written in the hub "
                f"(incomplete: {sorted(k for k, v in entree.items() if v)})"
            )
            continue
        async with connexion.transaction():
            deja = await connexion.fetchval(
                "SELECT objet_id FROM mark.lien_externe WHERE systeme = $1 AND id_externe = $2 "
                "AND objet_type = $3",
                str(systeme),
                str(id_externe),
                OBJET_RENDEZ_VOUS,
            )
            if deja is not None:
                bilan["deja"] += 1
                continue
            intervenant_id, cle = await _intervenant(connexion, entree)
            adresse_id = None
            adresse = (
                entree.get("adresse")
                if isinstance(entree.get("adresse"), dict)
                else None
            )
            if adresse and (adresse.get("commune") or adresse.get("voie")):
                adresse_id = await connexion.fetchval(
                    """
                    INSERT INTO mark.adresse (contact_id, numero, voie, code_postal, commune, code_insee,
                                              latitude, longitude, verifiee)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id
                    """,
                    contact_id,
                    (str(adresse["numero"])[:20] if adresse.get("numero") else None),
                    adresse.get("voie"),
                    _cp(adresse.get("code_postal")),
                    adresse.get("commune"),
                    _cp(adresse.get("code_insee")),
                    _coordonnee(adresse.get("latitude")),
                    _coordonnee(adresse.get("longitude")),
                    bool(adresse.get("verifiee")),
                )
                await connexion.execute(
                    "UPDATE mark.demande SET adresse_id = $2 WHERE id = $1 AND adresse_id IS NULL",
                    demande_id,
                    adresse_id,
                )
            rendez_vous_id = await connexion.fetchval(
                """
                INSERT INTO mark.rendez_vous (demande_id, intervenant_id, adresse_id, debut, fin, statut, origine)
                VALUES ($1, $2, $3, $4, $5, 'pose', 'agent') RETURNING id
                """,
                demande_id,
                intervenant_id,
                adresse_id,
                debut,
                fin,
            )
            await connexion.execute(
                "INSERT INTO mark.lien_externe (systeme, id_externe, objet_type, objet_id) "
                "VALUES ($1, $2, $3, $4)",
                str(systeme),
                str(id_externe),
                OBJET_RENDEZ_VOUS,
                rendez_vous_id,
            )
            await ecrire_suite_du_rendez_vous(
                connexion, rendez_vous_id, appel_id, entree, intervenant_id
            )
            bilan["rendez_vous"] += 1
            bilan["ids"].append(rendez_vous_id)
            if cle:
                mentions.append(
                    {
                        "cle": cle,
                        "source": "rendez_vous",
                        "certitude": "certaine",
                        "extrait": entree.get("motif") or entree.get("titre"),
                    }
                )
    bilan["mentions"] = await ecrire_mentions(connexion, appel_id, mentions)
    return bilan


async def ecrire_suite_du_rendez_vous(
    connexion: asyncpg.Connection,
    rendez_vous_id: int,
    appel_id: int | None,
    entree: dict,
    intervenant_id: int | None,
) -> None:
    """What else an appointment carries into the hub (the planner's attribution, L5).
    Nothing for an appointment booked by a plain connector action."""
    return
