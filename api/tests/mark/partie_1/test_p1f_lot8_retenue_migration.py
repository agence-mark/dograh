"""[.mark] Plan final Partie 1, lot 8b-1a (E1, § 17) : le statut ``retenue`` (la commande écrite en base au « oui », pas encore envoyable), migration 054.

| Test | Ce qu'il prouve |
|---|---|
| montée, descente, remontée | la 054 accepte ``retenue`` ; la descente la refuse de nouveau sans perdre une commande (une ligne ``retenue`` redevient ``nouvelle`` : ce que l'ancien code envoyait) ; la remontée remet l'état |
| transitions | ``retenue`` ne mène qu'à ``nouvelle`` (l'envoi de la fin de l'appel) ou ``annulee`` (jamais accordée) ; un pas rejoué ne passe qu'une fois |
| rattrapage | une ligne ``retenue`` n'est ni reprise ni « sans réponse » : elle ne part que par la fin de l'appel |
| compte du client | ``retenue → annulee`` sort la commande du compte du client, une seule fois (A6) |
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import restauration
from api.db.bases_clients import restauration_liaison as liaison
from api.db.bases_clients.restauration_commande import TRANSITIONS
from api.tests.mark import test_base_client as _base
from api.tests.mark import test_restauration_classeur_commande as _classeur
from api.tests.mark.partie_1.aides_briques import descendre_jusqu_a

# Fixtures du dossier reprises par nom, sans import de nom ni rustine de lint.
base_essai = _base.base_essai
base_prete = _base.base_prete
commerce = _classeur.commerce

AJOUT = "INSERT INTO mark.resto_commande (numero, numero_court, site_id, mode, total, statut) VALUES ($1, 'C1', $2, 'emporter', 1000, $3)"


async def _site(c) -> int:
    await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('E')")
    return await c.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom) SELECT id, 'a', 'A' FROM mark.entreprise LIMIT 1 RETURNING id")


async def test_la_054_se_monte_se_descend_et_se_remonte_sans_perdre_une_commande(base_prete):
    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert await c.fetchval("SELECT 1 FROM mark.schema_version WHERE version = 54") == 1
        site = await _site(c)
        retenue = uuid.uuid4()
        await c.execute(AJOUT, retenue, site, "retenue")

        for _ in range(2):  # la descente se rejoue
            await descendre_jusqu_a(c, 54)
        assert await c.fetchval("SELECT 1 FROM mark.schema_version WHERE version = 54") is None
        assert await c.fetchval("SELECT statut FROM mark.resto_commande WHERE numero = $1", retenue) == "nouvelle"  # rien de perdu
        with pytest.raises(asyncpg.CheckViolationError):
            await c.execute(AJOUT, uuid.uuid4(), site, "retenue")

        assert 54 in await schema.appliquer_migrations(c)
        await c.execute(AJOUT, uuid.uuid4(), site, "retenue")
        assert await c.fetchval("SELECT count(*) FROM mark.schema_version WHERE version = 54") == 1
    finally:
        await c.close()


def test_retenue_ne_mene_qu_a_l_envoi_ou_a_l_annulation():
    assert TRANSITIONS["retenue"] == frozenset({"nouvelle", "annulee"})
    assert all("retenue" not in suivants for de, suivants in TRANSITIONS.items() if de != "retenue")  # rien ne revient à « retenue »


async def _retenue(commerce) -> str:
    r = await _classeur.enregistrer(commerce)
    numero = r.faits["numero"]
    await commerce.c.execute("UPDATE mark.resto_commande SET statut = 'retenue', maj_le = maj_le - interval '1 hour' WHERE numero = $1::uuid", numero)
    return numero


async def test_une_ligne_retenue_n_est_jamais_reprise_par_le_rattrapage(commerce):
    numero = await _retenue(commerce)
    assert numero not in await liaison.commandes_a_reprendre(commerce.c, commerce.a)
    assert numero not in [x["numero"] for x in await liaison.commandes_sans_reponse(commerce.c, commerce.a, depuis_minutes=0)]


async def test_retenue_puis_annulee_sort_du_compte_du_client_une_seule_fois(commerce):
    numero = await _retenue(commerce)
    compte = "SELECT nb_commandes FROM mark.resto_client WHERE site_id = $1 AND telephone = $2"
    avant = await commerce.c.fetchval(compte, commerce.a, _classeur.TEL)
    assert (await restauration.changer_statut(commerce.c, commerce.a, numero, "retenue", "annulee", "agent")).statut == "OK"
    assert (await restauration.changer_statut(commerce.c, commerce.a, numero, "retenue", "annulee", "agent")).statut == "DEJA_FAIT"
    assert await commerce.c.fetchval(compte, commerce.a, _classeur.TEL) == avant - 1


async def test_retenue_puis_nouvelle_ne_passe_qu_une_fois(commerce):
    numero = await _retenue(commerce)
    assert (await restauration.changer_statut(commerce.c, commerce.a, numero, "retenue", "nouvelle", "agent")).statut == "OK"
    assert (await restauration.changer_statut(commerce.c, commerce.a, numero, "retenue", "nouvelle", "agent")).statut == "DEJA_FAIT"
    assert (await restauration.changer_statut(commerce.c, commerce.a, numero, "retenue", "annulee", "agent")).statut == "INTERDIT"
