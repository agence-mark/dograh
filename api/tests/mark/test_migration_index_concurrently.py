"""[.mark] Revue serveur, mineur 9 : les index de Conversations sur ``workflow_runs`` se créent SANS verrouiller les écritures.

La migration ``e6c9a2d4b815`` est jouée pour de vrai (descente puis montée) sur la base de test, hors transaction (c'est la
condition de ``CREATE INDEX CONCURRENTLY``). Les index existent avant et après ; la montée est idempotente.

| Test | Ce qu'il prouve |
|---|---|
| une seule tête | la chaîne des migrations n'a qu'une tête, ``e6c9a2d4b815`` (sur ``d5b8f1a3c704``) |
| ordinaire interdit | la migration ``c4a7d2e9b301`` ne crée plus d'index (ils verrouilleraient la table) |
| descente et montée | la descente retire les trois index, la montée les recrée avec ``CONCURRENTLY`` ; relancée, elle ne casse rien |
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

RACINE = Path(__file__).resolve().parents[2] / "alembic"
NOMS = {"idx_workflow_runs_definition_id", "idx_workflow_runs_workflow_created", "idx_workflow_runs_note_juge"}


def _module(nom_fichier: str):
    spec = importlib.util.spec_from_file_location(nom_fichier[:-3], RACINE / "versions" / nom_fichier)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_une_seule_tete_sur_la_precedente():
    config = Config()
    config.set_main_option("script_location", str(RACINE))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["e6c9a2d4b815"]
    assert scripts.get_revision("e6c9a2d4b815").down_revision == "d5b8f1a3c704"


def test_la_migration_c4_ne_cree_plus_d_index_ordinaire():
    source = (RACINE / "versions" / "c4a7d2e9b301_mark_note_juge_des_appels.py").read_text(encoding="utf-8")
    assert "create_index" not in source
    nouvelle = (RACINE / "versions" / "e6c9a2d4b815_mark_index_workflow_runs_concurrently.py").read_text(encoding="utf-8")
    assert "CREATE INDEX CONCURRENTLY" in nouvelle and "DROP INDEX CONCURRENTLY" in nouvelle and "autocommit_block" in nouvelle


def _index(connexion) -> set[str]:
    return set(connexion.execute(sa.text("SELECT indexname FROM pg_indexes WHERE tablename = 'workflow_runs'")).scalars()) & NOMS


async def test_descente_puis_montee_hors_transaction(test_engine):
    migration = _module("e6c9a2d4b815_mark_index_workflow_runs_concurrently.py")

    def jouer(connexion):
        contexte = MigrationContext.configure(connexion)

        def lancer(fonction):
            # Comme Alembic : la migration s'ouvre dans sa transaction, l'index sort de cette transaction (autocommit_block).
            with contexte.begin_transaction():
                fonction()

        with Operations.context(contexte):
            avant = _index(connexion)
            lancer(migration.downgrade)
            apres_descente = _index(connexion)
            lancer(migration.upgrade)
            apres_montee = _index(connexion)
            lancer(migration.upgrade)  # relancée : IF NOT EXISTS
            lancer(migration.downgrade)
            lancer(migration.downgrade)  # relancée : IF EXISTS
            lancer(migration.upgrade)
            return avant, apres_descente, apres_montee, _index(connexion)

    async with test_engine.connect() as connexion:
        connexion = await connexion.execution_options(isolation_level="AUTOCOMMIT")
        avant, apres_descente, apres_montee, final = await connexion.run_sync(jouer)
    assert (avant, apres_descente, apres_montee, final) == (NOMS, set(), NOMS, NOMS)
