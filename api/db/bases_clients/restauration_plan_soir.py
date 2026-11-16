"""[.mark] Module Restauration, lot 26, M13 : le plan de salle du SOIR dans la base du client.

Ce que le plan enregistré (``resto_table``) ne garde pas : les tables RASSEMBLÉES pour un jour (et un service) et leurs positions du soir. Une ligne
par (établissement, jour, service) ; le plan de salle n'est jamais touché, « Revenir au plan » = ``retirer_plan_du_soir``. La capacité des
réservations (``restauration_reservation``) lit ces lignes : une table rassemblée est UNE table de la somme des couverts.

Le portail écrit la table directement (contrat § 1) ; ces fonctions sont celles du fork (agent, scripts, tests) : mêmes règles, mêmes refus.
Toutes prennent la connexion du rôle d'écriture puis ``etablissement_id`` (relu côté serveur, jamais d'un corps de requête).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import asyncpg

from api.db.bases_clients.restauration_carte import _json
from api.db.bases_clients.restauration_commun import Resultat, poser_session

POSITION_MAX = 100000  # une coordonnée du plan, en unités du plan (numeric(7, 2) à la base)


def _plan(ligne: asyncpg.Record) -> dict[str, Any]:
    return {
        "jour": ligne["jour"], "service_id": ligne["service_id"],
        "assemblages": [list(g) for g in (_json(ligne["assemblages"]) or [])], "positions": _json(ligne["positions"]) or {},
    }


async def plan_du_soir(connexion: asyncpg.Connection, etablissement_id: int, jour: date, service_id: int | None = None) -> dict[str, Any] | None:
    """Le plan du soir de CE jour et de CE service (``None`` : toute la journée), ``None`` si aucun n'est posé."""
    ligne = await connexion.fetchrow(
        "SELECT * FROM mark.resto_plan_soir WHERE site_id = $1 AND jour = $2 AND service_id IS NOT DISTINCT FROM $3", etablissement_id, jour, service_id
    )
    return _plan(ligne) if ligne else None


async def poser_plan_du_soir(
    connexion: asyncpg.Connection, etablissement_id: int, jour: date, assemblages: list[list[int]], positions: dict[int, dict[str, float]] | None = None,
    *, service_id: int | None = None, source: str = "mark", auteur: str | None = None,
) -> Resultat:
    """Pose (ou remplace) le plan du soir. ``assemblages`` : des groupes d'au moins deux tables ACTIVES de CET établissement, aucune table dans deux
    groupes ; ``positions`` : ``{id de table: {"x", "y"}}`` pour des tables de CET établissement. ``OK`` (``faits`` = le plan), ``INTROUVABLE`` (service
    ou table qui n'est pas de cet établissement), ``ARGUMENT_INVALIDE`` (``manque`` : ``assemblages`` ou ``positions``)."""
    if not isinstance(jour, date):
        return Resultat("ARGUMENT_INVALIDE", manque="jour")
    if not isinstance(assemblages, list) or any(
        not isinstance(g, list) or len(set(g)) < 2 or len(set(g)) != len(g) or any(not isinstance(i, int) or isinstance(i, bool) for i in g) for g in assemblages
    ):
        return Resultat("ARGUMENT_INVALIDE", {}, "Un groupe réunit au moins deux tables différentes.", "assemblages")
    tout = [i for g in assemblages for i in g]
    if len(set(tout)) != len(tout):
        return Resultat("ARGUMENT_INVALIDE", {}, "Une table ne peut être que dans un groupe.", "assemblages")
    positions = positions or {}
    for cle, p in positions.items():
        if (
            not isinstance(cle, int) or isinstance(cle, bool) or not isinstance(p, dict)
            or any(not isinstance(p.get(k), (int, float)) or isinstance(p.get(k), bool) or not 0 <= p[k] <= POSITION_MAX for k in ("x", "y"))
        ):
            return Resultat("ARGUMENT_INVALIDE", {}, "Une position est un x et un y.", "positions")
    async with connexion.transaction():
        await poser_session(connexion, source, auteur or f"plan_du_soir:{source}")
        if service_id is not None and not await connexion.fetchval("SELECT 1 FROM mark.resto_service WHERE id = $1 AND site_id = $2", service_id, etablissement_id):
            return Resultat("INTROUVABLE", {"service_id": service_id})
        voulues = set(tout) | set(positions)
        if voulues:
            connues = {r["id"] for r in await connexion.fetch("SELECT id FROM mark.resto_table WHERE site_id = $1 AND actif AND id = ANY($2::bigint[])", etablissement_id, list(voulues))}
            if connues != voulues:
                return Resultat("INTROUVABLE", {"tables": sorted(voulues - connues)})
        ligne = await connexion.fetchrow(
            "INSERT INTO mark.resto_plan_soir (site_id, jour, service_id, assemblages, positions) VALUES ($1, $2, $3, $4::jsonb, $5::jsonb) "
            "ON CONFLICT (site_id, jour, coalesce(service_id, 0)) DO UPDATE SET assemblages = EXCLUDED.assemblages, positions = EXCLUDED.positions "
            "RETURNING *",
            etablissement_id, jour, service_id, json.dumps([sorted(g) for g in assemblages]),
            json.dumps({str(k): {"x": p["x"], "y": p["y"]} for k, p in positions.items()}),
        )
    return Resultat("OK", _plan(ligne))


async def retirer_plan_du_soir(
    connexion: asyncpg.Connection, etablissement_id: int, jour: date, service_id: int | None = None, *, source: str = "mark", auteur: str | None = None
) -> Resultat:
    """« Revenir au plan » : le plan du soir de ce jour et de ce service disparaît, le plan enregistré n'a pas bougé. ``OK`` ou ``DEJA_FAIT`` (rien à retirer)."""
    async with connexion.transaction():
        await poser_session(connexion, source, auteur or f"plan_du_soir:{source}")
        retire = await connexion.fetchval(
            "DELETE FROM mark.resto_plan_soir WHERE site_id = $1 AND jour = $2 AND service_id IS NOT DISTINCT FROM $3 RETURNING 1", etablissement_id, jour, service_id
        )
    return Resultat("OK" if retire else "DEJA_FAIT", {"jour": jour, "service_id": service_id})
