"""[.mark] SQL of the client's database: the referential Dograh writes and reads (B2, B3).

When a database is attached, it is the SOURCE of the establishments, their numbers,
hours and sentences: Dograh's screen writes here (one transaction each, the author
stamped in ``mark.auteur`` so that ``journal_modif`` says who), and the copy the
calls read is rebuilt from here (``lignes_du_referentiel``; the checks are in
``api/services/base_client/referentiel.py``).

Hours live in ``site.horaires_texte`` (decision of Evan, 06/10, option A); the tables
``horaire`` and ``fermeture`` stay empty until the portal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import asyncpg

from api.schemas.etablissements import CatalogueEtablissements
from api.schemas.phrases import CataloguePhrases

RAISON_SOCIALE_PAR_DEFAUT = "Entreprise"


@dataclass
class LignesDuReferentiel:
    """The rows as stored, before any check."""

    sites: list[dict]
    numeros: list[dict]
    surcharges: list[dict]
    phrases: list[dict]


async def _auteur(connexion: asyncpg.Connection, auteur: str) -> None:
    await connexion.execute("SELECT set_config('mark.auteur', $1, true)", auteur[:200])


async def _entreprise(connexion: asyncpg.Connection) -> int:
    existante = await connexion.fetchval(
        "SELECT id FROM mark.entreprise ORDER BY id LIMIT 1"
    )
    if existante is not None:
        return existante
    return await connexion.fetchval(
        "INSERT INTO mark.entreprise (raison_sociale) VALUES ($1) RETURNING id",
        RAISON_SOCIALE_PAR_DEFAUT,
    )


async def ecrire_etablissements(
    connexion: asyncpg.Connection, catalogue: CatalogueEtablissements, auteur: str
) -> None:
    """Replace the establishments Dograh manages (rows with a ``cle``), in one transaction.

    ⛔ An establishment removed on screen is DEACTIVATED (``actif = false``), never
    deleted: past calls and requests refer to it.
    """
    async with connexion.transaction():
        await _auteur(connexion, auteur)
        entreprise = await _entreprise(connexion)
        gardes: list[str] = []
        for ordre, e in enumerate(catalogue.etablissements):
            a = e.adresse
            site_id = await connexion.fetchval(
                """
                INSERT INTO mark.site (entreprise_id, cle, nom, actif, ordre, second_numero, numero_transfert,
                                       adresse_cp, adresse_insee, adresse_commune, adresse_voie,
                                       horaires_texte, annonce_fermeture, annonce_pause, termes_lexique)
                VALUES ($1, $2, $3, true, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::jsonb)
                ON CONFLICT (cle) DO UPDATE SET
                    nom = EXCLUDED.nom, actif = true, ordre = EXCLUDED.ordre,
                    second_numero = EXCLUDED.second_numero, numero_transfert = EXCLUDED.numero_transfert,
                    adresse_cp = EXCLUDED.adresse_cp, adresse_insee = EXCLUDED.adresse_insee,
                    adresse_commune = EXCLUDED.adresse_commune, adresse_voie = EXCLUDED.adresse_voie,
                    horaires_texte = EXCLUDED.horaires_texte, annonce_fermeture = EXCLUDED.annonce_fermeture,
                    annonce_pause = EXCLUDED.annonce_pause, termes_lexique = EXCLUDED.termes_lexique
                RETURNING id
                """,
                entreprise,
                e.id,
                e.nom,
                ordre,
                e.second_numero,
                e.numero_transfert,
                a.code_postal if a else None,
                a.code_insee if a else None,
                a.commune if a else None,
                a.voie if a else None,
                e.horaires_ouverture,
                e.annonce_fermeture,
                e.annonce_pause,
                json.dumps([t.model_dump(mode="json") for t in e.termes_lexique]),
            )
            gardes.append(e.id)
            # Only what changed is written: the journal says what really moved.
            await connexion.execute(
                "DELETE FROM mark.site_numero WHERE site_id = $1 AND NOT (numero = ANY($2::text[]))",
                site_id,
                list(e.numeros),
            )
            for numero in e.numeros:
                await connexion.execute(
                    "INSERT INTO mark.site_numero (numero, site_id) VALUES ($1, $2) "
                    "ON CONFLICT (numero) DO UPDATE SET site_id = EXCLUDED.site_id",
                    numero,
                    site_id,
                )
            await connexion.execute(
                "DELETE FROM mark.phrase_site WHERE site_id = $1 AND NOT (variable = ANY($2::text[]))",
                site_id,
                list(e.phrases),
            )
            for variable, contenu in e.phrases.items():
                await connexion.execute(
                    "INSERT INTO mark.phrase_site (variable, site_id, contenu) "
                    "SELECT $1, $2, $3 WHERE EXISTS (SELECT 1 FROM mark.phrase WHERE variable = $1) "
                    "ON CONFLICT (variable, site_id) DO UPDATE SET contenu = EXCLUDED.contenu",
                    variable,
                    site_id,
                    contenu,
                )
        await connexion.execute(
            "UPDATE mark.site SET actif = false WHERE actif AND cle IS NOT NULL AND NOT (cle = ANY($1::text[]))",
            gardes,
        )


async def ecrire_phrases(
    connexion: asyncpg.Connection, catalogue: CataloguePhrases, auteur: str
) -> None:
    async with connexion.transaction():
        await _auteur(connexion, auteur)
        variables = [p.variable for p in catalogue.phrases]
        await connexion.execute(
            "DELETE FROM mark.phrase WHERE NOT (variable = ANY($1::text[]))", variables
        )
        for ordre, p in enumerate(catalogue.phrases):
            await connexion.execute(
                """
                INSERT INTO mark.phrase (variable, description, contenu, niveau, ordre)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (variable) DO UPDATE SET description = EXCLUDED.description,
                    contenu = EXCLUDED.contenu, niveau = EXCLUDED.niveau, ordre = EXCLUDED.ordre
                """,
                p.variable,
                p.description,
                p.contenu,
                p.niveau,
                ordre,
            )


async def lignes_du_referentiel(connexion: asyncpg.Connection) -> LignesDuReferentiel:
    sites = await connexion.fetch(
        "SELECT * FROM mark.site WHERE cle IS NOT NULL AND actif ORDER BY ordre, id"
    )
    numeros = await connexion.fetch(
        "SELECT numero, site_id FROM mark.site_numero ORDER BY numero"
    )
    surcharges = await connexion.fetch(
        "SELECT variable, site_id, contenu FROM mark.phrase_site"
    )
    phrases = await connexion.fetch(
        "SELECT variable, description, contenu, niveau FROM mark.phrase ORDER BY ordre, variable"
    )
    lignes_sites = []
    for site in sites:
        site = dict(site)
        brut = site.get("termes_lexique")
        site["termes_lexique"] = (
            json.loads(brut) if isinstance(brut, str) else (brut or [])
        )
        lignes_sites.append(site)
    return LignesDuReferentiel(
        sites=lignes_sites,
        numeros=[dict(n) for n in numeros],
        surcharges=[dict(s) for s in surcharges],
        phrases=[dict(p) for p in phrases],
    )
