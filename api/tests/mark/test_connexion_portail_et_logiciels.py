"""[.mark] Lot F6 du chantier cloture-code-avant-migration : la connexion du portail à la base du client et les
logiciels connectés, par la vraie route et la vraie authentification (une clé d'API de l'organisation).

Règle du 22/10 : aucun rôle dans le fork. « Réservée au propriétaire » veut dire : la route se connecte à la base
avec le compte PROPRIÉTAIRE (seul à pouvoir appeler ``mark.donner_connexion_portail``, ``REVOKE ... FROM PUBLIC`` de la
015), pour l'organisation de la clé, jamais pour une autre.

| Test | Ce qu'il prouve |
|---|---|
| connexion du portail | la route rend le compte et un mot de passe qui OUVRE vraiment la base, une seule fois ; rappelée, l'ancien mot de passe cesse de marcher ; le mot de passe n'est ni dans `journal_modif`, ni dans aucune ligne d'aucune table, ni dans les journaux de l'api ; sans clé : 401 ; autre organisation sans base : 409 et le compte de A intact |
| connexion en panne | une base qui refuse : 503 sans le texte de l'erreur, aucun mot de passe dans les journaux |
| logiciels connectés | la liste porte le mode d'accès, les types d'erreur, la date de la dernière erreur (seulement avec une erreur), « utilisé par » calculé depuis les outils ; aucun jeton dans la réponse ; la liste d'une organisation ne montre pas l'autre |
| suppression | `DELETE` appelle Nango avec l'identifiant de LA connexion de l'organisation et la clé d'intégration ; celle de l'autre organisation reste ; logiciel non connecté ou connecté chez l'autre seulement : 404 sans appel de suppression ; sans clé : 401 ; Nango en panne : 503 |
"""

from __future__ import annotations

import json
from unittest.mock import patch

import asyncpg
import httpx
import pytest

from api.db.bases_clients import connexion as schema
from api.services.integrations.connectors import nango
from api.services.integrations.connectors.catalogue import connecteur
from api.tests.mark.test_agents_servis import (  # noqa: F401  (fixtures)
    _client,
    _cle,
    _journaux,
    _organisation,
    base_v4,
    smtp,
)
from api.tests.mark.test_base_client import _serveur, base_essai  # noqa: F401
from api.tests.mark.test_ecritures_par_element import _installer

CHEMIN_PORTAIL = "/api/v1/organizations/base-client/connexion-portail"


async def _ouvre(base: str, role: str, mot_de_passe: str) -> bool:
    """Le compte ouvre-t-il vraiment la base ? (le test se connecte pour de bon)"""
    from urllib.parse import urlsplit

    hote = urlsplit(_serveur()).netloc.rsplit("@", 1)[-1]
    try:
        c = await asyncpg.connect(
            f"postgresql://{role}:{mot_de_passe}@{hote}/{base}", timeout=5
        )
    except (asyncpg.InvalidPasswordError, asyncpg.InvalidAuthorizationSpecificationError):
        return False
    await c.close()
    return True


async def _tout_le_contenu(base: str) -> str:
    """Toutes les lignes de toutes les tables de la base, en texte (lues par le propriétaire)."""
    c = await schema.connecter_proprietaire(base)
    try:
        morceaux = []
        for table in await c.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'mark'"):
            for ligne in await c.fetch(
                f"SELECT row_to_json(t)::text AS ligne FROM mark.{table['tablename']} t"
            ):
                morceaux.append(ligne["ligne"])
        return "\n".join(morceaux)
    finally:
        await c.close()


async def test_la_connexion_du_portail_s_ouvre_une_fois_se_renouvelle_et_ne_laisse_aucune_trace(
    base_v4, smtp, db_session, async_session
):
    _user, _org, entetes = await _installer(db_session, async_session, base_v4)
    autre = await _organisation(async_session, db_session)
    cle_b = await _cle(db_session, autre.organisation.id, autre.utilisateur.id)
    with _journaux() as journaux:
        async with _client() as client:
            for en_tetes in ({}, {"X-API-Key": "dgr_fausse_cle_0123456789"}):
                assert (await client.post(CHEMIN_PORTAIL, headers=en_tetes)).status_code == 401
            premiere = await client.post(CHEMIN_PORTAIL, headers=entetes)
            assert premiere.status_code == 200, premiere.text
            compte = premiere.json()
            assert compte["base"] == base_v4 and compte["role"] == f"{base_v4}_portail_c"
            assert len(compte["mot_de_passe"]) >= 32
            # Revue du chantier : la réponse qui porte le mot de passe n'est mise en cache nulle part.
            assert premiere.headers["cache-control"] == "no-store"
            assert premiere.headers["pragma"] == "no-cache"
            # Le mot de passe ouvre vraiment la base, et lit via le groupe du portail
            # (la base n'a reçu que son condensé SCRAM : la connexion prouve qu'il est juste).
            assert await _ouvre(base_v4, compte["role"], compte["mot_de_passe"])
            # Renouvelé : l'ancien cesse de marcher, le nouveau marche.
            seconde = await client.post(CHEMIN_PORTAIL, headers=entetes)
            assert seconde.status_code == 200, seconde.text
            nouveau = seconde.json()["mot_de_passe"]
            assert nouveau != compte["mot_de_passe"]
            assert not await _ouvre(base_v4, compte["role"], compte["mot_de_passe"])
            assert await _ouvre(base_v4, compte["role"], nouveau)
            # Une autre organisation, sans base : refusée, et le compte de A n'a pas bougé.
            refus = await client.post(CHEMIN_PORTAIL, headers={"X-API-Key": cle_b})
            assert refus.status_code == 409, refus.text
            assert await _ouvre(base_v4, compte["role"], nouveau)
    # Aucun des deux mots de passe : ni dans la base (journal compris), ni dans les journaux de l'api.
    contenu = await _tout_le_contenu(base_v4)
    texte_des_journaux = "\n".join(journaux)
    for mot_de_passe in (compte["mot_de_passe"], nouveau):
        assert mot_de_passe not in contenu
        assert mot_de_passe not in texte_des_journaux
    assert compte["role"] in texte_des_journaux  # seul le nom du compte est journalisé


