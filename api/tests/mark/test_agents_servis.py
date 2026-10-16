"""[.mark] Chantier agents-specialises, lot 9 (= lot 6 du plan fiche-etablissement) : les agents que l'organisation
sert, lus pour le portail ; le groupe ; le rattachement ; l'accès par clé d'API (C7) ; le contrôle des horaires ;
la mise à niveau de toutes les bases.

Plan `Labo-agent-vocal/plans/agents-specialises/` (M9, M10, D3, D89, D90, A13, C5, C7). Les routes sont jouées
par la VRAIE authentification (une vraie clé d'API, jamais une surcharge de l'utilisateur), sur la base de test.

| Test | Ce qu'il prouve |
|---|---|
| capacités | chaque capacité allumée puis éteinte dans une définition publiée se lit juste |
| groupe | le principal, ses spécialisés, qui appelle qui, les capacités de l'ENSEMBLE |
| liens | un lien vers un agent d'une autre organisation n'existe pas ; un principal n'est jamais le spécialisé d'un autre |
| routes et clés | sans clé ou avec une fausse clé : refusé ; la clé d'une autre organisation ne voit rien et ne rattache rien |
| rattachement | rattacher un principal rattache ses spécialisés ; détacher de même ; rejouable |
| auteur | l'auteur réel du portail est au journal ; jamais pour une session ; nettoyé |
| clé | la clé n'apparaît ni dans une réponse ni dans un journal |
| horaires | le point d'entrée dit « valide » ou la raison, sans rien écrire |
| mise à niveau | toutes les bases montent, un échec n'arrête pas les autres, jamais deux fois une migration |
"""

from __future__ import annotations

import copy
import json
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import asyncpg
import httpx
import pytest
from loguru import logger

from api.db.bases_clients import connexion as schema
from api.enums import OrganizationConfigurationKey
from api.services.auth.depends import auteur_du_portail
from api.services.groupe.agents_servis import lire_agents_servis, membres_a_rattacher
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401  (fixtures)
from api.tests.mark.test_base_client import (
    _RedisFactice,
    _serveur,
    base_essai,
    base_prete,
)  # noqa: F401
from api.tests.mark.test_clavier_porte_la_fiche import FICHE
from api.tests.mark.test_passation_clavier import _arete, _groupe, _noeud, _republier

ROUTE = "/api/v1/organizations/agents-servis"


async def _oublier(async_session):
    """Un appel de l'API ouvre sa propre session ; dans le test, une seule session sert à tout : on l'oublie
    entre deux publications pour lire ce que la base dit (et non sa mémoire)."""
    await async_session.flush()
    async_session.expunge_all()


def _definition(outils=()):
    return {
        "nodes": [
            _noeud(
                "a", "startCall", "accueil", "Tu accueilles.", tool_uuids=list(outils)
            ),
            _noeud("f", "endCall", "fin", "Conclure."),
        ],
        "edges": [_arete("a", "f", "fin")],
    }


async def _outil(db_session, org, nom, categorie, definition):
    return await db_session.create_tool(
        organization_id=org.organisation.id,
        user_id=org.utilisateur.id,
        name=nom,
        description=nom,
        category=categorie,
        definition=definition,
    )


def _integration(connecteur, action):
    return {
        "type": "integration",
        "config": {"connecteur": connecteur, "action": action, "delai_ms": 5000},
    }


# --------------------------------------------------------------------------- #
# 1. Les capacités, lues dans la définition publiée (D89)
# --------------------------------------------------------------------------- #

TOUTES_ETEINTES = {
    "transfert": False,
    "demande_transmise": False,
    "rendez_vous": False,
    "mail": False,
    "sms": False,
    "verification": False,
}


async def _capacites(db_session, org, async_session):
    # Un appel de l'API ouvre sa propre session ; dans le test, une seule session sert à tout : on l'oublie
    # entre deux publications pour lire ce que la base dit (et non sa mémoire).
    await _oublier(async_session)
    servis = await lire_agents_servis(org.organisation.id)
    [agent] = [a for a in servis.agents if a.id == org.agent.id]
    return agent.capacites.model_dump()


