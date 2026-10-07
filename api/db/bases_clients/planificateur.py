"""[.mark] SQL of the planner in the client's database (chantier l-agent-collegue, L5, migration 010).

- The rules: ``reglage_planificateur`` (the organization's row, one row per establishment that
  overrides something) and ``type_rendez_vous`` (organization-wide, or one establishment's).
- What the planner reads during a call: the people who do a type of appointment, with their
  agenda in the calendar software chosen; how many appointments each was given lately (the
  turn and its fairness, P7).
- Every write goes through ``mark.auteur`` (journal of the referential, like the team).
"""

from __future__ import annotations

from datetime import datetime

import asyncpg

from api.schemas.planificateur import (
    Planificateur,
    ReglagesPlanificateur,
    TypeRendezVous,
)

COLONNES = tuple(ReglagesPlanificateur.model_fields)


class ReferenceInconnue(ValueError):
    """An establishment or a subject the client's database does not know. Safe to show."""


def _reglages(ligne) -> ReglagesPlanificateur:
    # A client database still at version 12 has no ``fenetre_equite_jours``: read as inherited (the
    # default), so a call never fails in the gap between the deployment and « Upgrade » (013).
    colonnes_lues = set(ligne.keys())
    valeurs = {c: (ligne[c] if c in colonnes_lues else None) for c in COLONNES}
    for cle in ("delai_minimal_h", "zone_rayon_km", "coefficient_trajet", "vitesse_kmh"):
        if valeurs[cle] is not None:
            valeurs[cle] = float(valeurs[cle])
    if valeurs["zone_communes"] is not None:
        valeurs["zone_communes"] = list(valeurs["zone_communes"])
    return ReglagesPlanificateur.model_validate(valeurs)


async def lire_planificateur(connexion: asyncpg.Connection) -> Planificateur:
    sites = {r["id"]: r["cle"] for r in await connexion.fetch("SELECT id, cle FROM mark.site")}
    sujets = {r["id"]: r["code"] for r in await connexion.fetch("SELECT id, code FROM mark.sujet")}
    planificateur = Planificateur()
    for ligne in await connexion.fetch("SELECT * FROM mark.reglage_planificateur ORDER BY id"):
        reglages = _reglages(ligne)
        if ligne["site_id"] is None:
            planificateur.reglages = reglages
        elif sites.get(ligne["site_id"]):
            planificateur.par_etablissement[sites[ligne["site_id"]]] = reglages
    planificateur.types = [
        TypeRendezVous(
            code=r["code"],
            etablissement=sites.get(r["site_id"]) if r["site_id"] else None,
            libelle=r["libelle"],
            duree_min=r["duree_min"],
            sujet=sujets.get(r["sujet_id"]) if r["sujet_id"] else None,
            marge_avant_min=r["marge_avant_min"],
            marge_apres_min=r["marge_apres_min"],
            actif=r["actif"],
        )
        for r in await connexion.fetch(
            "SELECT * FROM mark.type_rendez_vous ORDER BY ordre, site_id NULLS FIRST, id"
        )
        if not r["site_id"] or sites.get(r["site_id"])
    ]
    return planificateur


async def _ecrire_reglages(connexion, site_id: int | None, reglages: ReglagesPlanificateur) -> None:
    valeurs = reglages.model_dump()
    if all(v is None for v in valeurs.values()):
        await connexion.execute(
            "DELETE FROM mark.reglage_planificateur WHERE coalesce(site_id, 0) = coalesce($1::bigint, 0)",
            site_id,
        )
        return
    colonnes = ", ".join(COLONNES)
    marqueurs = ", ".join(f"${i + 2}" for i in range(len(COLONNES)))
    mises_a_jour = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLONNES)
    await connexion.execute(
        f"""
        INSERT INTO mark.reglage_planificateur (site_id, {colonnes}) VALUES ($1, {marqueurs})
        ON CONFLICT ((coalesce(site_id, 0))) DO UPDATE SET {mises_a_jour}
        """,
        site_id,
        *[valeurs[c] for c in COLONNES],
    )


