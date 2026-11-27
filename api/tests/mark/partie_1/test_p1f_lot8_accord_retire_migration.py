"""[.mark] Plan final Partie 1, lot 8b-3 (T35) : la migration 056 et la marque « accord retiré » (``accord_retire_le``) d'une commande ``retenue``.

| Test | Ce qu'il prouve |
|---|---|
| montée, descente, remontée | la colonne suit la montée et la descente, rejouables ; une ligne retenue n'est jamais perdue |
"""

from __future__ import annotations

import uuid

from api.db.bases_clients import connexion as schema
from api.tests.mark import test_base_client as _base
from api.tests.mark.partie_1.aides_briques import descendre_jusqu_a

# Fixtures du dossier reprises par nom, sans import de nom ni rustine de lint.
base_essai = _base.base_essai
base_prete = _base.base_prete

COLONNE = "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'mark' AND table_name = 'resto_commande' AND column_name = 'accord_retire_le'"


async def test_la_056_se_monte_se_descend_et_se_remonte(base_prete):
    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert await c.fetchval("SELECT 1 FROM mark.schema_version WHERE version = 56") == 1
        assert await c.fetchval(COLONNE) == 1
        await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('E')")
        site = await c.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom) SELECT id, 'a', 'A' FROM mark.entreprise LIMIT 1 RETURNING id")
        numero = uuid.uuid4()
        await c.execute("INSERT INTO mark.resto_commande (numero, numero_court, site_id, mode, total, statut, appel_id, accord_retire_le) "
                        "VALUES ($1, 'C1', $2, 'emporter', 1000, 'retenue', '1', now())", numero, site)

        for _ in range(2):  # la descente se rejoue
            await descendre_jusqu_a(c, 56)
        assert await c.fetchval("SELECT 1 FROM mark.schema_version WHERE version = 56") is None
        assert await c.fetchval(COLONNE) == 0
        assert await c.fetchval("SELECT statut FROM mark.resto_commande WHERE numero = $1", numero) == "retenue"  # rien de perdu

        assert 56 in await schema.appliquer_migrations(c)
        assert await c.fetchval(COLONNE) == 1
        assert await c.fetchval("SELECT count(*) FROM mark.schema_version WHERE version = 56") == 1
    finally:
        await c.close()
