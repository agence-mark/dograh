"""[.mark] Module Restauration, lot 20 (demande de la fenêtre principale) : la migration 031 ferme la liste des DOUZE mécanismes de remise dans la base.

| Test | Ce qu'il prouve |
|---|---|
| liste fermée | chacun des douze mécanismes s'écrit ; un mécanisme inconnu est refusé à l'écriture ET à la modification d'une ligne (le portail écrit la table directement) |
| même liste que le code | la liste de la contrainte est exactement ``FAMILLE_DU_MECANISME`` (le code et la base ne divergent pas) |
| descente | la descente retire la contrainte (un mécanisme inconnu s'écrit de nouveau) sans toucher une ligne ; remontée : la contrainte revient |
| lignes d'avant | une ligne d'un mécanisme inconnu écrite AVANT la contrainte reste (la contrainte est posée ``NOT VALID``), elle ne peut plus être modifiée vers un autre mécanisme inconnu |
"""

from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients.restauration_remise import MECANISMES
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401

MIGRATIONS = Path(schema.__file__).parent / "migrations"
CONTRAINTE = "resto_remise_mecanisme_ferme"


async def _site(c) -> int:
    await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('Entreprise')")
    return await c.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, 'remise', 'remise', 'Europe/Paris' FROM mark.entreprise RETURNING id")


async def _poser(c, site: int, ref: str, mecanisme: str) -> None:
    await c.execute("INSERT INTO mark.resto_remise (site_id, ref, nom, mecanisme) VALUES ($1, $2, $2, $3)", site, ref, mecanisme)


async def _contrainte(c) -> bool:
    return bool(await c.fetchval("SELECT count(*) FROM pg_constraint WHERE conname = $1", CONTRAINTE))


async def test_seuls_les_douze_mecanismes_s_ecrivent_et_la_descente_rouvre_la_liste(base_prete):
    c = await schema.connecter_proprietaire(base_prete)
    try:
        site = await _site(c)
        for m in MECANISMES:
            await _poser(c, site, m, m)
        assert len(MECANISMES) == 12
        with pytest.raises(asyncpg.CheckViolationError):
            await _poser(c, site, "BIDON", "bonus_mystere")
        with pytest.raises(asyncpg.CheckViolationError):
            await c.execute("UPDATE mark.resto_remise SET mecanisme = 'bonus_mystere' WHERE ref = 'montant'")
        assert await c.fetchval("SELECT mecanisme FROM mark.resto_remise WHERE ref = 'montant'") == "montant"
        # la liste de la base est celle du code
        texte = await c.fetchval("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = $1", CONTRAINTE)
        assert all(f"'{m}'" in texte for m in MECANISMES) and texte.count("::text") == len(MECANISMES)
        # descente : la liste se rouvre, aucune ligne n'est touchée
        avant = await c.fetchval("SELECT count(*) FROM mark.resto_remise")
        async with c.transaction():
            await c.execute((MIGRATIONS / "descentes" / "031-descente.sql").read_text(encoding="utf-8").replace("SET search_path = mark;", "SET LOCAL search_path = mark;"))
        assert not await _contrainte(c) and await c.fetchval("SELECT count(*) FROM mark.resto_remise") == avant
        await _poser(c, site, "BIDON", "bonus_mystere")  # écrite AVANT la contrainte
        # remontée : la contrainte revient, la ligne d'avant reste, mais ne peut plus changer vers un autre mécanisme inconnu
        async with c.transaction():
            await c.execute((MIGRATIONS / "031-remise-mecanisme-ferme.sql").read_text(encoding="utf-8").replace("SET search_path = mark;", "SET LOCAL search_path = mark;"))
        assert await _contrainte(c) and await c.fetchval("SELECT mecanisme FROM mark.resto_remise WHERE ref = 'BIDON'") == "bonus_mystere"
        with pytest.raises(asyncpg.CheckViolationError):
            await c.execute("UPDATE mark.resto_remise SET mecanisme = 'autre_mystere' WHERE ref = 'BIDON'")
        with pytest.raises(asyncpg.CheckViolationError):
            await _poser(c, site, "BIDON2", "bonus_mystere")
    finally:
        await c.close()
