"""[.mark] Revue serveur M8 : la migration de l'équipe (``b4e2a7c19d30``) ne fait plus de tous les comptes des Administrateurs.

La migration est jouée pour de vrai (montée, descente, remontée) dans un schéma jetable de la base de test, à l'intérieur
d'une transaction annulée à la fin : rien ne reste, la base migrée des autres tests n'est pas touchée.

| Test | Ce qu'il prouve |
|---|---|
| comptes nommés | ``MARK_ADMINISTRATEURS`` (casse ignorée) : ces comptes Administrateurs, les autres sans rôle |
| variable absente | le plus ancien compte seul devient Administrateur |
| aucune adresse trouvée | même repli : jamais une installation sans administrateur |
| base vide | aucun membre, la migration passe |
| descente | les six tables partent ; la remontée refait la même graine |
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "b4e2a7c19d30_mark_equipe_roles.py"
SCHEMA = "m8_essai_migration"
TABLES = {"mark_roles", "mark_role_permissions", "mark_role_organisations", "mark_membres", "mark_invitations", "mark_journal"}


def _migration():
    spec = importlib.util.spec_from_file_location("migration_b4e2a7c19d30", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _decor(connexion, comptes):
    """Un schéma jetable avec ce que la migration lit : ``users`` (id, email, created_at) et ``organizations``."""
    connexion.execute(sa.text(f"CREATE SCHEMA {SCHEMA}"))
    connexion.execute(sa.text(f"SET LOCAL search_path TO {SCHEMA}"))
    connexion.execute(sa.text("CREATE TABLE users (id serial PRIMARY KEY, email varchar, created_at timestamptz)"))
    connexion.execute(sa.text("CREATE TABLE organizations (id serial PRIMARY KEY)"))
    ids = {}
    for email, cree_le in comptes:
        ids[email] = connexion.execute(
            sa.text("INSERT INTO users (email, created_at) VALUES (:e, :c) RETURNING id"), {"e": email, "c": cree_le}
        ).scalar()
    return ids


def _administrateurs(connexion) -> set[int]:
    return set(
        connexion.execute(
            sa.text(
                "SELECT m.user_id FROM mark_membres m JOIN mark_roles r ON r.id = m.role_id WHERE r.nom = 'Administrateur'"
            )
        ).scalars()
    )


def _membres(connexion) -> set[int]:
    return set(connexion.execute(sa.text("SELECT user_id FROM mark_membres")).scalars())


def _tables(connexion) -> set[str]:
    return set(
        connexion.execute(
            sa.text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"), {"s": SCHEMA}
        ).scalars()
    )


async def _jouer(test_engine, fonction):
    """Joue ``fonction(connexion_sync)`` dans une transaction toujours annulée."""
    async with test_engine.connect() as connexion:
        transaction = await connexion.begin()
        try:
            return await connexion.run_sync(fonction)
        finally:
            await transaction.rollback()


T0 = datetime(2026, 1, 1, tzinfo=UTC)
COMPTES = [
    ("pierre@example.com", T0 + timedelta(days=2)),
    ("evan@example.com", T0),  # le plus ancien, sans être le premier inséré
    ("stagiaire@example.com", T0 + timedelta(days=5)),
]


def _monter(connexion):
    with Operations.context(MigrationContext.configure(connexion)):
        _migration().upgrade()


def _descendre(connexion):
    with Operations.context(MigrationContext.configure(connexion)):
        _migration().downgrade()


async def test_seuls_les_comptes_nommes_deviennent_administrateurs(test_engine, monkeypatch):
    monkeypatch.setenv("MARK_ADMINISTRATEURS", " Evan@Example.com, pierre@example.com ,")

    def cas(connexion):
        ids = _decor(connexion, COMPTES)
        _monter(connexion)
        return ids, _administrateurs(connexion), _membres(connexion)

    ids, administrateurs, membres = await _jouer(test_engine, cas)
    assert administrateurs == {ids["evan@example.com"], ids["pierre@example.com"]}
    assert ids["stagiaire@example.com"] not in membres  # sans rôle


async def test_sans_variable_le_plus_ancien_compte_seul(test_engine, monkeypatch):
    monkeypatch.delenv("MARK_ADMINISTRATEURS", raising=False)

    def cas(connexion):
        ids = _decor(connexion, COMPTES)
        _monter(connexion)
        return ids, _membres(connexion), _administrateurs(connexion)

    ids, membres, administrateurs = await _jouer(test_engine, cas)
    assert membres == administrateurs == {ids["evan@example.com"]}


async def test_aucune_adresse_trouvee_repli_sur_le_plus_ancien(test_engine, monkeypatch):
    monkeypatch.setenv("MARK_ADMINISTRATEURS", "personne@example.com")

    def cas(connexion):
        ids = _decor(connexion, COMPTES)
        _monter(connexion)
        return ids, _membres(connexion)

    ids, membres = await _jouer(test_engine, cas)
    assert membres == {ids["evan@example.com"]}


async def test_une_base_sans_compte_passe_sans_membre(test_engine, monkeypatch):
    monkeypatch.delenv("MARK_ADMINISTRATEURS", raising=False)

    def cas(connexion):
        _decor(connexion, [])
        _monter(connexion)
        return _membres(connexion)

    assert await _jouer(test_engine, cas) == set()


async def test_la_descente_retire_les_tables_et_la_remontee_refait_la_graine(test_engine, monkeypatch):
    monkeypatch.setenv("MARK_ADMINISTRATEURS", "pierre@example.com")

    def cas(connexion):
        ids = _decor(connexion, COMPTES)
        _monter(connexion)
        montee = _tables(connexion)
        _descendre(connexion)
        descente = _tables(connexion)
        _monter(connexion)
        return ids, montee, descente, _administrateurs(connexion), _tables(connexion)

    ids, montee, descente, administrateurs, remontee = await _jouer(test_engine, cas)
    assert TABLES <= montee
    assert not (TABLES & descente) and descente == {"users", "organizations"}
    assert TABLES <= remontee
    assert administrateurs == {ids["pierre@example.com"]}


@pytest.mark.parametrize(
    ("brut", "attendu"),
    [(None, []), ("", []), (" , ", []), ("A@x.fr,a@x.fr, b@x.fr", ["a@x.fr", "b@x.fr"])],
)
def test_la_variable_se_lit_sans_casse_ni_doublon(brut, attendu):
    assert _migration().adresses_des_administrateurs(brut) == attendu


async def test_la_sortie_dit_les_promus_et_les_adresses_introuvables_sans_les_autres_adresses(test_engine, monkeypatch, capsys):
    """Revue de contrôle, point 7 : une adresse mal tapée ne passe plus sans bruit ; aucune adresse d'un autre compte n'est écrite."""
    monkeypatch.setenv("MARK_ADMINISTRATEURS", "evan@example.com, pierr@example.com")

    def cas(connexion):
        ids = _decor(connexion, COMPTES)
        _monter(connexion)
        return ids

    ids = await _jouer(test_engine, cas)
    sortie = capsys.readouterr().out
    assert f"(id) : {ids['evan@example.com']}" in sortie  # l'identifiant promu
    assert "pierr@example.com" in sortie and "introuvables" in sortie  # la faute de frappe se voit
    assert "stagiaire@example.com" not in sortie and "pierre@example.com" not in sortie  # jamais les autres comptes


async def test_la_sortie_dit_le_repli_quand_aucune_adresse_n_est_trouvee(test_engine, monkeypatch, capsys):
    monkeypatch.setenv("MARK_ADMINISTRATEURS", "personne@example.com")

    def cas(connexion):
        _decor(connexion, COMPTES)
        _monter(connexion)

    await _jouer(test_engine, cas)
    sortie = capsys.readouterr().out
    assert "repli sur le plus ancien compte" in sortie and "personne@example.com" in sortie
    assert "evan@example.com" not in sortie
