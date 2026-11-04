"""[.mark] Partie 3, lot 14 (SE-19, J-1 à J-3) : Intégrations à la maquette.

| Test | Ce qu'il prouve |
|---|---|
| descriptions | chaque connecteur du catalogue a sa description en français et en anglais, rendue par la route du catalogue |
| dernier usage | le détail d'une connexion lit ``last_fetched_at`` et ``updated_at`` de Nango (champs de sa doc officielle) et rien d'autre |
| essai MCP | « Tester la connexion » d'un serveur ENREGISTRÉ garde son état et sa date ; une mise à jour de l'outil ne les efface pas |
| cloisonnement | tester le serveur d'une autre organisation : 404, rien n'est écrit |
| autre catégorie | un outil qui n'est pas un serveur MCP est refusé (422) |
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.services.integrations.connectors import nango
from api.services.integrations.connectors.catalogue import connecteurs
from api.services.integrations.connectors.descriptions import DESCRIPTIONS, description_de
from api.services.outils_mark import essai as essai_mark
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")

SERVEUR = {
    "schema_version": 1,
    "type": "mcp",
    "config": {"transport": "streamable_http", "url": "https://mcp.example.test/mcp", "discovered_tools": []},
}


def test_chaque_connecteur_du_catalogue_a_sa_description_en_deux_langues():
    for c in connecteurs():
        fr, en = description_de(c.nom)
        assert fr and en, f"{c.nom} n'a pas de description"
    assert set(DESCRIPTIONS) == {c.nom for c in connecteurs()}, "une description ne vise aucun connecteur"


async def test_la_route_du_catalogue_rend_les_descriptions(db_session):
    org = await creer_organisation(db_session, "desc-cat")
    _, jeton = await creer_compte(db_session, "desc-cat@example.com", role="Administrateur", organisations=[org])
    async with client_http() as c:
        r = await c.get("/api/v1/connecteurs/catalogue", headers=entetes(jeton, org))
    assert r.status_code == 200
    par_nom = {x["nom"]: x for x in r.json()}
    assert par_nom["hubspot"]["description"] and par_nom["hubspot"]["description_en"]


async def test_le_detail_d_une_connexion_lit_le_dernier_usage_et_la_verification():
    connexion = nango.Connexion(connection_id="cx-a", integration="hubspot", provider="hubspot", creee_le=None)
    corps = {
        "credentials": {"type": "OAUTH2", "access_token": "jamais-affiche"},
        "updated_at": "2026-11-03T10:00:00Z",
        "last_fetched_at": "2026-11-04T08:30:00Z",
    }
    reponse = SimpleNamespace(status_code=200, json=lambda: corps)
    with patch.object(nango, "_requete", new=AsyncMock(return_value=reponse)):
        detail = await nango.detail_de(connexion)
    assert detail.mode_acces == "OAUTH2"
    assert detail.mis_a_jour_le == "2026-11-03T10:00:00Z"
    assert detail.dernier_usage_le == "2026-11-04T08:30:00Z"
    assert "jamais-affiche" not in repr(detail)
    sans_usage = SimpleNamespace(status_code=200, json=lambda: {"credentials": {"type": "API_KEY"}})
    with patch.object(nango, "_requete", new=AsyncMock(return_value=sans_usage)):
        assert (await nango.detail_de(connexion)).dernier_usage_le is None


def test_le_test_de_connexion_est_une_cle_a_part_conservee_par_les_mises_a_jour():
    definition = essai_mark.noter_le_test_de_connexion(SERVEUR, True)
    assert definition["config"]["dernier_test_connexion"]["joignable"] is True
    assert "dernier_essai" not in definition["config"], "tester une connexion ne valide jamais un outil"
    nouvelle = {"schema_version": 1, "type": "mcp", "config": {"url": "https://autre.example.test/mcp"}}
    gardee = essai_mark.conserver_les_champs_du_serveur(definition, nouvelle)
    assert gardee["config"]["dernier_test_connexion"] == definition["config"]["dernier_test_connexion"]


async def test_tester_un_serveur_enregistre_garde_l_etat_et_la_date(db_session):
    org = await creer_organisation(db_session, "mcp-etat")
    user, jeton = await creer_compte(db_session, "mcp-etat@example.com", role="Administrateur", organisations=[org])
    outil = await db_session.create_tool(organization_id=org, user_id=user.id, name="Stock", definition=SERVEUR, category="mcp", description="x")
    corps = {"url": "https://mcp.example.test/mcp", "outil_uuid": outil.tool_uuid}
    async with client_http() as c:
        with patch("api.services.outils_mark.mcp.tester_la_connexion", new=AsyncMock(return_value={"ok": False, "outils": [], "erreur": "x"})):
            ko = await c.post("/api/v1/tools/mcp/tester", headers=entetes(jeton, org), json=corps)
        relu = await db_session.get_tool_by_uuid(outil.tool_uuid, org)
        premier = relu.definition["config"]["dernier_test_connexion"]
        with patch("api.services.outils_mark.mcp.tester_la_connexion", new=AsyncMock(return_value={"ok": True, "outils": [], "erreur": None})):
            ok = await c.post("/api/v1/tools/mcp/tester", headers=entetes(jeton, org), json=corps)
        # une mise à jour de l'outil par l'écran ne perd pas l'état
        await c.put(
            f"/api/v1/tools/{outil.tool_uuid}",
            headers=entetes(jeton, org),
            json={"name": "Stock", "definition": {"schema_version": 1, "type": "mcp", "config": {"transport": "streamable_http", "url": "https://mcp.example.test/mcp", "discovered_tools": []}}},
        )
    assert ko.status_code == 200 and ok.status_code == 200
    assert premier["joignable"] is False
    final = (await db_session.get_tool_by_uuid(outil.tool_uuid, org)).definition["config"]["dernier_test_connexion"]
    assert final["joignable"] is True and final["le"] >= premier["le"]


async def test_tester_sans_serveur_enregistre_n_ecrit_rien_et_une_autre_organisation_est_refusee(db_session):
    org_a = await creer_organisation(db_session, "mcp-a")
    org_b = await creer_organisation(db_session, "mcp-b")
    user_b, _ = await creer_compte(db_session, "mcp-b@example.com", role="Administrateur", organisations=[org_b])
    _, jeton_a = await creer_compte(db_session, "mcp-a@example.com", role="Administrateur", organisations=[org_a])
    chez_b = await db_session.create_tool(organization_id=org_b, user_id=user_b.id, name="B", definition=SERVEUR, category="mcp", description="x")
    http = await db_session.create_tool(
        organization_id=org_a,
        user_id=(await creer_compte(db_session, "mcp-a2@example.com", organisations=[org_a]))[0].id,
        name="H",
        definition={"schema_version": 1, "type": "http_api", "config": {"method": "GET", "url": "https://x.example.test"}},
        category="http_api",
        description="x",
    )
    async with client_http() as c:
        with patch("api.services.outils_mark.mcp.tester_la_connexion", new=AsyncMock(return_value={"ok": True, "outils": []})):
            autre = await c.post("/api/v1/tools/mcp/tester", headers=entetes(jeton_a, org_a), json={"url": "https://mcp.example.test/mcp", "outil_uuid": chez_b.tool_uuid})
            pas_mcp = await c.post("/api/v1/tools/mcp/tester", headers=entetes(jeton_a, org_a), json={"url": "https://mcp.example.test/mcp", "outil_uuid": http.tool_uuid})
    assert autre.status_code == 404
    assert pas_mcp.status_code == 422
    assert "dernier_test_connexion" not in (await db_session.get_tool_by_uuid(chez_b.tool_uuid, org_b)).definition["config"]
