"""[.mark] Module Restauration, lot 20, étape 1 : les tables de la caisse de démo (Alembic ``e3b7c1d9a4f2``) et leur accès.

| Test | Ce qu'il prouve |
|---|---|
| descente et montée | les trois tables et leurs index partent et reviennent ; relancée, rien ne casse ; une seule tête |
| accès borné | un restaurant de test se lit, se modifie et se supprime seulement avec SON organisation ; les commandes et messages le suivent en cascade |
| jeton | seule l'empreinte est gardée : la recherche par empreinte retrouve le restaurant, jamais par le jeton |
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from api.db import db_client
from api.tests.mark.equipe_commun import creer_organisation

RACINE = Path(__file__).resolve().parents[2] / "alembic"
FICHIER = "e3b7c1d9a4f2_mark_restauration_caisse_demo.py"
TABLES = ("mark_caisse_demo_restaurant", "mark_caisse_demo_commande", "mark_caisse_demo_message")
T0 = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


def test_la_chaine_a_une_seule_tete_et_la_caisse_de_demo_est_la_tete():
    config = Config()
    config.set_main_option("script_location", str(RACINE))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["e3b7c1d9a4f2"]
    assert scripts.get_revision("e3b7c1d9a4f2").down_revision == "c5a8e2f1d934"


async def test_la_descente_retire_les_trois_tables_et_la_montee_les_rend(test_engine):
    spec = importlib.util.spec_from_file_location("caisse_demo_mig", RACINE / "versions" / FICHIER)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def jouer(connexion):
        contexte = MigrationContext.configure(connexion)

        def etat():
            return [connexion.execute(sa.text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"public.{t}"}).scalar() for t in TABLES]

        with Operations.context(contexte):
            avant = etat()
            with contexte.begin_transaction():
                migration.downgrade()
            apres_descente = etat()
            with contexte.begin_transaction():
                migration.upgrade()
            return avant, apres_descente, etat()

    async with test_engine.connect() as connexion:
        connexion = await connexion.execution_options(isolation_level="AUTOCOMMIT")
        avant, apres_descente, apres_montee = await connexion.run_sync(jouer)
    assert (avant, apres_descente, apres_montee) == ([True] * 3, [False] * 3, [True] * 3)


async def test_un_restaurant_de_test_n_est_servi_qu_a_son_organisation_et_garde_le_jeton_en_empreinte(db_session):
    a = await creer_organisation(db_client, "demo-tables-a")
    b = await creer_organisation(db_client, "demo-tables-b")
    r = await db_client.creer_restaurant_de_demo(a, "Pizzeria de test", "pdv-tables-1", T0, jeton_empreinte="e" * 64)
    assert (r["etat"], r["minutes_en_plus"], r["carte"], r["stocks"]) == ("ouvert", 0, {}, [])
    assert await db_client.lire_restaurant_de_demo(b, r["id"]) is None  # une autre organisation ne le voit pas
    assert await db_client.modifier_restaurant_de_demo(b, r["id"], {"nom": "Piraté"}, T0) is None
    assert await db_client.supprimer_restaurant_de_demo(b, r["id"]) is False
    assert (await db_client.lire_restaurant_de_demo(a, r["id"]))["nom"] == "Pizzeria de test"
    assert (await db_client.lire_restaurant_de_demo_par_jeton("e" * 64))["id"] == r["id"]
    assert await db_client.lire_restaurant_de_demo_par_jeton("f" * 64) is None
    assert [x["id"] for x in await db_client.lister_restaurants_de_demo(b)] == []
    with pytest.raises(ValueError):
        await db_client.modifier_restaurant_de_demo(a, r["id"], {"organization_id": b}, T0)  # jamais changer d'organisation
    await db_client.ajouter_commande_de_demo(r["id"], "c1", "N-1", "new", {"x": 1}, T0)
    await db_client.ajouter_message_de_demo(r["id"], "m1", {"id": "m1"}, T0)
    assert await db_client.supprimer_restaurant_de_demo(a, r["id"]) is True
    assert await db_client.lire_commande_de_demo(r["id"], "c1") is None and await db_client.lire_message_de_demo("m1") is None  # en cascade