async def test_chaque_capacite_allumee_puis_eteinte_se_lit_juste(
    db_session, async_session
):
    org = await _organisation(async_session, db_session, actif=False)
    base = {}
    # (nom, ce qu'on allume, ce qui doit s'allumer)
    cas = [
        (
            "transfert par un transfert d'appel",
            "transfer_call",
            {
                "schema_version": 1,
                "type": "transfer_call",
                "config": {"destination": "+33600000000"},
            },
            None,
            {"transfert": True},
        ),
        (
            "direction vers une personne",
            "integration",
            _integration("equipe", "diriger_vers_personne"),
            None,
            {"transfert": True, "demande_transmise": True},
        ),
        (
            "rendez-vous : les créneaux",
            "integration",
            _integration("planificateur", "proposer_creneaux"),
            None,
            {"rendez_vous": True},
        ),
        (
            "rendez-vous : la pose",
            "integration",
            _integration("planificateur", "poser_rendez_vous"),
            None,
            {"rendez_vous": True},
        ),
    ]
    for nom, categorie, definition, _, attendu in cas:
        outil = await _outil(db_session, org, nom, categorie, definition)
        await _republier(db_session, org.agent, _definition([outil.tool_uuid]), base)
        assert await _capacites(db_session, org, async_session) == {
            **TOUTES_ETEINTES,
            **attendu,
        }, nom
        await _republier(db_session, org.agent, _definition(), base)
        assert await _capacites(db_session, org, async_session) == TOUTES_ETEINTES, (
            f"{nom} éteint"
        )
    # Un outil d'une autre sorte (calculatrice) ne dit aucune capacité.
    autre = await _outil(
        db_session, org, "Calcul", "calculator", {"type": "calculator", "config": {}}
    )
    await _republier(db_session, org.agent, _definition([autre.tool_uuid]), base)
    assert await _capacites(db_session, org, async_session) == TOUTES_ETEINTES
    # Les réglages : courriel, SMS (appelant, puis équipe), vérification.
    reglages = [
        ({"apres_appel": {"actif": True, "mail": True}}, {"mail": True}),
        ({"apres_appel": {"actif": True, "mail": False}}, {}),
        (
            {"apres_appel": {"actif": False, "mail": True}},
            {},
        ),  # l'après-appel éteint : rien ne part
        (
            {
                "apres_appel": {
                    "actif": True,
                    "mail": False,
                    "sms": {"appelant": {"actif": True, "texte": "Merci"}},
                }
            },
            {"sms": True},
        ),
        (
            {
                "apres_appel": {
                    "actif": True,
                    "mail": False,
                    "sms": {
                        "equipe": {
                            "actif": True,
                            "texte": "Alerte",
                            "numeros": ["+33611111111"],
                        }
                    },
                }
            },
            {"sms": True},
        ),
        ({"verification_appelant": True}, {"verification": True}),
        ({"verification_appelant": False}, {}),
    ]
    for config, attendu in reglages:
        await _republier(db_session, org.agent, _definition(), config)
        assert await _capacites(db_session, org, async_session) == {
            **TOUTES_ETEINTES,
            **attendu,
        }, config
    # Jamais publié sur la version courante : on lit la publiée, pas le brouillon.
    await db_session.save_workflow_draft(
        org.agent.id,
        workflow_definition=_definition(),
        workflow_configurations={"verification_appelant": True},
    )
    assert await _capacites(db_session, org, async_session) == {
        **TOUTES_ETEINTES
    }  # la dernière publiée : verification_appelant False


# --------------------------------------------------------------------------- #
# 2. Le groupe : le principal, ses spécialisés, qui appelle qui, l'ensemble
# --------------------------------------------------------------------------- #


