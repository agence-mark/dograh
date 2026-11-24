"""[.mark] Plan final Partie 1, lot 9, constat 137 : la 053 retire les colonnes mortes ``fin_aujourd_hui`` et ``fin_aujourd_hui_le`` (remplacées par ``fin_aujourd_hui_a`` en 050)."""

from __future__ import annotations

from api.db.bases_clients import connexion as schema
from api.tests.mark.partie_1.aides_briques import descendre_jusqu_a
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401

_COLONNES = "('fin_aujourd_hui', 'fin_aujourd_hui_le')"


async def _presentes(c) -> set[str]:
    lignes = await c.fetch(
        f"SELECT column_name FROM information_schema.columns WHERE table_schema='mark' AND table_name='resto_reglage_type' AND column_name IN {_COLONNES}"
    )
    return {r["column_name"] for r in lignes}


async def test_migration_053_montee_descente_montee(base_prete):  # noqa: F811
    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert await _presentes(c) == set()
        assert await c.fetchval("SELECT 1 FROM mark.schema_version WHERE version = 53") == 1
        await descendre_jusqu_a(c, 53)
        assert await _presentes(c) == {"fin_aujourd_hui", "fin_aujourd_hui_le"}
        assert await c.fetchval("SELECT 1 FROM mark.schema_version WHERE version = 53") is None
        assert 53 in await schema.appliquer_migrations(c)
        assert await _presentes(c) == set()
        assert await c.fetchval("SELECT count(*) FROM mark.schema_version WHERE version = 53") == 1
    finally:
        await c.close()
