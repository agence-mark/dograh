"""[.mark] Clôture, lot A (décision d'Evan du 09/11) : trois interrupteurs par clé d'API pour les gestes qui coûtent ou engagent, par la porte MCP.

| Test | Ce qu'il prouve |
|---|---|
| éteints par défaut | une clé neuve (et une clé d'avant) a les trois interrupteurs éteints ; le refus dit quel réglage allumer, en français et en anglais, dans un seul format |
| allumé ne suffit pas | il faut en plus que le rôle de la clé porte la permission du geste, et que son créateur l'ait (plafond, base réelle) |
| allumé + permission | le geste passe, il est écrit au journal avec la porte ``mcp`` |
| irréversible | supprimer reste fermé à la porte MCP, tous interrupteurs allumés |
| qui allume | seul un membre qui gère les clés ; jamais un geste qu'il n'a pas lui-même ; journalisé ; la clé d'une autre organisation est introuvable |
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.services.builder.actions import registre
from api.services.builder.actions.registre import PORTE_MCP, Contexte
from api.services.equipe_mark import droits_effectifs, droits_mcp, espaces
from api.tests.mark.builder_commun import monde, utilisateur  # noqa: F401
from api.tests.mark.equipe_commun import client_http, creer_compte, creer_organisation, entetes, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_builder_familles_et_modes import FAMILLES, essais  # noqa: F401

GESTES = [
    ("essai_publication", droits_mcp.GESTE_PUBLIER, "agents.publier"),
    ("essai_appels_reels", droits_mcp.GESTE_APPELS_REELS, "agents.publier"),  # l'action d'essai prend la permission de sa famille
    ("tests_rejouer", droits_mcp.GESTE_TESTS_PAYANTS, "tests.jouer"),
]


def _cle(*interrupteurs, role=3):
    u = utilisateur(1)
    u.par_cle_api = True
    u.par_porte_mcp = True
    u.cle_api_role_id = role
    u.cle_api_mcp = frozenset(interrupteurs)
    return u


@pytest.fixture
def espions(monkeypatch, essais):  # noqa: F811
    """``tests_rejouer`` remplacé par une action d'essai qui note ses appels (les autres viennent de ``essais``)."""
    appels = {nom: [] for nom, _, _ in GESTES}

    async def fonction(contexte, parametres):
        appels["tests_rejouer"].append(1)
        return {"ok": True}

    monkeypatch.setitem(registre.REGISTRE, "tests_rejouer", dataclasses.replace(registre.REGISTRE["tests_rejouer"], fonction=fonction, parametres=registre.REGISTRE["essai_publication"].parametres))
    appels["essai_publication"] = essais["publication"]
    appels["essai_appels_reels"] = essais["appels_reels"]
    return appels


async def _jouer(nom, utilisateur_mcp, permissions):
    contexte = Contexte(user=utilisateur_mcp, workflow_id=None, porte=PORTE_MCP)
    with patch.object(droits_effectifs, "permissions_de", AsyncMock(return_value=frozenset(permissions))):
        return await registre.executer(nom, {}, contexte)


@pytest.mark.parametrize("nom, geste, permission", GESTES)
async def test_interrupteur_eteint_refus_clair_en_deux_langues_et_rien_n_est_fait(nom, geste, permission, monde, espions):  # noqa: F811
    refus = await _jouer(nom, _cle(), {permission})
    assert refus["ok"] is False and refus["code"] == "mcp_interrupteur_eteint" and refus["reglage"] == geste
    libelle_fr, libelle_en = droits_mcp.LIBELLES_DES_GESTES[geste]
    assert libelle_fr in refus["erreur_fr"] and libelle_en in refus["erreur"]
    assert set(refus) == {"ok", "code", "reglage", "erreur", "erreur_fr"}  # un seul format
    assert not espions[nom]