async def _groupe_avec_capacites(db_session, async_session):
    user, principal, specialise = await _groupe(db_session, async_session)
    organisation = principal.organization_id
    passation = (
        await db_session.get_tools_for_organization(
            organisation, category="transfer_agent"
        )
    )[0]
    planificateur = await db_session.create_tool(
        organization_id=organisation,
        user_id=user.id,
        name="Creneaux",
        description="x",
        category="integration",
        definition=_integration("planificateur", "proposer_creneaux"),
    )
    # Le spécialisé sait prendre un rendez-vous ; le principal envoie le courriel.
    await _republier(
        db_session,
        specialise,
        _definition([planificateur.tool_uuid]),
        {**copy.deepcopy(FICHE), "agent_principal_id": principal.id},
    )
    await _republier(
        db_session,
        principal,
        _definition([passation.tool_uuid]),
        {
            **copy.deepcopy(FICHE),
            "agents_specialises": [specialise.id],
            "apres_appel": {"actif": True, "mail": True},
        },
    )
    await _oublier(
        async_session
    )  # la session d'essai est unique : on lit ce que la base dit
    return user, principal, specialise


async def test_le_groupe_rend_qui_appelle_qui_et_les_capacites_de_l_ensemble(
    db_session, async_session
):
    user, principal, specialise = await _groupe_avec_capacites(
        db_session, async_session
    )
    servis = await lire_agents_servis(principal.organization_id)
    par_id = {a.id: a for a in servis.agents}
    p, s = par_id[principal.id], par_id[specialise.id]
    assert (p.role, s.role) == ("principal", "specialise")
    assert (
        p.agents_specialises == [specialise.id] and s.agent_principal_id == principal.id
    )
    assert (
        p.appelle == [specialise.id]
        and s.appele_par == [principal.id]
        and p.appele_par == []
        and s.appelle == []
    )
    # Chacun ses capacités ; l'ensemble les réunit.
    assert p.capacites.mail and not p.capacites.rendez_vous
    assert s.capacites.rendez_vous and not s.capacites.mail
    [groupe] = servis.groupes
    assert groupe.principal_id == principal.id and groupe.specialises == [specialise.id]
    assert (
        groupe.capacites.mail
        and groupe.capacites.rendez_vous
        and not groupe.capacites.sms
    )
    assert {(l.de, l.vers, l.par) for l in groupe.passations} == {
        (principal.id, specialise.id, "outil"),
        (specialise.id, principal.id, "retour"),
    }
    # Rattacher le principal, c'est rattacher ses spécialisés avec lui (A13) ; un spécialisé seul : lui seul.
    assert membres_a_rattacher(servis, [principal.id]) == [principal.id, specialise.id]
    assert membres_a_rattacher(servis, [specialise.id]) == [specialise.id]
    assert membres_a_rattacher(servis, [999_999_999]) == []


async def test_un_lien_vers_un_agent_d_une_autre_organisation_n_existe_pas(
    db_session, async_session
):
    user, principal, specialise = await _groupe_avec_capacites(
        db_session, async_session
    )
    autre = await _organisation(async_session, db_session)
    # Le principal déclare, en plus, un agent d'une autre organisation : il n'est pas du groupe.
    await _republier(
        db_session,
        principal,
        _definition(),
        {**copy.deepcopy(FICHE), "agents_specialises": [specialise.id, autre.agent.id]},
    )
    await _oublier(async_session)
    servis = await lire_agents_servis(principal.organization_id)
    assert {a.id for a in servis.agents} == {principal.id, specialise.id}
    [groupe] = servis.groupes
    assert groupe.specialises == [specialise.id]
    # Et l'autre organisation ne voit rien de celle-ci.
    chez_l_autre = await lire_agents_servis(autre.organisation.id)
    assert {a.id for a in chez_l_autre.agents} == {
        autre.agent.id
    } and chez_l_autre.groupes == []


async def test_un_agent_seul_reste_seul_et_un_principal_n_est_jamais_specialise(
    db_session, async_session
):
    org = await _organisation(async_session, db_session)
    seul = await lire_agents_servis(org.organisation.id)
    [agent] = seul.agents
    assert (
        agent.role,
        agent.agents_specialises,
        agent.agent_principal_id,
        seul.groupes,
    ) == ("seul", [], None, [])
    # Deux principaux qui se déclarent l'un l'autre : aucune chaîne, chacun reste principal.
    deux = await db_session.create_workflow(
        name="Second",
        workflow_definition=_definition(),
        user_id=org.utilisateur.id,
        organization_id=org.organisation.id,
    )
    await _republier(
        db_session, org.agent, _definition(), {"agents_specialises": [deux.id]}
    )
    await _republier(
        db_session, deux, _definition(), {"agents_specialises": [org.agent.id]}
    )
    await _oublier(async_session)
    servis = await lire_agents_servis(org.organisation.id)
    assert {a.role for a in servis.agents} == {"principal"}
    assert all(g.specialises == [] for g in servis.groupes)