async def test_une_base_qui_refuse_rend_503_sans_le_texte_de_l_erreur(
    base_v4, smtp, db_session, async_session
):
    _user, _org, entetes = await _installer(db_session, async_session, base_v4)
    secret_vu: list[str] = []
    original = asyncpg.Connection.fetchval

    async def _echec(self, requete, *args, **kwargs):
        if "donner_connexion_portail" in requete:
            # Comme une base dont l'erreur cite la requête (donc le mot de passe).
            secret_vu.append(args[0])
            raise asyncpg.PostgresError(f"ALTER ROLE ... PASSWORD '{args[0]}'")
        return await original(self, requete, *args, **kwargs)

    with _journaux() as journaux, patch.object(asyncpg.Connection, "fetchval", _echec):
        async with _client() as client:
            r = await client.post(CHEMIN_PORTAIL, headers=entetes)
    assert r.status_code == 503, r.text
    assert len(secret_vu) == 1 and len(secret_vu[0]) >= 32
    tout = r.text + "\n".join(journaux)
    assert secret_vu[0] not in tout
    assert "PASSWORD" not in tout and "ALTER ROLE" not in tout


# --------------------------------------------------------------------------- #
# Les logiciels connectés
# --------------------------------------------------------------------------- #

JETON_SECRET = "jeton-d-acces-qui-ne-sort-jamais-31"


class FauxNangoF6:
    """Les connexions par étiquette, leur détail (avec un jeton) et la suppression ; ce qui a été supprimé."""

    def __init__(self, org_a: int, org_b: int, integration: str):
        self.integration = integration
        self.connexions = [
            {
                "connection_id": "cx-a",
                "provider_config_key": integration,
                "provider": "google-calendar",
                "created": "2026-10-01T09:00:00Z",
                "tags": {"organization_id": str(org_a)},
                "errors": [{"type": "auth", "log_id": "l1"}],
            },
            {
                "connection_id": "cx-b",
                "provider_config_key": integration,
                "provider": "google-calendar",
                "created": "2026-10-02T09:00:00Z",
                "tags": {"organization_id": str(org_b)},
                "errors": [],
            },
            {
                "connection_id": "cx-autre-logiciel-b",
                "provider_config_key": "logiciel-de-b-seulement",
                "provider": "x",
                "created": "2026-10-03T09:00:00Z",
                "tags": {"organization_id": str(org_b)},
                "errors": [],
            },
        ]
        self.suppressions: list[tuple[str, str | None]] = []
        self.en_panne = False

    async def __call__(self, requete: httpx.Request) -> httpx.Response:
        if self.en_panne:
            raise httpx.ConnectError("down")
        chemin = requete.url.path
        if requete.method == "GET" and chemin == "/connections":
            tag = requete.url.params.get("tags[organization_id]")
            return httpx.Response(
                200,
                json={
                    "connections": [
                        c for c in self.connexions if c["tags"]["organization_id"] == tag
                    ]
                },
            )
        if requete.method == "GET" and chemin.startswith("/connection/"):
            identifiant = chemin.rsplit("/", 1)[-1]
            c = next((c for c in self.connexions if c["connection_id"] == identifiant), None)
            if c is None:
                return httpx.Response(404)
            return httpx.Response(
                200,
                json={
                    "connection_id": identifiant,
                    "updated_at": "2026-10-20T08:30:00Z",
                    "errors": c["errors"],
                    "credentials": {"type": "OAUTH2", "access_token": JETON_SECRET},
                },
            )
        if requete.method == "DELETE" and chemin.startswith("/connection/"):
            identifiant = chemin.rsplit("/", 1)[-1]
            self.suppressions.append(
                (identifiant, requete.url.params.get("provider_config_key"))
            )
            self.connexions = [c for c in self.connexions if c["connection_id"] != identifiant]
            return httpx.Response(200, json={"success": True})
        return httpx.Response(404)


