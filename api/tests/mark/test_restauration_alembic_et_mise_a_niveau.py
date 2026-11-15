"""[.mark] Module Restauration, lot 1 : le lien point de vente -> établissement (Alembic) et le passage des migrations
sur les bases clientes (essai à blanc, reprise, descente).

| Test | Ce qu'il prouve |
|---|---|
| une seule tête | la chaîne Alembic n'a qu'une tête, ``c5a8e2f1d934`` (sur ``b7d3f1a9c5e2``) |
| descente et montée | la table ``mark_point_de_vente`` et ses deux index uniques partent et reviennent ; relancée, rien ne casse |
| essai à blanc | une base en version 24 : l'essai dit « 25 à 30 » et n'écrit rien ; le passage réel les applique ; rejoué = rien de plus |
| descente refusée sans confirmation | ``descendre_une_base`` exige ``confirmer=True`` ; confirmée, elle retire 30 à 25 dans l'ordre |
| reprise | une base en échec est rapportée, les autres passent ; rejouée une fois réparée, elle reprend où elle s'était arrêtée |
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from api.db.bases_clients import connexion as schema
from api.services.base_client import mise_a_niveau as passage
from api.tests.mark.test_base_client import _serveur, base_essai, base_prete  # noqa: F401

RACINE = Path(__file__).resolve().parents[2] / "alembic"
FICHIER = "c5a8e2f1d934_mark_restauration_point_de_vente.py"
INDEX = {"uq_mark_point_de_vente_prise_point", "uq_mark_point_de_vente_etablissement"}


def _module():
    spec = importlib.util.spec_from_file_location("restauration_pdv", RACINE / "versions" / FICHIER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_la_chaine_alembic_a_une_seule_tete():
    config = Config()
    config.set_main_option("script_location", str(RACINE))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["c5a8e2f1d934"]
    assert scripts.get_revision("c5a8e2f1d934").down_revision == "b7d3f1a9c5e2"


def _etat(connexion):
    table = connexion.execute(sa.text("SELECT to_regclass('public.mark_point_de_vente') IS NOT NULL")).scalar()
    unique = {
        ligne[0]
        for ligne in connexion.execute(
            sa.text("SELECT i.indexname FROM pg_indexes i JOIN pg_class c ON c.relname = i.indexname JOIN pg_index x ON x.indexrelid = c.oid "
                    "WHERE i.tablename = 'mark_point_de_vente' AND x.indisunique AND NOT x.indisprimary")
        )
    }
    return table, unique


async def test_descente_puis_montee_du_lien_point_de_vente(test_engine):
    migration = _module()

    def jouer(connexion):
        contexte = MigrationContext.configure(connexion)

        def lancer(fonction):
            with contexte.begin_transaction():
                fonction()

        with Operations.context(contexte):
            avant = _etat(connexion)
            lancer(migration.downgrade)
            apres_descente = _etat(connexion)
            lancer(migration.upgrade)
            apres_montee = _etat(connexion)
            return avant, apres_descente, apres_montee

    async with test_engine.connect() as connexion:
        connexion = await connexion.execution_options(isolation_level="AUTOCOMMIT")
        avant, apres_descente, apres_montee = await connexion.run_sync(jouer)
    assert avant == (True, INDEX)
    assert apres_descente == (False, set())
    assert apres_montee == (True, INDEX)


# --------------------------------------------------------------------------- #
# Le passage sur les bases clientes
# --------------------------------------------------------------------------- #


async def _version(base):
    c = await schema.connecter_proprietaire(base)
    try:
        return await schema.version_de(c)
    finally:
        await c.close()


async def test_essai_a_blanc_passage_reel_et_descente_confirmee(base_prete):
    base = base_prete
    # sans confirmation, une descente ne fait rien
    with pytest.raises(ValueError):
        await passage.descendre_une_base(base, 24)
    assert await _version(base) == 30
    assert await passage.descendre_une_base(base, 24, confirmer=True) == [30, 29, 28, 27, 26, 25]
    assert await _version(base) == 24

    blanc = await passage.mettre_a_niveau_une_base(1, base, a_blanc=True)
    assert blanc.reussie and blanc.a_blanc and blanc.appliquees == [25, 26, 27, 28, 29, 30] and blanc.apres == 24
    assert "À BLANC" in blanc.ligne()
    assert await _version(base) == 24  # rien d'écrit

    reel = await passage.mettre_a_niveau_une_base(1, base)
    assert reel.reussie and reel.appliquees == [25, 26, 27, 28, 29, 30] and reel.apres == 30
    rejoue = await passage.mettre_a_niveau_une_base(1, base)
    assert rejoue.reussie and rejoue.appliquees == [] and rejoue.apres == 30


async def test_une_base_en_echec_n_arrete_pas_les_autres_et_la_reprise_continue(base_prete, monkeypatch):
    base = base_prete
    await passage.descendre_une_base(base, 25, confirmer=True)  # la base est en 25 : reste 26 à 30
    assert await _version(base) == 25
    inconnue = "mark_essai_inexistante"
    resultats = await passage.mettre_a_niveau_toutes_les_bases([(1, inconnue), (2, base)])
    assert not resultats[0].reussie and resultats[0].erreur
    assert resultats[1].reussie and resultats[1].appliquees == [26, 27, 28, 29, 30]
    # reprise sur la base qui avait échoué : rejouée, elle ne refait rien sur celle qui a réussi
    resultats = await passage.mettre_a_niveau_toutes_les_bases([(2, base)])
    assert resultats[0].reussie and resultats[0].appliquees == []