# --------------------------------------------------------------------------- #
# 3. Les routes, par la vraie authentification (clé d'API de l'organisation, C7)
# --------------------------------------------------------------------------- #


@contextmanager
def _journaux():
    lignes: list[str] = []
    identifiant = logger.add(lambda message: lignes.append(str(message)), level="DEBUG")
    try:
        yield lignes
    finally:
        logger.remove(identifiant)


def _client():
    from api.app import app

    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


async def _cle(db_session, organisation_id, utilisateur_id):
    _modele, brute = await db_session.create_api_key(
        organisation_id, "portail", created_by=utilisateur_id
    )
    return brute


async def test_les_routes_refusent_sans_cle_et_avec_la_cle_d_une_autre_organisation(
    base_v4, smtp, db_session, async_session
):
    user, principal, specialise = await _groupe_avec_capacites(
        db_session, async_session
    )
    org_a = principal.organization_id
    autre = await _organisation(async_session, db_session)
    cle_a = await _cle(db_session, org_a, user.id)
    cle_b = await _cle(db_session, autre.organisation.id, autre.utilisateur.id)
    await db_session.upsert_configuration(
        org_a, OrganizationConfigurationKey.BASE_CLIENT.value, {"nom_base": base_v4}
    )

    with _journaux() as journaux:
        async with _client() as client:
            # Sans clé, avec une fausse clé : refusé, pour la lecture comme pour l'écriture.
            for entetes in ({}, {"X-API-Key": "dgr_fausse_cle_0123456789"}):
                assert (await client.get(ROUTE, headers=entetes)).status_code == 401
                assert (
                    await client.put(
                        f"{ROUTE}/rattachement",
                        json={"workflow_ids": [principal.id]},
                        headers=entetes,
                    )
                ).status_code == 401
                assert (
                    await client.post(
                        "/api/v1/organizations/etablissements/controle-horaires",
                        json={"texte": "lundi : 10:00-18:30"},
                        headers=entetes,
                    )
                ).status_code == 401
            # La clé de A lit les agents de A, seulement.
            vue_a = (await client.get(ROUTE, headers={"X-API-Key": cle_a})).json()
            assert {a["id"] for a in vue_a["agents"]} == {principal.id, specialise.id}
            assert [g["principal_id"] for g in vue_a["groupes"]] == [principal.id]
            # La clé de l'autre organisation ne voit rien de A, et ne rattache rien de A.
            vue_b = (await client.get(ROUTE, headers={"X-API-Key": cle_b})).json()
            assert {a["id"] for a in vue_b["agents"]} == {autre.agent.id} and vue_b[
                "groupes"
            ] == []
            refus = await client.put(
                f"{ROUTE}/rattachement",
                json={"workflow_ids": [principal.id]},
                headers={"X-API-Key": cle_b},
            )
            assert refus.status_code in (404, 409), (
                refus.text
            )  # 404 : agent inconnu ; 409 : pas de base chez B
            # Une base chez B, pour que le refus ne soit pas « pas de base » : toujours 404.
            await db_session.upsert_configuration(
                autre.organisation.id,
                OrganizationConfigurationKey.BASE_CLIENT.value,
                {"nom_base": base_v4},
            )
            refus = await client.put(
                f"{ROUTE}/rattachement",
                json={"workflow_ids": [principal.id, autre.agent.id]},
                headers={"X-API-Key": cle_b},
            )
            assert refus.status_code == 404
            await db_session.upsert_configuration(
                autre.organisation.id,
                OrganizationConfigurationKey.BASE_CLIENT.value,
                {"nom_base": None},
            )
            reponses = [vue_a, vue_b]
    connexion = await schema.connecter(base_v4)
    try:
        assert (
            await connexion.fetchval(
                "SELECT count(*) FROM mark.agent WHERE rattache_le IS NOT NULL"
            )
            == 0
        )
    finally:
        await connexion.close()
    # La clé n'apparaît ni dans une réponse ni dans un journal (jamais plus que son préfixe).
    for cle in (cle_a, cle_b):
        assert not any(cle in ligne for ligne in journaux)
        assert cle not in json.dumps(reponses)