@pytest.mark.parametrize("nom, geste, permission", GESTES)
async def test_allume_mais_le_role_n_a_pas_la_permission_rien_n_est_fait(nom, geste, permission, monde, espions):  # noqa: F811
    refus = await _jouer(nom, _cle(geste), {"conversations.voir"})
    assert refus["ok"] is False and refus["code"] == "droits"
    assert not espions[nom]


@pytest.mark.parametrize("nom, geste, permission", GESTES)
async def test_allume_avec_la_permission_le_geste_passe_et_le_journal_garde_la_porte_mcp(nom, geste, permission, monde, espions):  # noqa: F811
    ecrites = []

    async def noter(user, action, organization_id, detail=None):
        ecrites.append((action, detail))

    with patch("api.services.equipe_mark.acces.journaliser", noter):
        resultat = await _jouer(nom, _cle(geste), {permission})
    assert resultat.get("ok") is True and len(espions[nom]) == 1
    assert ecrites and ecrites[-1][0] == f"mcp.{nom}" and ecrites[-1][1]["ok"] is True
    # un autre interrupteur n'ouvre pas ce geste
    autre = next(g for _, g, _ in GESTES if g != geste)
    assert (await _jouer(nom, _cle(autre), {permission}))["code"] == "mcp_interrupteur_eteint"


async def test_supprimer_reste_a_l_ecran_tous_interrupteurs_allumes(monde, espions):  # noqa: F811
    tous = _cle(*droits_mcp.GESTES_MCP)
    resultat = await _jouer("essai_irreversible", tous, set(droits_mcp.GESTES_MCP.values()) | {"agents.supprimer"})
    assert resultat["code"] == "porte_mcp"


async def test_la_cle_sans_role_n_a_aucun_interrupteur(monde, espions):  # noqa: F811
    u = _cle(*droits_mcp.GESTES_MCP, role=None)  # clé d'avant ou du portail : liste fermée, aucun geste
    resultat = await _jouer("essai_publication", u, {"agents.publier"})
    assert resultat["ok"] is False and resultat["code"] in {"cle_sans_ecriture", "porte_mcp"}


# ---------------------------------------------------------------------- le plafond du créateur, sur la vraie base
@pytest.fixture(autouse=False)
def _labo(db_session):
    espaces.reinitialiser_cache()
    yield
    espaces.reinitialiser_cache()


async def test_le_createur_qui_n_a_plus_la_permission_la_retire_a_la_cle_meme_interrupteur_allume(db_session, _labo, sans_preparation_des_organisations):  # noqa: F811
    db = db_session
    labo = await creer_organisation(db, "mcp-labo")
    client = await creer_organisation(db, "mcp-client")
    await espaces.definir_labo(labo, True)
    role_cle = await db.creer_role(nom="mcp-publieur", labo_ouvert=True, tous_les_clients=True, permissions=["agents.publier"], organisations=[])
    role_createur = await db.creer_role(nom="mcp-createur", labo_ouvert=True, tous_les_clients=True, permissions=["agents.publier"], organisations=[])
    createur, _ = await creer_compte(db, "mcp-createur@example.com", role="mcp-createur", organisations=[labo, client])
    cle = SimpleNamespace(id=createur.id, selected_organization_id=client, par_cle_api=True, cle_api_role_id=role_cle, cle_api_mcp=frozenset({"publier"}))
    assert "agents.publier" in await droits_effectifs.permissions_de(cle)
    await db.modifier_role(role_createur, nom="mcp-createur", labo_ouvert=True, tous_les_clients=True, permissions=["conversations.voir"], organisations=[])
    assert "agents.publier" not in await droits_effectifs.permissions_de(cle)  # plafond : le rôle de la clé le porte, pas son créateur
    refus = await registre._refus_de_la_cle_mcp(registre.REGISTRE["agent_publier"], Contexte(user=cle, workflow_id=None, porte=PORTE_MCP))
    assert refus is not None and refus["code"] == "droits"