@pytest.fixture
def nango_f6(monkeypatch):
    holder = {}

    def installer(org_a: int, org_b: int):
        integration = connecteur("google_agenda").integration
        faux = FauxNangoF6(org_a, org_b, integration)
        monkeypatch.setenv(nango.VARIABLE_URL, "http://nango.local")
        monkeypatch.setenv(nango.VARIABLE_CLE, "cle-secrete-nango-0123")
        monkeypatch.setattr(
            nango,
            "nouveau_client",
            lambda **o: httpx.AsyncClient(transport=httpx.MockTransport(faux), **o),
        )
        holder["faux"] = faux
        return faux

    return installer


async def test_les_logiciels_connectes_disent_leur_mode_leur_erreur_et_qui_les_utilise(
    base_v4, smtp, db_session, async_session, nango_f6
):
    user, org, entetes = await _installer(db_session, async_session, base_v4)
    autre = await _organisation(async_session, db_session)
    faux = nango_f6(org, autre.organisation.id)
    integration = faux.integration
    # Un outil de l'organisation qui appelle ce logiciel, un autre outil qui n'en est pas un.
    await db_session.create_tool(
        org,
        user.id,
        "Chercher un créneau",
        {
            "schema_version": 1,
            "type": "integration",
            "config": {"connecteur": "google_agenda", "action": "find_free_slots"},
        },
        category="integration",
    )
    async with _client() as client:
        r = await client.get("/api/v1/connecteurs/connexions", headers=entetes)
    assert r.status_code == 200, r.text
    corps = r.json()
    # Jamais un jeton, ni la clé de Nango, dans ce qui sort.
    assert JETON_SECRET not in r.text and "cle-secrete-nango-0123" not in r.text
    assert [c["connection_id"] for c in corps["connexions"]] == ["cx-a"]
    c = corps["connexions"][0]
    assert c["integration"] == integration
    assert c["mode_acces"] == "OAUTH2"
    assert c["types_erreurs"] == ["auth"] and c["erreurs"] == 1
    assert c["mis_a_jour_le"] == "2026-10-20T08:30:00Z"
    assert c["derniere_erreur_le"] == "2026-10-20T08:30:00Z"
    assert c["utilise_par"] == [
        {"tool_uuid": c["utilise_par"][0]["tool_uuid"], "nom": "Chercher un créneau"}
    ]
    # Une connexion sans erreur n'a pas de date d'erreur : celle de l'autre organisation, vue de chez elle.
    cle_b = await _cle(db_session, autre.organisation.id, autre.utilisateur.id)
    async with _client() as client:
        r = await client.get("/api/v1/connecteurs/connexions", headers={"X-API-Key": cle_b})
    ids_b = {c["connection_id"]: c for c in r.json()["connexions"]}
    assert set(ids_b) == {"cx-b", "cx-autre-logiciel-b"}
    assert ids_b["cx-b"]["derniere_erreur_le"] is None
    assert ids_b["cx-b"]["utilise_par"] == []  # l'outil de A n'est pas à B


async def test_supprimer_un_logiciel_appelle_nango_avec_la_connexion_de_l_organisation_seulement(
    base_v4, smtp, db_session, async_session, nango_f6
):
    _user, org, entetes = await _installer(db_session, async_session, base_v4)
    autre = await _organisation(async_session, db_session)
    faux = nango_f6(org, autre.organisation.id)
    integration = faux.integration
    chemin = f"/api/v1/connecteurs/connexions/{integration}"
    async with _client() as client:
        # Sans clé : refusé, rien de supprimé.
        assert (await client.delete(chemin)).status_code == 401
        assert faux.suppressions == []
        # Un logiciel que seule l'AUTRE organisation a connecté : 404, aucune suppression n'est envoyée.
        r = await client.delete(
            "/api/v1/connecteurs/connexions/logiciel-de-b-seulement", headers=entetes
        )
        assert r.status_code == 404, r.text
        assert faux.suppressions == []
        # La sienne : supprimée avec LE bon identifiant et la clé d'intégration.
        r = await client.delete(chemin, headers=entetes)
        assert r.status_code == 200 and r.json() == {"supprimee": True, "integration": integration}
        assert faux.suppressions == [("cx-a", integration)]
        # Celle de l'autre organisation est toujours là ; la suivante de A est « absente ».
        assert {c["connection_id"] for c in faux.connexions} == {"cx-b", "cx-autre-logiciel-b"}
        assert (await client.delete(chemin, headers=entetes)).status_code == 404
        assert faux.suppressions == [("cx-a", integration)]


async def test_supprimer_un_logiciel_quand_nango_est_en_panne_rend_503(
    base_v4, smtp, db_session, async_session, nango_f6
):
    _user, org, entetes = await _installer(db_session, async_session, base_v4)
    autre = await _organisation(async_session, db_session)
    faux = nango_f6(org, autre.organisation.id)
    faux.en_panne = True
    async with _client() as client:
        r = await client.delete(
            f"/api/v1/connecteurs/connexions/{faux.integration}", headers=entetes
        )
    assert r.status_code == 503, r.text
    assert "cle-secrete-nango-0123" not in r.text