async def test_rattacher_un_principal_rattache_ses_specialises_et_se_rejoue(
    base_v4, smtp, db_session, async_session
):
    user, principal, specialise = await _groupe_avec_capacites(
        db_session, async_session
    )
    org_a = principal.organization_id
    cle = await _cle(db_session, org_a, user.id)
    entetes = {"X-API-Key": cle}
    async with _client() as client:
        # Sans base du client rattachée : la route le dit, rien n'est écrit.
        sans = await client.put(
            f"{ROUTE}/rattachement",
            json={"workflow_ids": [principal.id]},
            headers=entetes,
        )
        assert sans.status_code == 409
        await db_session.upsert_configuration(
            org_a, OrganizationConfigurationKey.BASE_CLIENT.value, {"nom_base": base_v4}
        )
        # Avant : personne n'est rattaché.
        avant = (await client.get(ROUTE, headers=entetes)).json()
        assert [a["rattache"] for a in avant["agents"]] == [False, False] and avant[
            "groupes"
        ][0]["rattache"] is False
        # Rattacher le principal : le groupe entier.
        reponse = await client.put(
            f"{ROUTE}/rattachement",
            json={"workflow_ids": [principal.id]},
            headers=entetes,
        )
        assert reponse.status_code == 200, reponse.text
        corps = reponse.json()
        assert sorted(corps["rattaches"]) == sorted(
            [principal.id, specialise.id]
        ) and corps["agents"] == [principal.id, specialise.id]
        apres = (await client.get(ROUTE, headers=entetes)).json()
        assert (
            all(a["rattache"] for a in apres["agents"])
            and apres["groupes"][0]["rattache"] is True
        )
        # Rejoué : rien de plus à rattacher.
        rejeu = (
            await client.put(
                f"{ROUTE}/rattachement",
                json={"workflow_ids": [principal.id]},
                headers=entetes,
            )
        ).json()
        assert rejeu["rattaches"] == [] and rejeu["detaches"] == []
        # Un agent inconnu : refusé en bloc, rien n'a changé.
        inconnu = await client.put(
            f"{ROUTE}/rattachement",
            json={"workflow_ids": [specialise.id, 999_999_999]},
            headers=entetes,
        )
        assert inconnu.status_code == 404
        # Détacher le principal : le groupe entier.
        retrait = (
            await client.put(
                f"{ROUTE}/rattachement",
                json={"workflow_ids": [principal.id], "rattache": False},
                headers=entetes,
            )
        ).json()
        assert (
            sorted(retrait["detaches"]) == sorted([principal.id, specialise.id])
            and retrait["rattaches"] == []
        )
        final = (await client.get(ROUTE, headers=entetes)).json()
        assert [a["rattache"] for a in final["agents"]] == [False, False]
    connexion = await schema.connecter(base_v4)
    try:
        assert (
            await connexion.fetchval(
                "SELECT count(*) FROM mark.agent WHERE rattache_le IS NOT NULL"
            )
            == 0
        )
        # Les deux agents sont connus de la base (le portail les y lit), avec leur nom.
        assert await connexion.fetchval("SELECT count(*) FROM mark.agent") == 2
    finally:
        await connexion.close()


def test_l_auteur_du_portail_est_nettoye_et_prefixe():
    assert auteur_du_portail("Camille Dupont") == "portail : Camille Dupont"
    assert auteur_du_portail("portail : Camille Dupont") == "portail : Camille Dupont"
    assert (
        auteur_du_portail("  Portail :   Camille\tDupont\n")
        == "portail : Camille Dupont"
    )
    assert (
        auteur_du_portail("Camille\x00\x1b[31m Dupont")
        == "portail : Camille[31m Dupont"
    )  # contrôles retirés
    assert auteur_du_portail("x" * 500) == "portail : " + "x" * 120
    assert (
        auteur_du_portail("") is None
        and auteur_du_portail(None) is None
        and auteur_du_portail("portail :") is None
    )