async def ecrire_planificateur(
    connexion: asyncpg.Connection, planificateur: Planificateur, auteur: str
) -> None:
    async with connexion.transaction():
        await connexion.execute("SELECT set_config('mark.auteur', $1, true)", auteur[:200])
        sites = {
            r["cle"]: r["id"]
            for r in await connexion.fetch("SELECT id, cle FROM mark.site WHERE cle IS NOT NULL")
        }
        sujets = {
            r["code"]: r["id"]
            for r in await connexion.fetch("SELECT id, code FROM mark.sujet WHERE actif")
        }
        for cle in planificateur.par_etablissement:
            if cle not in sites:
                raise ReferenceInconnue(f"Unknown establishment « {cle} ».")
        for t in planificateur.types:
            if t.etablissement is not None and t.etablissement not in sites:
                raise ReferenceInconnue(f"{t.libelle}: unknown establishment « {t.etablissement} ».")
            if t.sujet is not None and t.sujet not in sujets:
                raise ReferenceInconnue(f"{t.libelle}: unknown subject « {t.sujet} ».")
        await _ecrire_reglages(connexion, None, planificateur.reglages)
        for cle, site_id in sites.items():
            await _ecrire_reglages(
                connexion, site_id, planificateur.par_etablissement.get(cle) or ReglagesPlanificateur()
            )
        gardes = []
        for ordre, t in enumerate(planificateur.types):
            site_id = sites.get(t.etablissement) if t.etablissement else None
            gardes.append(
                await connexion.fetchval(
                    """
                    INSERT INTO mark.type_rendez_vous (code, site_id, libelle, duree_min, sujet_id,
                        marge_avant_min, marge_apres_min, actif, ordre)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (code, (coalesce(site_id, 0))) DO UPDATE SET libelle = EXCLUDED.libelle,
                        duree_min = EXCLUDED.duree_min, sujet_id = EXCLUDED.sujet_id,
                        marge_avant_min = EXCLUDED.marge_avant_min, marge_apres_min = EXCLUDED.marge_apres_min,
                        actif = EXCLUDED.actif, ordre = EXCLUDED.ordre
                    RETURNING id
                    """,
                    t.code,
                    site_id,
                    t.libelle,
                    t.duree_min,
                    sujets.get(t.sujet) if t.sujet else None,
                    t.marge_avant_min,
                    t.marge_apres_min,
                    t.actif,
                    ordre,
                )
            )
        # A type removed on screen is removed (a booked appointment keeps its code as text).
        await connexion.execute(
            "DELETE FROM mark.type_rendez_vous WHERE NOT (id = ANY($1::bigint[]))", gardes
        )


async def personnes_du_type(
    connexion: asyncpg.Connection, sujet: str | None, etablissement: str | None, systeme: str
) -> list[dict]:
    """The ACTIVE people who do this type of appointment (the subject's, in its order of
    priority; no subject: everyone), of the establishment served or of the whole company,
    WITH an agenda in this software. ``{cle, prenom, nom, etablissement, agenda,
    joignable_par_transfert, telephone}``."""
    lignes = await connexion.fetch(
        """
        SELECT p.cle, p.prenom, p.nom, s.cle AS etablissement, l.id_externe AS agenda,
               p.joignable_par_transfert, p.telephone,
               coalesce(ps.priorite, 1) AS priorite, p.id
        FROM mark.personne p
        JOIN mark.lien_externe l ON l.objet_type = 'personne' AND l.objet_id = p.id AND l.systeme = $3
        LEFT JOIN mark.site s ON s.id = p.site_id
        LEFT JOIN mark.sujet su ON su.code = $1 AND su.actif
        LEFT JOIN mark.personne_sujet ps ON ps.personne_id = p.id AND ps.sujet_id = su.id
        WHERE p.actif AND p.cle IS NOT NULL
          AND ($1::text IS NULL OR ps.personne_id IS NOT NULL)
          AND (p.site_id IS NULL OR s.cle = $2)
        ORDER BY priorite, p.id
        """,
        sujet,
        etablissement,
        systeme,
    )
    return [{k: r[k] for k in ("cle", "prenom", "nom", "etablissement", "agenda",
                                "joignable_par_transfert", "telephone")} for r in lignes]


async def attributions_par_personne(
    connexion: asyncpg.Connection, type_code: str, depuis: datetime
) -> dict[str, int]:
    """How many appointments of this type each person was given since ``depuis`` (P7)."""
    return {
        r["cle"]: r["n"]
        for r in await connexion.fetch(
            """
            SELECT p.cle, count(*) AS n FROM mark.attribution a JOIN mark.personne p ON p.id = a.personne_id
            WHERE a.type_code = $1 AND a.le >= $2 GROUP BY p.cle
            """,
            type_code,
            depuis,
        )
    }


async def ecrire_attribution(
    connexion: asyncpg.Connection,
    rendez_vous_id: int,
    appel_id: int | None,
    personne_id: int | None,
    attribution: dict,
    type_code: str | None,
) -> None:
    """Inside the hub's transaction (``hub.ecrire_rendez_vous``)."""
    await connexion.execute(
        "UPDATE mark.rendez_vous SET type_code = $2 WHERE id = $1", rendez_vous_id, type_code
    )
    mode = attribution.get("mode")
    if mode not in ("premier_libre", "tour_de_role", "charge", "zone"):
        return
    rang = attribution.get("rang")
    await connexion.execute(
        """
        INSERT INTO mark.attribution (appel_id, rendez_vous_id, personne_id, type_code, mode, rang, motif)
        VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT (rendez_vous_id) DO NOTHING
        """,
        appel_id,
        rendez_vous_id,
        personne_id,
        type_code,
        mode,
        rang if isinstance(rang, int) else None,
        (str(attribution["motif"])[:200] if attribution.get("motif") else None),
    )