# ---------------------------------------------------------------------- qui allume, et où
async def _monde_http(db, suffixe):
    labo = await creer_organisation(db, f"sw-labo-{suffixe}")
    client = await creer_organisation(db, f"sw-client-{suffixe}")
    await espaces.definir_labo(labo, True)
    admin, jeton = await creer_compte(db, f"sw-admin-{suffixe}@example.com", role="Administrateur", organisations=[labo, client])
    return labo, client, admin, jeton


async def test_les_interrupteurs_sont_eteints_par_defaut_et_seul_qui_a_le_droit_les_allume(db_session, _labo, sans_preparation_des_organisations):  # noqa: F811
    db = db_session
    labo, client, admin, jeton = await _monde_http(db, "qui")
    gere_les_cles = await db.creer_role(nom="sw-gere-cles", labo_ouvert=True, tous_les_clients=True, permissions=["cles.gerer"], organisations=[])
    _, jeton_gestionnaire = await creer_compte(db, "sw-gest@example.com", role="sw-gere-cles", organisations=[labo, client])
    async with client_http() as c:
        cree = (await c.post("/api/v1/user/api-keys", headers=entetes(jeton, client), json={"name": "k"})).json()
        liste = (await c.get("/api/v1/user/api-keys", headers=entetes(jeton, client))).json()
        ligne = next(k for k in liste if k["id"] == cree["id"])
        assert (ligne["mcp_publier"], ligne["mcp_tests_payants"], ligne["mcp_appels_reels"]) == (False, False, False)
        # un membre qui gère les clés mais n'a pas lui-même la permission du geste ne l'allume pas
        refus = await c.put(f"/api/v1/user/api-keys/{cree['id']}/mcp", headers=entetes(jeton_gestionnaire, client), json={"publier": True})
        assert refus.status_code == 403 and "agents.publier" in refus.json()["detail"]
        # il peut éteindre
        assert (await c.put(f"/api/v1/user/api-keys/{cree['id']}/mcp", headers=entetes(jeton_gestionnaire, client), json={"publier": False})).status_code == 200
        # un administrateur allume, c'est journalisé
        ok = await c.put(f"/api/v1/user/api-keys/{cree['id']}/mcp", headers=entetes(jeton, client), json={"publier": True, "tests_payants": True})
        assert ok.status_code == 200
        liste = (await c.get("/api/v1/user/api-keys", headers=entetes(jeton, client))).json()
        ligne = next(k for k in liste if k["id"] == cree["id"])
        assert (ligne["mcp_publier"], ligne["mcp_tests_payants"], ligne["mcp_appels_reels"]) == (True, True, False)
        journal = (await c.get("/api/v1/equipe-mark/journal?action=cle_api.interrupteurs_mcp", headers=entetes(jeton, client))).json()
        assert journal["total"] >= 2 and journal["lignes"][0]["detail"]["publier"] is True
        # une clé ne change pas les interrupteurs d'une clé
        assert (await c.put(f"/api/v1/user/api-keys/{cree['id']}/mcp", headers={"X-API-Key": cree["api_key"]}, json={"publier": True})).status_code == 403
    assert gere_les_cles


async def test_la_cle_d_une_autre_organisation_est_introuvable(db_session, _labo, sans_preparation_des_organisations):  # noqa: F811
    db = db_session
    labo, client, admin, jeton = await _monde_http(db, "autre")
    async with client_http() as c:
        dans_labo = (await c.post("/api/v1/user/api-keys", headers=entetes(jeton, labo), json={"name": "labo"})).json()
        # la clé du Labo n'est pas visible depuis l'espace d'un client
        r = await c.put(f"/api/v1/user/api-keys/{dans_labo['id']}/mcp", headers=entetes(jeton, client), json={"publier": True})
        assert r.status_code == 404
        liste = (await c.get("/api/v1/user/api-keys", headers=entetes(jeton, labo))).json()
        assert next(k for k in liste if k["id"] == dans_labo["id"])["mcp_publier"] is False