async def test_l_auteur_reel_du_portail_est_au_journal_pour_une_cle_jamais_pour_une_session(
    base_v4, smtp, db_session, async_session, test_client_factory
):
    from api.services.etablissements import copie as module_copie

    user, principal, _specialise = await _groupe_avec_capacites(
        db_session, async_session
    )
    org_a = principal.organization_id
    cle = await _cle(db_session, org_a, user.id)
    await db_session.upsert_configuration(
        org_a, OrganizationConfigurationKey.BASE_CLIENT.value, {"nom_base": base_v4}
    )

    async def auteurs():
        c = await schema.connecter(base_v4)
        try:
            return [
                r["auteur"]
                for r in await c.fetch(
                    "SELECT auteur FROM mark.journal_modif WHERE table_nom = 'site' ORDER BY id"
                )
            ]
        finally:
            await c.close()

    with patch.object(module_copie, "_redis", AsyncMock(return_value=_RedisFactice())):
        async with _client() as client:
            r = await client.put(
                "/api/v1/organizations/etablissements",
                json={"etablissements": [{"id": "fiche-a", "nom": "Fiche A"}]},
                headers={"X-API-Key": cle, "X-Mark-Auteur": "Camille Dupont"},
            )
            assert r.status_code == 200, r.text
            r = await client.put(
                "/api/v1/organizations/etablissements",
                json={"etablissements": [{"id": "fiche-a", "nom": "Fiche A bis"}]},
                headers={"X-API-Key": cle},
            )
            assert r.status_code == 200, r.text
        # Une session de l'écran (pas de clé) : l'en-tête est ignoré.
        async with test_client_factory(user) as client:
            r = await client.put(
                "/api/v1/organizations/etablissements",
                json={"etablissements": [{"id": "fiche-a", "nom": "Fiche A ter"}]},
                headers={"X-Mark-Auteur": "Usurpateur"},
            )
            assert r.status_code == 200, r.text
    ecrits = await auteurs()
    # Revue du 16/10 : le nom donné par le portail, suivi du compte de la clé qui a écrit.
    assert ecrits[0].startswith("portail : Camille Dupont (dograh:") and ecrits[0].endswith(")")
    assert (
        ecrits[1].startswith("dograh:") and "portail" not in ecrits[1]
    )  # la clé sans en-tête : le compte de la clé
    assert ecrits[2].startswith("dograh:") and "Usurpateur" not in ecrits[2]


async def test_le_point_d_entree_de_controle_des_horaires_dit_valide_ou_la_raison(
    db_session, async_session
):
    user, principal, _specialise = await _groupe_avec_capacites(
        db_session, async_session
    )
    cle = await _cle(db_session, principal.organization_id, user.id)
    async with _client() as client:
        chemin = "/api/v1/organizations/etablissements/controle-horaires"
        semaine = "\n".join(
            f"{jour} : 10:00-18:30"
            for jour in (
                "lundi",
                "mardi",
                "mercredi",
                "jeudi",
                "vendredi",
                "samedi",
                "dimanche",
            )
        )
        bon = (
            await client.post(
                chemin, json={"texte": semaine}, headers={"X-API-Key": cle}
            )
        ).json()
        assert bon == {"valide": True, "raison": None}
        mauvais = (
            await client.post(
                chemin,
                json={"texte": "lundi : n'importe quoi"},
                headers={"X-API-Key": cle},
            )
        ).json()
        assert mauvais["valide"] is False and mauvais["raison"]
        # La même fonction que l'écran : le même refus pour le même texte.
        from api.services.pipecat.etat_ouverture import (
            HorairesInvalides,
            vers_expression_osm,
        )

        with pytest.raises(HorairesInvalides) as erreur:
            vers_expression_osm("lundi : n'importe quoi")
        assert mauvais["raison"] == str(erreur.value)


# --------------------------------------------------------------------------- #
# 4. Mettre à niveau toutes les bases (D3)
# --------------------------------------------------------------------------- #


