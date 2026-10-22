"""[.mark] Lot F4 du chantier cloture-code-avant-migration : les écritures PAR ÉLÉMENT, par la vraie route et la
vraie authentification (une clé d'API de l'organisation), sur une vraie base du client.

Règle du 22/10 : aucune restriction de champ dans le fork (ce que le client peut changer se décide au portail) ;
en revanche un champ absent n'est JAMAIS lu comme « vide » : phrases, lexique, numéros, sujets survivent à un
envoi incomplet.

| Test | Ce qu'il prouve |
|---|---|
| fiche | un envoi d'un seul champ ne touche que lui (phrases, lexique, numéros, fermeture gardés) ; une phrase envoyée vide est retirée ; l'ordre et les autres fiches ne bougent pas ; le journal dit « portail : … » |
| fermer | `/etat` ferme puis rouvre, sans rien toucher d'autre |
| personne | un envoi d'un champ ne touche que lui, les autres personnes et les sujets restent ; lieu inconnu refusé |
| planificateur | un réglage envoyé ne change que lui, au niveau demandé ; un type ajouté ne retire pas les autres ; retrait nommé |
| refus | sans clé : 401 ; la clé d'une autre organisation : 404 ; champ inconnu : 422 |
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx

from api.db.bases_clients import connexion as schema
from api.enums import OrganizationConfigurationKey
from api.tests.mark.test_agents_servis import (  # noqa: F401  (fixtures)
    _client,
    _cle,
    _groupe_avec_capacites,
    _organisation,
    base_v4,
    smtp,
)
from api.tests.mark.test_base_client import _RedisFactice, base_essai  # noqa: F401

RACINE = "/api/v1/organizations"


async def _installer(db_session, async_session, base_v4):
    """Une organisation avec sa base, deux fiches, une phrase au niveau fiche, une équipe et deux sujets."""
    user, principal, _specialise = await _groupe_avec_capacites(db_session, async_session)
    org = principal.organization_id
    await db_session.upsert_configuration(
        org, OrganizationConfigurationKey.BASE_CLIENT.value, {"nom_base": base_v4}
    )
    cle = await _cle(db_session, org, user.id)
    return user, org, {"X-API-Key": cle, "X-Mark-Auteur": "Camille Dupont"}


async def _journal(base, table):
    c = await schema.connecter(base)
    try:
        return [
            (r["ligne_id"], r["auteur"])
            for r in await c.fetch(
                "SELECT ligne_id, auteur FROM mark.journal_modif WHERE table_nom = $1 ORDER BY id", table
            )
        ]
    finally:
        await c.close()


async def _garnir(client, entetes):
    r = await client.put(
        f"{RACINE}/phrases",
        json={"phrases": [
            {"variable": "mot_du_lieu", "contenu": "Bienvenue", "niveau": "etablissement"},
            {"variable": "mot_commun", "contenu": "Bonjour", "niveau": "organisation"},
        ]},
        headers=entetes,
    )
    assert r.status_code == 200, r.text
    r = await client.put(
        f"{RACINE}/etablissements",
        json={"etablissements": [
            {
                "id": "nord", "nom": "Nord", "horaires_ouverture": None,
                "phrases": {"mot_du_lieu": "Bienvenue au nord"},
                "termes_lexique": [{"terme": "Edilkamin", "variantes": ["edil camin"]}],
                "annonce_pause": "Pause en cours",
            },
            {"id": "sud", "nom": "Sud"},
        ]},
        headers=entetes,
    )
    assert r.status_code == 200, r.text
    r = await client.put(
        f"{RACINE}/equipe",
        json={
            "personnes": [
                {"cle": "alice", "prenom": "Alice", "nom": "Martin", "mail": "alice@example.org",
                 "etablissements": ["nord"], "description": "Accueil"},
                {"cle": "bruno", "prenom": "Bruno", "etablissements": []},
            ],
            "sujets": [{"code": "devis", "libelle": "Devis", "destinataires": ["alice", "bruno"]}],
        },
        headers=entetes,
    )
    assert r.status_code == 200, r.text


def _rediriger():
    from api.services.etablissements import copie as module_copie

    return patch.object(module_copie, "_redis", AsyncMock(return_value=_RedisFactice()))


async def test_un_envoi_d_un_seul_champ_d_une_fiche_ne_touche_que_lui(
    base_v4, smtp, db_session, async_session
):
    _user, _org, entetes = await _installer(db_session, async_session, base_v4)
    with _rediriger():
        async with _client() as client:
            await _garnir(client, entetes)
            avant = (await client.get(f"{RACINE}/etablissements", headers=entetes)).json()
            r = await client.patch(f"{RACINE}/etablissements/nord", json={"nom": "Nord bis"}, headers=entetes)
            assert r.status_code == 200, r.text
            fiche = r.json()
            assert fiche["nom"] == "Nord bis"
            # Tout le reste de la fiche a survécu à un envoi qui ne le portait pas.
            assert fiche["phrases"] == {"mot_du_lieu": "Bienvenue au nord"}
            assert [t["terme"] for t in fiche["termes_lexique"]] == ["Edilkamin"]
            assert fiche["annonce_pause"] == "Pause en cours"
            apres = (await client.get(f"{RACINE}/etablissements", headers=entetes)).json()
            assert [e["id"] for e in apres["etablissements"]] == ["nord", "sud"]
            assert apres["etablissements"][1] == avant["etablissements"][1]
            # Une phrase envoyée vide est retirée, une autre variable envoyée s'ajoute sans effacer.
            r = await client.patch(
                f"{RACINE}/etablissements/nord", json={"phrases": {"mot_du_lieu": ""}}, headers=entetes
            )
            assert r.status_code == 200 and r.json()["phrases"] == {}
            r = await client.patch(
                f"{RACINE}/etablissements/nord", json={"phrases": {"mot_du_lieu": "Re"}}, headers=entetes
            )
            assert r.json()["phrases"] == {"mot_du_lieu": "Re"} and r.json()["nom"] == "Nord bis"
            # Une phrase qui n'est pas au niveau de la fiche est refusée, rien n'est écrit.
            r = await client.patch(
                f"{RACINE}/etablissements/nord", json={"phrases": {"mot_commun": "x"}}, headers=entetes
            )
            assert r.status_code == 422
            # Fiche inconnue : 404 ; champ inconnu : 422.
            assert (await client.patch(f"{RACINE}/etablissements/ailleurs", json={"nom": "x"}, headers=entetes)).status_code == 404
            assert (await client.patch(f"{RACINE}/etablissements/nord", json={"inconnu": 1}, headers=entetes)).status_code == 422
    lignes = await _journal(base_v4, "site")
    assert lignes and lignes[-1][1].startswith("portail : Camille Dupont (dograh:")


async def test_fermer_puis_rouvrir_une_fiche_sans_rien_toucher_d_autre(
    base_v4, smtp, db_session, async_session
):
    _user, _org, entetes = await _installer(db_session, async_session, base_v4)
    with _rediriger():
        async with _client() as client:
            await _garnir(client, entetes)
            r = await client.post(
                f"{RACINE}/etablissements/nord/etat", json={"etat_force": "FERME"}, headers=entetes
            )
            assert r.status_code == 200, r.text
            assert r.json()["etat_force"] == "FERME" and r.json()["phrases"] == {"mot_du_lieu": "Bienvenue au nord"}
            r = await client.post(
                f"{RACINE}/etablissements/nord/etat", json={"etat_force": None}, headers=entetes
            )
            assert r.json()["etat_force"] is None and r.json()["annonce_pause"] == "Pause en cours"
            # Une fin sans état forcé ne veut rien dire.
            r = await client.post(
                f"{RACINE}/etablissements/nord/etat",
                json={"etat_force": None, "etat_force_jusqu_a": "2030-01-01T10:00:00"},
                headers=entetes,
            )
            assert r.status_code == 422


async def test_un_envoi_d_un_champ_d_une_personne_ne_touche_ni_l_equipe_ni_les_sujets(
    base_v4, smtp, db_session, async_session
):
    _user, _org, entetes = await _installer(db_session, async_session, base_v4)
    with _rediriger():
        async with _client() as client:
            await _garnir(client, entetes)
            r = await client.patch(f"{RACINE}/equipe/personnes/alice", json={"role": "Cheffe"}, headers=entetes)
            assert r.status_code == 200, r.text
            alice = r.json()
            assert alice["role"] == "Cheffe" and alice["mail"] == "alice@example.org"
            assert alice["etablissements"] == ["nord"] and alice["description"] == "Accueil"
            equipe = (await client.get(f"{RACINE}/equipe", headers=entetes)).json()
            assert [p["cle"] for p in equipe["personnes"]] == ["alice", "bruno"]
            assert all(p["actif"] for p in equipe["personnes"])
            assert equipe["sujets"][0]["destinataires"] == ["alice", "bruno"]
            # Ses lieux, quand ils sont envoyés, la remplacent ; un lieu inconnu est refusé.
            r = await client.patch(f"{RACINE}/equipe/personnes/alice", json={"etablissements": []}, headers=entetes)
            assert r.json()["etablissements"] == [] and r.json()["role"] == "Cheffe"
            assert (await client.patch(f"{RACINE}/equipe/personnes/alice", json={"etablissements": ["nulle-part"]}, headers=entetes)).status_code == 422
            assert (await client.patch(f"{RACINE}/equipe/personnes/zoe", json={"role": "x"}, headers=entetes)).status_code == 404
            # Sa désactivation passe par le même envoi, sans toucher à l'autre.
            r = await client.patch(f"{RACINE}/equipe/personnes/bruno", json={"actif": False}, headers=entetes)
            assert r.json()["actif"] is False
            equipe = (await client.get(f"{RACINE}/equipe", headers=entetes)).json()
            assert {p["cle"]: p["actif"] for p in equipe["personnes"]} == {"alice": True, "bruno": False}
    assert any(a.startswith("portail : Camille Dupont") for _l, a in await _journal(base_v4, "personne"))


async def test_le_planificateur_change_un_reglage_a_un_niveau_sans_toucher_au_reste(
    base_v4, smtp, db_session, async_session
):
    _user, _org, entetes = await _installer(db_session, async_session, base_v4)
    with _rediriger():
        async with _client() as client:
            await _garnir(client, entetes)
            r = await client.put(
                f"{RACINE}/planificateur",
                json={
                    "reglages": {"nombre_creneaux": 4, "pas_min": 15},
                    "par_etablissement": {"nord": {"horizon_jours": 7}},
                    "types": [{"code": "visite", "libelle": "Visite", "duree_min": 60}],
                },
                headers=entetes,
            )
            assert r.status_code == 200, r.text
            r = await client.patch(
                f"{RACINE}/planificateur",
                json={"reglages": {"pas_min": 20}},
                headers=entetes,
            )
            assert r.status_code == 200, r.text
            p = r.json()
            assert p["reglages"]["pas_min"] == 20 and p["reglages"]["nombre_creneaux"] == 4
            assert p["par_etablissement"]["nord"]["horizon_jours"] == 7
            # Un établissement : ses surcharges seulement.
            r = await client.patch(
                f"{RACINE}/planificateur",
                json={"etablissement": "nord", "reglages": {"nombre_creneaux": 2}},
                headers=entetes,
            )
            p = r.json()
            assert p["par_etablissement"]["nord"] == {**p["par_etablissement"]["nord"], "nombre_creneaux": 2, "horizon_jours": 7}
            assert p["reglages"]["nombre_creneaux"] == 4
            # Un type ajouté ne retire pas les autres ; un retrait se nomme.
            r = await client.patch(
                f"{RACINE}/planificateur",
                json={"types": [{"code": "devis", "libelle": "Devis", "duree_min": 30}]},
                headers=entetes,
            )
            assert sorted(t["code"] for t in r.json()["types"]) == ["devis", "visite"]
            r = await client.patch(
                f"{RACINE}/planificateur", json={"types_retires": [{"code": "visite"}]}, headers=entetes
            )
            assert [t["code"] for t in r.json()["types"]] == ["devis"]
            # Établissement inconnu, plages illisibles, réglage inconnu : refusés.
            for corps in (
                {"etablissement": "ailleurs", "reglages": {"pas_min": 30}},
                {"reglages": {"plages": "lundi : n'importe quoi"}},
                {"reglages": {"inconnu": 1}},
            ):
                assert (await client.patch(f"{RACINE}/planificateur", json=corps, headers=entetes)).status_code == 422
    assert any(a.startswith("portail : Camille Dupont") for _l, a in await _journal(base_v4, "reglage_planificateur"))


async def test_les_ecritures_par_element_refusent_sans_cle_et_avec_la_cle_d_une_autre_organisation(
    base_v4, smtp, db_session, async_session
):
    _user, _org, entetes = await _installer(db_session, async_session, base_v4)
    autre = await _organisation(async_session, db_session)
    cle_b = await _cle(db_session, autre.organisation.id, autre.utilisateur.id)
    appels = [
        ("patch", f"{RACINE}/etablissements/nord", {"nom": "Piraté"}),
        ("post", f"{RACINE}/etablissements/nord/etat", {"etat_force": "FERME"}),
        ("patch", f"{RACINE}/equipe/personnes/alice", {"role": "Piraté"}),
        ("patch", f"{RACINE}/planificateur", {"reglages": {"pas_min": 5}}),
    ]
    with _rediriger():
        async with _client() as client:
            await _garnir(client, entetes)
            for methode, chemin, corps in appels:
                for en_tetes in ({}, {"X-API-Key": "dgr_fausse_cle_0123456789"}):
                    assert (await getattr(client, methode)(chemin, json=corps, headers=en_tetes)).status_code == 401
                # L'autre organisation : ni fiche, ni personne chez elle (pas de base : 404 ou 409), jamais 200.
                reponse = await getattr(client, methode)(chemin, json=corps, headers={"X-API-Key": cle_b})
                assert reponse.status_code in (404, 409), (chemin, reponse.status_code, reponse.text)
            assert (await client.get(f"{RACINE}/etablissements", headers=entetes)).json()["etablissements"][0]["nom"] == "Nord"
