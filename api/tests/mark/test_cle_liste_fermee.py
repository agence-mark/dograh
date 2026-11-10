"""[.mark] Builder partie 3, sous-lot 17a : une clé d'API n'a que les permissions d'une LISTE FERMÉE (décision n° 1 de Pierre, option A).

| Test | Ce qu'il prouve |
|---|---|
| la liste | la liste fermée est dans les permissions réelles, ne contient aucun geste d'équipe, de publication ni de clé ; l'ancien complément en est dérivé |
| interdictions | une clé du client reçoit 403 sur : publier (agent, groupe), appeler (appel de test, essai), campagne (lancer, reprendre, créer), créer une clé (clé d'API, clé de service), geste d'équipe (rôle, invitation, nouveau client, réglage d'un espace), proposer / relancer / retirer une proposition de logiciel |
| tout le reste est fermé | toute permission du registre qui n'est pas dans la liste est refusée à une clé : une permission nouvelle est fermée tant qu'on ne l'ouvre pas |
| MCP | un outil MCP d'écriture (créer, enregistrer un agent, créer un outil) et une action d'écriture du builder par MCP sont refusés à une clé de client, acceptés à la clé du Labo d'un membre de l'équipe |
| ouvert à la clé | les gestes du portail passent : fils (écrire, répondre), lien d'une proposition de SON organisation (200, auteur réel dans ``autorise_par``), autoriser un compte, couper une connexion |
| cloisonnement | la clé du client B ne voit ni ne touche le fil ni la proposition du client A (404), sur chaque route ouverte à une clé |
| permission propre | la connexion du portail à la base exige ``base_client.connexion_portail`` (plus ``cles.gerer``) : un compte d'équipe avec seulement ``cles.gerer`` est refusé, avec la nouvelle il passe jusqu'à la route |
| migration | la montée accorde les deux permissions aux rôles qui ont ``cles.gerer`` et à eux seuls, deux fois sans doublon ; la descente les retire |
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa
from fastapi import HTTPException

from api.mcp_server import auth as auth_mcp
from api.services.builder.actions import registre
from api.services.builder.bibliotheque import droits
from api.services.equipe_mark import espaces, registre_routes as registre_permissions
from api.services.equipe_mark.acces import PERMISSIONS_JAMAIS_PAR_CLE
from api.services.equipe_mark.permissions import PERMISSIONS, PERMISSIONS_DE_CLE
from api.services.integrations.connectors import propositions
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)
from api.tests.mark.test_connecteurs_catalogue_f3 import base, relais  # noqa: F401  (fixtures)

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")

MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "a7c2e9d4b6f1_permissions_portail.py"


@pytest.fixture(autouse=True)
def _cache_du_labo_propre():
    espaces.reinitialiser_cache()
    yield
    espaces.reinitialiser_cache()


async def _deux_clients(db, s: str):
    a = await creer_organisation(db, f"lf-a-{s}")
    b = await creer_organisation(db, f"lf-b-{s}")
    admin, _ = await creer_compte(db, f"lf-admin-{s}@example.com", role="Administrateur", organisations=[a, b])
    _, cle_a = await db.create_api_key(a, "portail A", admin.id)
    _, cle_b = await db.create_api_key(b, "portail B", admin.id)
    return SimpleNamespace(a=a, b=b, cle_a=cle_a, cle_b=cle_b, admin=admin)


def _cle(cle: str, auteur: str | None = None) -> dict:
    h = {"X-API-Key": cle}
    if auteur:
        h["X-Mark-Auteur"] = auteur
    return h


# --------------------------------------------------------------------------- la liste


def test_la_liste_fermee_est_reelle_et_ne_contient_aucun_geste_d_equipe_de_publication_ou_de_cle():
    assert PERMISSIONS_DE_CLE <= set(PERMISSIONS)
    interdites = {
        "agents.publier", "agents.supprimer", "tests.jouer", "builder.lancer", "cles.gerer", "telephonie.gerer", "clients.creer",
        "clients.exporter_ramener", "clients.ouvrir_portail", "equipe.gerer", "roles.gerer", "atelier.regler", "donnees.exporter",
        "relation.ecrire",
    }
    assert not (PERMISSIONS_DE_CLE & interdites)
    assert PERMISSIONS_JAMAIS_PAR_CLE == set(PERMISSIONS) - PERMISSIONS_DE_CLE
    assert {"connecteurs.autoriser", "base_client.connexion_portail"} <= PERMISSIONS_DE_CLE


async def test_toute_permission_du_registre_hors_de_la_liste_est_refusee_a_une_cle():
    from api.app import app
    from fastapi.routing import APIRoute

    # Pour chaque permission hors liste, une route réelle du registre qui l'exige : la clé y reçoit 403 (route trouvée par le registre).
    par_permission: dict[str, tuple[str, str]] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/v1"):
            continue
        for methode in route.methods or ():
            trouvee = registre_permissions.decision_de(methode, route.path.removeprefix("/api/v1"))
            if trouvee and isinstance(trouvee[0], registre_permissions.Permission):
                par_permission.setdefault(trouvee[0].cle, (methode, route.path))
    hors_liste = {c for c in par_permission if c not in PERMISSIONS_DE_CLE}
    assert {"agents.publier", "tests.jouer", "cles.gerer", "builder.lancer", "clients.creer"} <= hors_liste
    # Le registre est lu ici sans base : la décision se prend avant la route, d'après la permission seule.
    from api.services.equipe_mark.acces import appliquer_acces

    for cle in sorted(hors_liste):
        methode, chemin = par_permission[cle]
        connexion = SimpleNamespace(headers={}, scope={"route": SimpleNamespace(path_format=chemin), "type": "http", "method": methode})
        utilisateur = SimpleNamespace(id=1, selected_organization_id=5)
        with (
            patch("api.services.equipe_mark.espaces.rafraichir_labo", AsyncMock()),
            patch("api.services.equipe_mark.acces.acces_de", AsyncMock(return_value=None)),
            patch("api.services.equipe_mark.acces.detacher_de_sa_session", lambda u: None),
        ):
            with pytest.raises(HTTPException) as e:
                await appliquer_acces(connexion, utilisateur, par_cle_api=True)
        assert e.value.status_code == 403, (cle, methode, chemin)


# --------------------------------------------------------------------------- les interdictions, une à une

INTERDICTIONS = [
    ("publier un agent", "post", "/api/v1/workflow/1/publish", None),
    ("publier le groupe", "post", "/api/v1/workflow/1/groupe/publier", None),
    ("appeler (appel de test)", "post", "/api/v1/telephony/initiate-call", {}),
    ("appeler (essai d'un agent)", "post", "/api/v1/workflow/1/runs", {}),
    ("campagne : lancer", "post", "/api/v1/campaign/1/start", None),
    ("campagne : reprendre", "post", "/api/v1/campaign/1/resume", None),
    ("campagne : créer", "post", "/api/v1/campaign/create", {}),
    ("créer une clé d'API", "post", "/api/v1/user/api-keys", {}),
    ("créer une clé de service", "post", "/api/v1/user/service-keys", {}),
    ("geste d'équipe : rôle", "post", "/api/v1/equipe-mark/roles", {}),
    ("geste d'équipe : invitation", "post", "/api/v1/equipe-mark/invitations", {}),
    ("créer un client", "post", "/api/v1/organizations", {}),
    ("régler un espace", "put", "/api/v1/espaces/1", {}),
    ("proposer un logiciel", "post", "/api/v1/connecteurs/propositions", {}),
    ("relancer une proposition", "post", "/api/v1/connecteurs/propositions/x/relancer", None),
    ("retirer une proposition", "delete", "/api/v1/connecteurs/propositions/x", None),
]


@pytest.mark.parametrize("libelle, methode, chemin, corps", INTERDICTIONS, ids=[i[0] for i in INTERDICTIONS])
async def test_une_cle_de_client_est_refusee_sur_chaque_interdiction(db_session, libelle, methode, chemin, corps):
    cas = await _deux_clients(db_session, "i" + str(abs(hash(libelle)) % 10_000))
    async with client_http() as c:
        r = await getattr(c, methode)(chemin, headers=_cle(cas.cle_a), **({"json": corps} if corps is not None else {}))
    assert r.status_code == 403, (libelle, r.status_code, r.text[:200])
    assert "API key" in r.json()["detail"]


# --------------------------------------------------------------------------- MCP


def _par_mcp(user):
    return patch.multiple(
        auth_mcp,
        get_http_headers=lambda include=None: {"x-api-key": "cle-de-test"},
        _handle_api_key_auth=AsyncMock(return_value=user),
    )


async def test_un_outil_mcp_d_ecriture_est_refuse_a_une_cle_de_client_et_accepte_a_celle_du_labo():
    labo = 7
    membre = lambda org: SimpleNamespace(id=3, selected_organization_id=org)  # noqa: E731
    with (
        patch.object(droits, "organisation_bibliotheque", return_value=labo),
        patch("api.services.builder.constantes.organisation_bibliotheque", return_value=labo),
        patch.object(droits.db_client, "is_user_member_of_organization", AsyncMock(return_value=True), create=True),
        patch.object(droits.db_client, "acces_du_compte", AsyncMock(return_value=SimpleNamespace(labo_ouvert=True, permissions=frozenset(PERMISSIONS))), create=True),  # SA-9 : le créateur porte tout
    ):
        with _par_mcp(membre(8)):  # clé d'un client
            with pytest.raises(HTTPException) as e:
                await auth_mcp.authenticate_mcp_write("save_workflow")
        assert e.value.status_code == 403
        with _par_mcp(membre(labo)):  # clé du Labo, créée par un membre de l'équipe
            assert (await auth_mcp.authenticate_mcp_write("save_workflow")).selected_organization_id == labo
        with _par_mcp(membre(8)):  # la lecture reste ouverte à la clé du client
            assert (await auth_mcp.authenticate_mcp_request()).selected_organization_id == 8


async def test_les_trois_outils_mcp_d_ecriture_de_l_amont_passent_par_la_garde_d_ecriture():
    import inspect

    from api.mcp_server.tools import create_workflow, save_workflow, tool_creation

    for module in (create_workflow, save_workflow, tool_creation):
        source = inspect.getsource(module)
        assert "authenticate_mcp_write(" in source, module.__name__  # clôture, lot A : l'outil se nomme, sa permission est dans ``droits_mcp``
        assert "authenticate_mcp_request(" not in source, module.__name__


async def test_une_action_d_ecriture_du_builder_par_mcp_est_refusee_a_une_cle_de_client():
    labo = 7
    action = next(a for a in registre.REGISTRE.values() if a.ecriture and a.mcp)
    lecture = next(a for a in registre.REGISTRE.values() if not a.ecriture and a.mcp)
    client = SimpleNamespace(id=3, selected_organization_id=8, par_porte_mcp=True, par_cle_api=True)
    equipe = SimpleNamespace(id=3, selected_organization_id=labo, par_porte_mcp=True, par_cle_api=True)
    with (
        patch.object(droits, "organisation_bibliotheque", return_value=labo),
        patch("api.services.builder.constantes.organisation_bibliotheque", return_value=labo),
        patch.object(droits.db_client, "is_user_member_of_organization", AsyncMock(return_value=True), create=True),
        patch.object(droits.db_client, "acces_du_compte", AsyncMock(return_value=SimpleNamespace(labo_ouvert=True, permissions=frozenset(PERMISSIONS))), create=True),  # SA-9 : le créateur porte tout
        patch("api.services.builder.portes.refus_de_la_porte", AsyncMock(return_value=None)),
    ):
        refus = await registre.executer(action.nom, {}, registre.Contexte(user=client, porte=registre.PORTE_MCP))
        assert refus["ok"] is False and refus["code"] == "cle_sans_ecriture"
        # Ni la clé du Labo, ni la lecture d'une clé de client, n'est arrêtée par cette garde.
        passee = await registre.executer(action.nom, {}, registre.Contexte(user=equipe, porte=registre.PORTE_MCP))
        assert passee.get("code") != "cle_sans_ecriture"
        lue = await registre.executer(lecture.nom, {}, registre.Contexte(user=client, porte=registre.PORTE_MCP))
        assert lue.get("code") != "cle_sans_ecriture"


# --------------------------------------------------------------------------- ouvert à la clé, cloisonné


async def test_la_cle_du_client_ecrit_a_mark_et_le_client_b_ne_voit_rien(db_session):
    cas = await _deux_clients(db_session, "f1")
    async with client_http() as c:
        cree = await c.post(
            "/api/v1/organizations/relation/fils",
            headers=_cle(cas.cle_a, "portail : Martine Leroy"),
            json={"sujet": "Une question", "texte": "Bonjour"},
        )
        assert cree.status_code == 201, cree.text
        fil = cree.json()["id"]
        chez_a = await c.get("/api/v1/organizations/relation/fils", headers=_cle(cas.cle_a))
        chez_b = await c.get("/api/v1/organizations/relation/fils", headers=_cle(cas.cle_b))
        lecture_b = await c.get(f"/api/v1/organizations/relation/fils/{fil}", headers=_cle(cas.cle_b))
        ecriture_b = await c.post(f"/api/v1/organizations/relation/fils/{fil}/messages", headers=_cle(cas.cle_b), json={"texte": "intrus"})
    assert [f["id"] for f in chez_a.json()] == [fil]
    assert chez_b.json() == []
    assert lecture_b.status_code == 404 and ecriture_b.status_code == 404


async def test_le_lien_d_une_proposition_est_accorde_a_la_cle_de_son_organisation_avec_l_auteur_reel(db_session, base, relais):  # noqa: F811
    cas = await _deux_clients(db_session, "l1")
    proposee = await propositions.proposer(
        cas.a, propositions.NouvelleProposition(connecteur="slack", compte="equipe sav"), "mark : Evan"
    )
    chemin = f"/api/v1/connecteurs/propositions/{proposee.identifiant}/lien"
    async with client_http() as c:
        ok = await c.post(
            chemin,
            headers=_cle(cas.cle_a, "portail : Martine Leroy"),
            # Un nom envoyé dans le corps ne se substitue jamais à l'auteur lu dans l'en-tête.
            json={"autorise_par": "Quelqu'un d'autre"},
        )
        autre = await c.post(chemin, headers=_cle(cas.cle_b, "portail : Intrus"))
    assert ok.status_code == 200, ok.text
    assert ok.json()["lien"] == "https://connect.test/x"
    assert relais.sessions[-1]["tags"]["autorise_par"] == "portail : Martine Leroy"
    assert relais.sessions[-1]["tags"]["organization_id"] == str(cas.a)
    assert autre.status_code == 404  # la proposition du client A n'existe pas pour la clé du client B
    assert len(relais.sessions) == 1  # et aucun lien n'a été fait pour B


async def test_la_cle_autorise_reconnecte_et_coupe_ses_propres_comptes_seulement(db_session, base, relais):  # noqa: F811
    cas = await _deux_clients(db_session, "l2")
    async with client_http() as c:
        lien = await c.post("/api/v1/connecteurs/lien", headers=_cle(cas.cle_a, "portail : Martine Leroy"), json={"connecteurs": ["slack"], "compte": "equipe sav"})
        coupe = await c.delete("/api/v1/connecteurs/connexions/slack", headers=_cle(cas.cle_a))
    assert lien.status_code == 200, lien.text
    assert relais.sessions[-1]["tags"]["autorise_par"] == "portail : Martine Leroy"
    assert coupe.status_code == 404  # atteinte (pas 403) : ce client n'a aucune connexion Slack, et rien d'un autre n'est touché


# --------------------------------------------------------------------------- permission propre à la base du client


async def test_la_connexion_du_portail_a_la_base_exige_sa_permission_propre_et_non_cles_gerer(db_session):
    org = await creer_organisation(db_session, "lf-base")
    ancien = await db_session.creer_role(nom="Cles-seulement", labo_ouvert=False, tous_les_clients=True, permissions=["cles.gerer"], organisations=[])
    nouveau = await db_session.creer_role(nom="Base-portail", labo_ouvert=False, tous_les_clients=True, permissions=["base_client.connexion_portail"], organisations=[])
    refuse, j_refuse = await creer_compte(db_session, "lf-cles@example.com", organisations=[org])
    await db_session.poser_membre(refuse.id, ancien)
    passe, j_passe = await creer_compte(db_session, "lf-base@example.com", organisations=[org])
    await db_session.poser_membre(passe.id, nouveau)
    chemin = "/api/v1/organizations/base-client/connexion-portail"
    async with client_http() as c:
        non = await c.post(chemin, headers=entetes(j_refuse, org))
        oui = await c.post(chemin, headers=entetes(j_passe, org))
    assert non.status_code == 403 and "base_client.connexion_portail" in non.json()["detail"]
    assert oui.status_code != 403  # la décision est prise ; la route répond ensuite pour son compte (ici : pas de base rattachée)


# --------------------------------------------------------------------------- migration


def _charger_migration():
    spec = importlib.util.spec_from_file_location("migration_permissions_portail", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_la_migration_accorde_les_deux_permissions_aux_roles_qui_gerent_les_cles_et_se_defait(db_session):
    avec = await db_session.creer_role(nom="Mig-avec-cles", labo_ouvert=False, tous_les_clients=True, permissions=["cles.gerer"], organisations=[])
    sans = await db_session.creer_role(nom="Mig-sans-cles", labo_ouvert=False, tous_les_clients=True, permissions=["conversations.voir"], organisations=[])
    migration = _charger_migration()

    async def permissions(role: int) -> set[str]:
        async with db_session.async_session() as session:
            lignes = await session.execute(sa.text("SELECT permission FROM mark_role_permissions WHERE role_id = :r"), {"r": role})
            return {p for (p,) in lignes}

    async def jouer(instructions):
        async with db_session.async_session() as session:
            for instruction in instructions:
                await session.execute(sa.text(instruction))
            await session.commit()

    class _Op:
        def __init__(self):
            self.instructions: list[str] = []

        def execute(self, texte):
            self.instructions.append(texte)

    for _ in range(2):  # deux montées de suite : aucun doublon
        op = _Op()
        with patch.object(migration, "op", op):
            migration.upgrade()
        await jouer(op.instructions)
    assert await permissions(avec) == {"cles.gerer", "connecteurs.autoriser", "base_client.connexion_portail"}
    assert await permissions(sans) == {"conversations.voir"}
    op = _Op()
    with patch.object(migration, "op", op):
        migration.downgrade()
    await jouer(op.instructions)
    assert await permissions(avec) == {"cles.gerer"}