async def test_toutes_les_bases_montent_un_echec_n_arrete_pas_les_autres_jamais_deux_fois(
    base_essai,
):
    import asyncpg as pg

    from api.services.base_client.mise_a_niveau import mettre_a_niveau_toutes_les_bases
    from api.tests.mark.test_base_portail import _base_en_version_14

    anciennes = [f"{base_essai}_x", f"{base_essai}_y"]
    for nom in anciennes:
        await _base_en_version_14(nom)
    try:
        resultats = await mettre_a_niveau_toutes_les_bases(
            [
                (1, anciennes[0]),
                (2, f"{base_essai}_absente"),
                (3, anciennes[1]),
                (4, anciennes[0]),
            ]
        )
        par_org = {r.organisation_id: r for r in resultats}
        # Deux bases à jour, une base absente en échec (dite, sans adresse), la même base nommée deux fois signalée.
        assert (
            par_org[1].reussie
            and par_org[1].avant == 14
            and par_org[1].apres == schema.version_attendue()
            and par_org[1].appliquees == list(range(15, schema.version_attendue() + 1))
        )
        assert par_org[3].reussie and par_org[3].appliquees == list(
            range(15, schema.version_attendue() + 1)
        )
        assert not par_org[2].reussie and "does not exist" in par_org[2].erreur
        assert not par_org[4].reussie and "aussi rattachée" in par_org[4].erreur
        assert _serveur().split("@")[-1] not in " ".join(
            r.ligne() for r in resultats
        )  # jamais l'adresse du serveur
        # Rejouée : rien n'est rejoué.
        rejeu = await mettre_a_niveau_toutes_les_bases(
            [(1, anciennes[0]), (3, anciennes[1])]
        )
        assert [(r.appliquees, r.apres) for r in rejeu] == [
            ([], schema.version_attendue()),
            ([], schema.version_attendue()),
        ]
        # Le compte courant a ses droits sur ce que la 015 a créé.
        connexion = await schema.connecter(anciennes[0])
        try:
            assert (
                await connexion.fetchval("SELECT count(*) FROM mark.appel_motif") == 0
            )
        finally:
            await connexion.close()
    finally:
        maintenance = await pg.connect(f"{_serveur()}/postgres", timeout=5)
        try:
            for nom in anciennes:
                await maintenance.execute(
                    f'DROP DATABASE IF EXISTS "{nom}" WITH (FORCE)'
                )
                for suffixe in (
                    "portail",
                    "salarie",
                    "direction",
                    "interface",
                    "ecriture",
                ):
                    await maintenance.execute(f'DROP ROLE IF EXISTS "{nom}_{suffixe}"')
        finally:
            await maintenance.close()


async def test_une_mise_a_niveau_deja_en_cours_sur_la_base_n_est_pas_doublee(
    base_prete,
):
    from api.services.base_client.mise_a_niveau import (
        CLE_VERROU,
        mettre_a_niveau_une_base,
    )

    # Une autre mise à niveau tient le verrou de la base : celle-ci s'efface, sans rien rejouer.
    autre = await schema.connecter_proprietaire(base_prete)
    try:
        assert (
            await autre.fetchval("SELECT pg_try_advisory_lock($1)", CLE_VERROU) is True
        )
        resultat = await mettre_a_niveau_une_base(1, base_prete)
        assert resultat.reussie and resultat.ignoree and resultat.appliquees == []
    finally:
        await autre.close()
    libre = await mettre_a_niveau_une_base(1, base_prete)
    assert (
        libre.reussie
        and libre.ignoree is None
        and libre.appliquees == []
        and libre.apres == libre.avant
    )


# --------------------------------------------------------------------------- #
# 5. Toutes les routes que le portail appelle : refusées sans clé, cloisonnées par organisation (C7)
# --------------------------------------------------------------------------- #

