"""[.mark] cloture-code, D152 : « Appliquer à tous les établissements », côté base du client.

Trois familles vivent dans la base du client : un champ des règles du planificateur (la fenêtre du tour
de rôle comprise), un type de rendez-vous, un réglage terrain d'un module. Chacune est recopiée de
l'établissement source dans TOUS les autres établissements actifs de la base, en UNE transaction : une
erreur au milieu n'en change aucun.

``mark.auteur`` est posé comme dans les autres écritures du référentiel : les déclencheurs journalisent
(``journal_modif``, ``module_reglage_historique``) ligne par ligne, donc établissement par établissement.
Aucune restriction « ceux que le compte voit » : c'est Dograh, il fait tout ; ce filtre est celui du portail.

Les familles de la fiche (horaires, adresse, annonces, phrases) ne passent pas ici : elles s'écrivent par
le catalogue des établissements (``api/services/etablissements/appliquer_a_tous.py``).
"""

from __future__ import annotations

import asyncpg

from api.db.bases_clients.planificateur import (
    COLONNES,
    ReferenceInconnue,
    ReglagesPlanificateur,
    _ecrire_reglages,
    _reglages,
)


async def _declare(connexion: asyncpg.Connection, module: str, cle: str) -> bool:
    """Le module déclare-t-il ce réglage terrain dans ``module_reglage`` ? (la même règle que la base)"""
    return bool(
        await connexion.fetchval(
            "SELECT EXISTS (SELECT 1 FROM mark.module m, jsonb_array_elements(m.reglages_terrain) d "
            "WHERE m.code = $1 AND d ->> 'cle' = $2 AND d ->> 'lieu' = 'module_reglage')",
            module,
            cle,
        )
    )


async def appliquer_a_tous(
    connexion: asyncpg.Connection, source: str, reglage: str, cle: str, auteur: str
) -> list[str]:
    """Recopie ``reglage``/``cle`` de ``source`` dans tous les autres établissements actifs ; rend leurs
    identifiants, dans l'ordre. ``ReferenceInconnue`` (rien d'écrit) : source, type, module ou clé inconnus."""
    async with connexion.transaction():
        await connexion.execute("SELECT set_config('mark.auteur', $1, true)", auteur[:200])
        sites = {
            r["cle"]: r["id"]
            for r in await connexion.fetch(
                "SELECT id, cle FROM mark.site WHERE cle IS NOT NULL AND actif ORDER BY ordre, id"
            )
        }
        if source not in sites:
            raise ReferenceInconnue(f"Unknown establishment « {source} ».")
        cibles = {c: i for c, i in sites.items() if c != source}
        if reglage == "planificateur":
            await _regles(connexion, sites[source], cibles, cle)
        elif reglage == "type":
            await _type(connexion, sites[source], cibles, cle)
        elif reglage == "module":
            await _module(connexion, sites[source], cibles, cle)
        else:
            raise ReferenceInconnue(f"« {reglage} » is not kept in the client's database.")
        return list(cibles)


async def _regles(connexion: asyncpg.Connection, source_id: int, cibles: dict[str, int], champ: str) -> None:
    if champ not in COLONNES:
        raise ReferenceInconnue(f"« {champ} » is not a planner setting.")
    ligne = await connexion.fetchrow(
        "SELECT * FROM mark.reglage_planificateur WHERE site_id = $1", source_id
    )
    valeur = _reglages(ligne).model_dump()[champ] if ligne is not None else None
    for site_id in cibles.values():
        propre = await connexion.fetchrow(
            "SELECT * FROM mark.reglage_planificateur WHERE site_id = $1", site_id
        )
        valeurs = _reglages(propre).model_dump() if propre is not None else ReglagesPlanificateur().model_dump()
        valeurs[champ] = valeur
        await _ecrire_reglages(connexion, site_id, ReglagesPlanificateur.model_validate(valeurs))


async def _type(connexion: asyncpg.Connection, source_id: int, cibles: dict[str, int], code: str) -> None:
    modele = await connexion.fetchval(
        "SELECT id FROM mark.type_rendez_vous WHERE code = $1 AND site_id = $2", code, source_id
    )
    if modele is None:
        raise ReferenceInconnue(f"The appointment type « {code} » does not exist on this establishment.")
    if not cibles:
        return
    # Son rang dans la liste d'un lieu qui l'a déjà reste le sien (``ordre`` n'est pas touché).
    await connexion.execute(
        """
        INSERT INTO mark.type_rendez_vous (code, site_id, libelle, duree_min, sujet_id,
            marge_avant_min, marge_apres_min, actif, ordre)
        SELECT t.code, s.id, t.libelle, t.duree_min, t.sujet_id, t.marge_avant_min, t.marge_apres_min,
               t.actif, t.ordre
        FROM mark.type_rendez_vous t, mark.site s
        WHERE t.id = $1 AND s.id = ANY($2::bigint[])
        ORDER BY s.ordre, s.id
        ON CONFLICT (code, (coalesce(site_id, 0))) DO UPDATE SET libelle = EXCLUDED.libelle,
            duree_min = EXCLUDED.duree_min, sujet_id = EXCLUDED.sujet_id,
            marge_avant_min = EXCLUDED.marge_avant_min, marge_apres_min = EXCLUDED.marge_apres_min,
            actif = EXCLUDED.actif
        """,
        modele,
        list(cibles.values()),
    )


async def _module(connexion: asyncpg.Connection, source_id: int, cibles: dict[str, int], cle: str) -> None:
    module, _, reglage = cle.partition(".")
    if not module or not reglage:
        raise ReferenceInconnue("A module setting is named « module.key ».")
    if not await connexion.fetchval("SELECT to_regclass('mark.module_reglage') IS NOT NULL"):
        raise ReferenceInconnue("The client database has no module settings yet: click « Upgrade ».")
    if not await _declare(connexion, module, reglage):
        raise ReferenceInconnue(f"« {reglage} » is not a setting declared by the module « {module} ».")
    ligne = await connexion.fetchval(
        "SELECT id FROM mark.module_reglage WHERE module_code = $1 AND cle = $2 AND site_id = $3",
        module,
        reglage,
        source_id,
    )
    if ligne is None:
        # Rien chez la source : « rien » est recopié (les autres reviennent à l'absence de valeur).
        await connexion.execute(
            "DELETE FROM mark.module_reglage WHERE module_code = $1 AND cle = $2 AND site_id = ANY($3::bigint[])",
            module,
            reglage,
            list(cibles.values()),
        )
        return
    await connexion.execute(
        """
        INSERT INTO mark.module_reglage (module_code, site_id, cle, valeur)
        SELECT r.module_code, s.id, r.cle, r.valeur
        FROM mark.module_reglage r, mark.site s
        WHERE r.id = $1 AND s.id = ANY($2::bigint[])
        ORDER BY s.ordre, s.id
        ON CONFLICT (module_code, cle, (coalesce(site_id, 0))) DO UPDATE SET valeur = EXCLUDED.valeur
        """,
        ligne,
        list(cibles.values()),
    )
