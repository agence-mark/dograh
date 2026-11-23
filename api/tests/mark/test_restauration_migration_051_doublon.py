"""[.mark] Contrôle d'avant le banc (23/11), Pierre A1 : la migration 051 (clé anti-doublon hors commandes annulées), montée et descente, jouées sur une COPIE.

| Test | Ce qu'il prouve |
|---|---|
| montée, descente, remontée | l'index est partiel (une annulée et une vivante peuvent porter la même clé, deux vivantes non) ; la descente vide la clé de l'annulée, se rejoue, ne perd aucune commande ; la remontée remet l'état d'avant |
| arbitre | l'arbitre ``ON CONFLICT`` de la caisse est accepté par l'index de la 051 (sinon 42P10 à chaque commande de la caisse) |
| texte | le ``WHERE`` de l'arbitre dans ``restauration_liaison`` est celui de la 051 |
"""

from __future__ import annotations

import uuid
from pathlib import Path

import asyncpg
import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import restauration_liaison as lia
from api.tests.mark.partie_1.aides_briques import descendre_jusqu_a
from api.tests.mark.test_base_client import _serveur, base_essai, base_prete  # noqa: F401

DESCENTE = Path(schema.__file__).parent / "migrations" / "descentes" / "051-descente.sql"
MONTEE = Path(schema.__file__).parent / "migrations" / "051-doublon-hors-commandes-annulees.sql"
AJOUT = "INSERT INTO mark.resto_commande (numero, numero_court, site_id, mode, total, statut, cle_doublon) VALUES ($1, 'C1', $2, 'emporter', 1000, $3, $4)"
CONDITION = "WHERE cle_doublon IS NOT NULL AND statut <> 'annulee'"


async def _index(c) -> str:
    return await c.fetchval("SELECT indexdef FROM pg_indexes WHERE schemaname = 'mark' AND indexname = 'resto_commande_doublon_idx'")


async def _site(c) -> int:
    await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('E')")
    return await c.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom) SELECT id, 'a', 'A' FROM mark.entreprise LIMIT 1 RETURNING id")


async def test_la_051_se_monte_se_descend_et_se_remonte_sans_perdre_une_commande(base_prete):
    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert (await schema.version_de(c)) >= 51 and "annulee" in await _index(c)
        site = await _site(c)
        annulee, vivante = uuid.uuid4(), uuid.uuid4()
        await c.execute(AJOUT, annulee, site, "annulee", "appel:1")
        await c.execute(AJOUT, vivante, site, "nouvelle", "appel:1")  # permis : l'annulée n'est plus « déjà faite »
        with pytest.raises(asyncpg.UniqueViolationError):
            await c.execute(AJOUT, uuid.uuid4(), site, "nouvelle", "appel:1")  # deux vivantes : refusé

        for _ in range(2):  # la descente se rejoue (les migrations plus hautes d'abord : l'ordre des descentes)
            await descendre_jusqu_a(c, 51)
        assert (await schema.version_de(c)) == 50 and "annulee" not in await _index(c)
        assert await c.fetchval("SELECT count(*) FROM mark.resto_commande") == 2  # rien de perdu
        assert await c.fetchval("SELECT cle_doublon FROM mark.resto_commande WHERE numero = $1", annulee) is None
        assert await c.fetchval("SELECT cle_doublon FROM mark.resto_commande WHERE numero = $1", vivante) == "appel:1"
        with pytest.raises(asyncpg.UniqueViolationError):
            await c.execute(AJOUT, uuid.uuid4(), site, "annulee", "appel:1")  # avant la 051 : l'index couvre toutes les commandes

        assert 51 in await schema.appliquer_migrations(c)
        assert (await schema.version_de(c)) >= 51 and "annulee" in await _index(c)
        await c.execute(AJOUT, uuid.uuid4(), site, "annulee", "appel:1")  # la remontée remet l'état d'avant
        assert await c.fetchval("SELECT count(*) FROM mark.resto_commande") == 3
    finally:
        await c.close()


async def test_l_arbitre_de_la_caisse_est_accepte_par_l_index_de_la_051(base_prete):
    c = await schema.connecter_proprietaire(base_prete)
    try:
        site = await _site(c)
        sql = (f"INSERT INTO mark.resto_commande (numero, numero_court, site_id, mode, total, statut, cle_doublon) VALUES ($1, 'C1', $2, 'emporter', 1000, 'acceptee', $3) "
               f"ON CONFLICT (site_id, cle_doublon) {CONDITION} DO NOTHING RETURNING numero")
        assert await c.fetchval(sql, uuid.uuid4(), site, "caisse:x") is not None
        assert await c.fetchval(sql, uuid.uuid4(), site, "caisse:x") is None  # rejeu : pas de doublon
    finally:
        await c.close()


def test_l_arbitre_de_la_caisse_porte_le_meme_where_que_l_index():
    assert f"{CONDITION} DO NOTHING" in Path(lia.__file__).read_text(encoding="utf-8")
    assert CONDITION in MONTEE.read_text(encoding="utf-8")