ROUTES_DU_PORTAIL = [
    ("GET", "/api/v1/organizations/etablissements", None),
    ("PUT", "/api/v1/organizations/etablissements", {"etablissements": []}),
    (
        "POST",
        "/api/v1/organizations/etablissements/copier",
        {"source": "a", "id": "b", "nom": "B"},
    ),
    ("POST", "/api/v1/organizations/etablissements/reprise", {"ecrire": False}),
    ("POST", "/api/v1/organizations/etablissements/agent", {"workflow_id": 1}),
    (
        "POST",
        "/api/v1/organizations/etablissements/controle-horaires",
        {"texte": "lundi : 10:00-18:30"},
    ),
    ("GET", "/api/v1/organizations/equipe", None),
    ("PUT", "/api/v1/organizations/equipe", {"personnes": [], "sujets": []}),
    ("GET", "/api/v1/organizations/planificateur", None),
    ("PUT", "/api/v1/organizations/planificateur", {}),
    ("GET", "/api/v1/organizations/agents-servis", None),
    ("PUT", "/api/v1/organizations/agents-servis/rattachement", {"workflow_ids": [1]}),
]


@pytest.mark.parametrize("methode, chemin, corps", ROUTES_DU_PORTAIL)
async def test_chaque_route_du_portail_refuse_sans_cle_et_avec_une_fausse_cle(
    methode, chemin, corps
):
    async with _client() as client:
        for entetes in (
            {},
            {"X-API-Key": "dgr_fausse_cle_0123456789"},
            {"X-API-Key": ""},
        ):
            reponse = await client.request(methode, chemin, json=corps, headers=entetes)
            assert reponse.status_code == 401, (
                methode,
                chemin,
                entetes,
                reponse.status_code,
                reponse.text,
            )


async def test_la_cle_d_une_organisation_ne_lit_ni_n_ecrit_chez_une_autre(
    base_v4, smtp, db_session, async_session
):
    from api.services.etablissements import copie as module_copie

    user_a, principal, _specialise = await _groupe_avec_capacites(
        db_session, async_session
    )
    autre = await _organisation(async_session, db_session)
    cle_a = await _cle(db_session, principal.organization_id, user_a.id)
    cle_b = await _cle(db_session, autre.organisation.id, autre.utilisateur.id)
    await db_session.upsert_configuration(
        principal.organization_id,
        OrganizationConfigurationKey.BASE_CLIENT.value,
        {"nom_base": base_v4},
    )
    with patch.object(module_copie, "_redis", AsyncMock(return_value=_RedisFactice())):
        async with _client() as client:
            ecrit = await client.put(
                "/api/v1/organizations/etablissements",
                json={"etablissements": [{"id": "fiche-a", "nom": "Fiche A"}]},
                headers={"X-API-Key": cle_a},
            )
            assert ecrit.status_code == 200, ecrit.text
            # A relit sa fiche ; la clé de B ne la voit pas, et son enregistrement ne touche pas celle de A.
            chez_a = (
                await client.get(
                    "/api/v1/organizations/etablissements", headers={"X-API-Key": cle_a}
                )
            ).json()
            chez_b = (
                await client.get(
                    "/api/v1/organizations/etablissements", headers={"X-API-Key": cle_b}
                )
            ).json()
            assert [e["id"] for e in chez_a["etablissements"]] == [
                "fiche-a"
            ] and chez_b["etablissements"] == []
            ecrit_b = await client.put(
                "/api/v1/organizations/etablissements",
                json={"etablissements": [{"id": "fiche-b", "nom": "Fiche B"}]},
                headers={"X-API-Key": cle_b},
            )
            assert ecrit_b.status_code == 200, ecrit_b.text
            apres = (
                await client.get(
                    "/api/v1/organizations/etablissements", headers={"X-API-Key": cle_a}
                )
            ).json()
            assert [e["id"] for e in apres["etablissements"]] == ["fiche-a"]
            # Copier une fiche d'une autre organisation : introuvable (404 ou refus), jamais une copie.
            copie = await client.post(
                "/api/v1/organizations/etablissements/copier",
                json={"source": "fiche-a", "id": "copie-b", "nom": "Copie"},
                headers={"X-API-Key": cle_b},
            )
            assert copie.status_code in (404, 422), copie.text
            # Les agents d'une autre organisation : pas lus, pas rattachés (404).
            lecture = await client.post(
                "/api/v1/organizations/etablissements/agent",
                json={"workflow_id": principal.id},
                headers={"X-API-Key": cle_b},
            )
            assert lecture.status_code == 404
