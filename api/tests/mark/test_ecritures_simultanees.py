"""[.mark] Constat 28 du chantier cloture-code-avant-migration : deux modifications SIMULTANÉES d'une même fiche
ou d'une même personne ne se défont pas.

Une écriture par élément lit la fiche (ou la personne), pose les champs envoyés, réécrit le tout. Sans verrou, la
seconde relit AVANT que la première écrive et la remplace : la valeur de la première disparaît. Par la vraie route
et la vraie base du client.

| Test | Ce qu'il prouve |
|---|---|
| fiche | deux PATCH en même temps sur deux champs d'une même fiche : les deux valeurs restent, dans la base du client et dans la copie |
| personne | deux PATCH en même temps sur deux champs d'une même personne : les deux valeurs restent |
| deux fiches | deux PATCH en même temps sur deux fiches différentes : la copie (miroir) garde les deux |

Épreuve par mutation (faite à la main le 22/10, puis annulée) : retirer le verrou fait rougir les deux premiers. Le
troisième reste vert sans verrou (la fenêtre de course du miroir est trop courte pour être rejouée à coup sûr) : il
garde la copie, il ne prouve pas le verrou.
"""

from __future__ import annotations

import asyncio

import pytest

from api.tests.mark.test_agents_servis import (  # noqa: F401  (fixtures)
    _client,
    base_v4,
    smtp,
)
from api.tests.mark.test_base_client import _RedisFactice, base_essai  # noqa: F401
from api.tests.mark.test_ecritures_par_element import (  # noqa: F401
    RACINE,
    _garnir,
    _installer,
    _rediriger,
)


@pytest.fixture
def base_de_dograh_une_requete_a_la_fois(db_session):
    """La base de Dograh des tests est UNE session partagée : deux requêtes qui la touchent ensemble se
    marcheraient dessus (« another operation is in progress »), ce qui n'a rien à voir avec ce qu'on prouve ici.
    Chaque emploi de la session passe donc l'un après l'autre ; la base DU CLIENT, elle, reste en vraies
    connexions séparées, et c'est elle qui porte les verrous éprouvés."""
    tour = asyncio.Lock()
    ouvrir = db_session.async_session

    class _Un:
        def __init__(self):
            self._contexte = ouvrir()

        async def __aenter__(self):
            await tour.acquire()
            return await self._contexte.__aenter__()

        async def __aexit__(self, *exc):
            try:
                return await self._contexte.__aexit__(*exc)
            finally:
                tour.release()

    db_session.async_session = lambda: _Un()
    yield
    db_session.async_session = ouvrir


async def test_deux_modifications_simultanees_d_une_meme_fiche_gardent_les_deux_valeurs(
    base_v4, smtp, db_session, async_session, base_de_dograh_une_requete_a_la_fois
):
    _user, org, entetes = await _installer(db_session, async_session, base_v4)
    with _rediriger():
        async with _client() as client:
            await _garnir(client, entetes)
            reponses = await asyncio.gather(
                client.patch(f"{RACINE}/etablissements/nord", json={"nom": "Nord bis"}, headers=entetes),
                client.patch(f"{RACINE}/etablissements/nord", json={"annonce_pause": "Pause longue"}, headers=entetes),
            )
            assert [r.status_code for r in reponses] == [200, 200], [r.text for r in reponses]
            fiche = next(
                e for e in (await client.get(f"{RACINE}/etablissements", headers=entetes)).json()["etablissements"]
                if e["id"] == "nord"
            )
            assert fiche["nom"] == "Nord bis"
            assert fiche["annonce_pause"] == "Pause longue"
    # La copie que les appels lisent (le miroir) dit la même chose.
    from api.services.etablissements.stockage import _miroir_etablissements_strict

    miroir = next(e for e in (await _miroir_etablissements_strict(org)).etablissements if e.id == "nord")
    assert (miroir.nom, miroir.annonce_pause) == ("Nord bis", "Pause longue")


async def test_deux_modifications_simultanees_d_une_meme_personne_gardent_les_deux_valeurs(
    base_v4, smtp, db_session, async_session, base_de_dograh_une_requete_a_la_fois
):
    _user, _org, entetes = await _installer(db_session, async_session, base_v4)
    with _rediriger():
        async with _client() as client:
            await _garnir(client, entetes)
            reponses = await asyncio.gather(
                client.patch(f"{RACINE}/equipe/personnes/alice", json={"role": "Cheffe"}, headers=entetes),
                client.patch(f"{RACINE}/equipe/personnes/alice", json={"description": "Direction"}, headers=entetes),
            )
            assert [r.status_code for r in reponses] == [200, 200], [r.text for r in reponses]
            equipe = (await client.get(f"{RACINE}/equipe", headers=entetes)).json()
            alice = next(p for p in equipe["personnes"] if p["cle"] == "alice")
            assert alice["role"] == "Cheffe"
            assert alice["description"] == "Direction"


async def test_deux_modifications_simultanees_de_deux_fiches_gardent_les_deux_dans_la_copie(
    base_v4, smtp, db_session, async_session, base_de_dograh_une_requete_a_la_fois
):
    _user, org, entetes = await _installer(db_session, async_session, base_v4)
    with _rediriger():
        async with _client() as client:
            await _garnir(client, entetes)
            reponses = await asyncio.gather(
                client.patch(f"{RACINE}/etablissements/nord", json={"nom": "Nord bis"}, headers=entetes),
                client.patch(f"{RACINE}/etablissements/sud", json={"nom": "Sud bis"}, headers=entetes),
            )
            assert [r.status_code for r in reponses] == [200, 200], [r.text for r in reponses]
    from api.services.etablissements.stockage import _miroir_etablissements_strict

    miroir = {e.id: e.nom for e in (await _miroir_etablissements_strict(org)).etablissements}
    assert miroir == {"nord": "Nord bis", "sud": "Sud bis"}


async def test_sans_base_du_client_l_ecriture_d_une_fiche_passe_par_le_verrou_de_dograh(
    smtp, db_session, async_session
):
    """Une organisation sans base du client : le miroir est la source, le verrou est pris dans la base de
    Dograh (séquentiel ici : la session de test est unique)."""
    from api.tests.mark.test_agents_servis import _cle, _groupe_avec_capacites

    user, principal, _specialise = await _groupe_avec_capacites(db_session, async_session)
    entetes = {"X-API-Key": await _cle(db_session, principal.organization_id, user.id)}
    with _rediriger():
        async with _client() as client:
            r = await client.put(
                f"{RACINE}/etablissements",
                json={"etablissements": [{"id": "nord", "nom": "Nord"}, {"id": "sud", "nom": "Sud"}]},
                headers=entetes,
            )
            assert r.status_code == 200, r.text
            r = await client.patch(f"{RACINE}/etablissements/nord", json={"nom": "Nord bis"}, headers=entetes)
            assert r.status_code == 200, r.text
            r = await client.patch(f"{RACINE}/etablissements/nord", json={"annonce_pause": "Pause"}, headers=entetes)
            assert r.status_code == 200 and r.json()["nom"] == "Nord bis"
            lues = (await client.get(f"{RACINE}/etablissements", headers=entetes)).json()["etablissements"]
            assert [(e["id"], e["nom"]) for e in lues] == [("nord", "Nord bis"), ("sud", "Sud")]
