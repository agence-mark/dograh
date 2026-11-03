"""[.mark] Builder partie 2, U3 sexies points 5 à 7 : statistiques par outil, serveurs MCP, identifiants.

| Test | Ce qu'il prouve |
|---|---|
| statistiques | exécutions, réussite, durée médiane et dernières exécutions égales au décompte des appels ; un appel sans fin est un échec |
| pagination | les dernières exécutions sont paginées par 25 côté serveur |
| agents | les agents et étapes qui utilisent l'outil sont lus dans leur dernière version |
| cloisonnement | les appels d'une autre organisation ne comptent jamais |
| MCP SSE et HTTP | les deux transports se joignent chacun sur un vrai serveur de test, avec leurs en-têtes |
| MCP désactivé | un outil désactivé n'est jamais proposé au modèle ni appelable ; confirmer exige l'accord de l'appelant |
| tester la connexion | découvre les outils d'un serveur, rend une erreur claire sinon, refuse l'identifiant d'une autre organisation |
| identifiants | « utilisé par » calculé ; remplacement d'une valeur sans la renvoyer ; autre organisation : 404 |
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import uvicorn
from fastmcp import FastMCP

from api.services.outils_mark import mcp as mcp_mark
from api.services.outils_mark import statistiques
from api.services.workflow.mcp_tool_session import McpToolSession, discover_mcp_tools
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)
from api.tests.support.mcp_mock_server import running_mcp_server

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")

HTTP = {
    "schema_version": 1,
    "type": "http_api",
    "config": {"method": "GET", "url": "https://agenda.example.test/rdv"},
}


async def _monde(db, suffixe: str):
    org = await creer_organisation(db, f"stat-{suffixe}")
    user, jeton = await creer_compte(db, f"stat-{suffixe}@example.com", role="Administrateur", organisations=[org])
    return org, user, jeton


def _debut(i, nom, instant):
    return {"type": "rtf-function-call-start", "timestamp": instant, "node_name": "Accueil", "payload": {"function_name": nom, "tool_call_id": f"c{i}", "arguments": {}}}


def _fin(i, instant, resultat):
    return {"type": "rtf-function-call-end", "timestamp": instant, "payload": {"tool_call_id": f"c{i}", "result": resultat}}


def _horodatage(secondes: float) -> str:
    return (datetime(2026, 11, 1, 10, 0, 0, tzinfo=UTC) + timedelta(seconds=secondes)).isoformat()


async def _run(db, org, user, agent, evenements):
    return await db.create_workflow_run(
        name="appel", workflow_id=agent.id, mode="twilio", user_id=user.id, organization_id=org, logs={"realtime_feedback_events": evenements}
    )


async def _outil(db, org, user, nom="Chercher RDV", definition=None):
    return await db.create_tool(
        organization_id=org, user_id=user.id, name=nom, definition=definition or HTTP, category="http_api", description="x"
    )


async def test_les_statistiques_sont_egales_au_decompte_des_appels(db_session):
    org, user, jeton = await _monde(db_session, "calcul")
    outil = await _outil(db_session, org, user)
    agent = await db_session.create_workflow(
        name="Accueil", workflow_definition={"nodes": [{"id": "1", "data": {"name": "Accueil", "tool_uuids": [outil.tool_uuid]}}], "edges": []}, user_id=user.id, organization_id=org
    )
    # Appel 1 : 2 exécutions, une réussie (1 s), une en échec (3 s). Appel 2 : une réussie (2 s), une sans fin.
    # Un autre outil (autre nom) ne compte pas.
    await _run(db_session, org, user, agent, [
        _debut(1, "chercher_rdv", _horodatage(0)), _fin(1, _horodatage(1), {"status": "success", "data": {}}),
        _debut(2, "chercher_rdv", _horodatage(5)), _fin(2, _horodatage(8), {"status": "error", "error": "panne"}),
        _debut(3, "autre_outil", _horodatage(9)), _fin(3, _horodatage(10), {"status": "success"}),
    ])
    await _run(db_session, org, user, agent, [
        _debut(1, "chercher_rdv", _horodatage(0)), _fin(1, _horodatage(2), '{"status": "success"}'),
        _debut(2, "chercher_rdv", _horodatage(4)),
    ])
    async with client_http() as c:
        s = (await c.get(f"/api/v1/tools/{outil.tool_uuid}/statistiques", headers=entetes(jeton, org))).json()
        resume = (await c.get("/api/v1/tools/statistiques", headers=entetes(jeton, org))).json()
    assert (s["executions"], s["reussies"], s["echecs"], s["reussite"]) == (4, 2, 2, 50)
    assert s["duree_mediane_ms"] == 2000  # 1 s, 3 s, 2 s : la médiane est 2 s (l'appel sans fin n'a pas de durée)
    assert s["jours"] == 30 and s["total_executions"] == 4 and len(s["dernieres_executions"]) == 4
    assert s["agents"] == [{"agent_id": agent.id, "agent": "Accueil", "etapes": ["Accueil"]}]
    assert resume[outil.tool_uuid]["executions"] == 4 and resume[outil.tool_uuid]["nb_agents"] == 1


async def test_les_dernieres_executions_sont_paginees_par_25(db_session):
    org, user, jeton = await _monde(db_session, "pages")
    outil = await _outil(db_session, org, user)
    agent = await db_session.create_workflow(name="A", workflow_definition={}, user_id=user.id, organization_id=org)
    evenements = []
    for i in range(30):
        evenements += [_debut(i, "chercher_rdv", _horodatage(i * 2)), _fin(i, _horodatage(i * 2 + 1), {"status": "success"})]
    await _run(db_session, org, user, agent, evenements)
    async with client_http() as c:
        p0 = (await c.get(f"/api/v1/tools/{outil.tool_uuid}/statistiques?page=0", headers=entetes(jeton, org))).json()
        p1 = (await c.get(f"/api/v1/tools/{outil.tool_uuid}/statistiques?page=1", headers=entetes(jeton, org))).json()
    assert p0["executions"] == 30 and len(p0["dernieres_executions"]) == 25 and len(p1["dernieres_executions"]) == 5


async def test_les_appels_d_une_autre_organisation_ne_comptent_pas(db_session):
    org_a, user_a, jeton_a = await _monde(db_session, "iso-a")
    org_b, user_b, _ = await _monde(db_session, "iso-b")
    outil = await _outil(db_session, org_a, user_a)
    agent_b = await db_session.create_workflow(name="B", workflow_definition={}, user_id=user_b.id, organization_id=org_b)
    await _run(db_session, org_b, user_b, agent_b, [_debut(1, "chercher_rdv", _horodatage(0)), _fin(1, _horodatage(1), {"status": "success"})])
    async with client_http() as c:
        s = (await c.get(f"/api/v1/tools/{outil.tool_uuid}/statistiques", headers=entetes(jeton_a, org_a))).json()
    assert s["executions"] == 0 and s["reussite"] is None and s["duree_mediane_ms"] is None


def test_les_outils_d_un_serveur_mcp_se_reconnaissent_a_leur_prefixe():
    serveur = SimpleNamespace(name="Mon Serveur", tool_uuid="abcdef123456", category="mcp")
    assert statistiques.reconnait(serveur, "mcp__mon_serveur__chercher")
    assert not statistiques.reconnait(serveur, "mcp__autre__chercher")


# ---- Serveurs MCP ------------------------------------------------------------------------------------------------------


def _port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.asynccontextmanager
async def serveur_sse(exige: dict[str, str] | None = None):
    """Un vrai serveur FastMCP en SSE sur un port libre (fichier de test : le support partagé ne sait que le HTTP)."""
    mcp = FastMCP("sse-test")

    @mcp.tool()
    def echo(text: str) -> str:
        """Echo."""
        return f"echo:{text}"

    @mcp.tool()
    def effacer(cible: str) -> str:
        """Efface."""
        return f"efface:{cible}"

    app = mcp.http_app(transport="sse")
    if exige:
        interne = app

        async def gardee(scope, receive, send):
            if scope["type"] == "http":
                recus = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
                if any(recus.get(k.lower()) != v for k, v in exige.items()):
                    await send({"type": "http.response.start", "status": 401, "headers": []})
                    await send({"type": "http.response.body", "body": b"no"})
                    return
            await interne(scope, receive, send)

        app = gardee
    port = _port()
    serveur = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    fil = threading.Thread(target=serveur.run, daemon=True)
    fil.start()
    url = f"http://127.0.0.1:{port}/sse"
    for _ in range(50):
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", url, timeout=0.5, headers=exige or {}):
                    break
        except Exception:
            await asyncio.sleep(0.1)
    try:
        yield url
    finally:
        serveur.should_exit = True
        fil.join(timeout=5)


async def _session(url, transport, **options):
    session = McpToolSession(
        tool_uuid="u-mcp", tool_name="Serveur", url=url, credential=None, tools_filter=[],
        timeout_secs=10, sse_read_timeout_secs=20, transport=transport, **options,
    )
    await session.start()
    return session


async def test_le_transport_http_se_joint_avec_ses_en_tetes():
    async with running_mcp_server(required_headers={"X-Zone": "eu"}) as url:
        sans = await _session(url, "streamable_http")
        avec = await _session(url, "streamable_http", extra_headers={"X-Zone": "eu"})
        try:
            assert sans.available is False  # sans l'en-tête libre : refusé
            assert avec.available is True
            assert await avec.call("mcp__serveur__echo", {"text": "hi"}) == "echo:hi"
        finally:
            await avec.close()


async def test_le_transport_sse_se_joint_avec_ses_en_tetes():
    async with serveur_sse(exige={"X-Zone": "eu"}) as url:
        sans = await _session(url, "sse")
        avec = await _session(url, "sse", extra_headers={"X-Zone": "eu"})
        try:
            assert sans.available is False
            assert avec.available is True
            assert await avec.call("mcp__serveur__echo", {"text": "yo"}) == "echo:yo"
        finally:
            await avec.close()
        decouverts = await discover_mcp_tools(
            url=url, credential=None, timeout_secs=10, sse_read_timeout_secs=20, transport="sse", extra_headers={"X-Zone": "eu"}
        )
    assert sorted(d["name"] for d in decouverts) == ["echo", "effacer"]


async def test_un_outil_desactive_n_est_jamais_propose_ni_appelable_et_confirmer_exige_l_accord():
    async with serveur_sse() as url:
        session = await _session(url, "sse", reglages_outils={"effacer": "desactive", "echo": "confirmer"})
        try:
            noms = [s.name for s in session.function_schemas()]
            assert noms == ["mcp__serveur__echo"]  # « effacer » n'est jamais proposé au modèle
            schema = session.function_schemas()[0]
            assert "accord_appelant" in schema.properties and "accord_appelant" in schema.required
            assert session.demande_un_accord("mcp__serveur__echo")
            with pytest.raises(RuntimeError):
                await session.call("mcp__serveur__effacer", {"cible": "x"})  # ni appelable par un nom forcé
            # L'accord n'est jamais transmis au serveur.
            assert await session.call("mcp__serveur__echo", {"text": "ok", "accord_appelant": True}) == "echo:ok"
        finally:
            await session.close()


def test_le_desactive_rejoint_le_filtre_des_outils():
    cfg = {"reglages_outils": {"effacer": "desactive", "payer": "confirmer"}, "tools_filter": []}
    connus = {"discovered_tools": [{"name": "chercher"}, {"name": "effacer"}, {"name": "payer"}]}
    assert mcp_mark.filtre_effectif(cfg, connus) == ["chercher", "payer"]
    assert mcp_mark.filtre_effectif({**cfg, "tools_filter": ["effacer", "payer"]}, connus) == ["payer"]
    assert mcp_mark.filtre_effectif({"reglages_outils": {}, "tools_filter": ["a"]}, connus) == ["a"]


async def test_tester_la_connexion_decouvre_les_outils_et_dit_l_erreur(db_session):
    org, user, jeton = await _monde(db_session, "tester")
    async with serveur_sse() as url, client_http() as c:
        ok = await c.post("/api/v1/tools/mcp/tester", headers=entetes(jeton, org), json={"url": url, "transport": "sse", "timeout_secs": 5, "sse_read_timeout_secs": 10})
        ko = await c.post("/api/v1/tools/mcp/tester", headers=entetes(jeton, org), json={"url": "http://127.0.0.1:9/sse", "transport": "sse", "timeout_secs": 1, "sse_read_timeout_secs": 1})
        mauvaise = await c.post("/api/v1/tools/mcp/tester", headers=entetes(jeton, org), json={"url": "ftp://x"})
    assert ok.json()["ok"] is True and sorted(o["name"] for o in ok.json()["outils"]) == ["echo", "effacer"]
    assert ko.json()["ok"] is False and ko.json()["erreur"]
    assert mauvaise.status_code == 422


async def test_tester_refuse_l_identifiant_d_une_autre_organisation(db_session):
    org_a, _, jeton_a = await _monde(db_session, "tmcp-a")
    org_b, _, jeton_b = await _monde(db_session, "tmcp-b")
    async with client_http() as c:
        cle_b = (await c.post("/api/v1/credentials/", headers=entetes(jeton_b, org_b), json={"name": "B", "credential_type": "bearer_token", "credential_data": {"token": "t"}})).json()["uuid"]
        r = await c.post("/api/v1/tools/mcp/tester", headers=entetes(jeton_a, org_a), json={"url": "https://mcp.example.test/mcp", "credential_uuid": cle_b})
    assert r.status_code == 404


async def test_les_outils_decouverts_apparaissent_dans_outils_marques_mcp(db_session):
    org, user, jeton = await _monde(db_session, "decouverts")
    definition = {
        "schema_version": 1,
        "type": "mcp",
        "config": {"url": "https://mcp.example.test/mcp", "transport": "sse", "reglages_outils": {"effacer": "desactive"}, "discovered_tools": [{"name": "chercher", "description": "Cherche"}, {"name": "effacer", "description": "Efface"}]},
    }
    await db_session.create_tool(organization_id=org, user_id=user.id, name="Mon Serveur", definition=definition, category="mcp", description="x")
    async with client_http() as c:
        liste = (await c.get("/api/v1/tools/mcp/decouverts", headers=entetes(jeton, org))).json()
    assert [(o["nom"], o["reglage"], o["fonction"]) for o in liste] == [
        ("chercher", "autorise", "mcp__mon_serveur__chercher"),
        ("effacer", "desactive", "mcp__mon_serveur__effacer"),
    ]


# ---- Identifiants -------------------------------------------------------------------------------------------------------


async def test_un_identifiant_dit_qui_l_utilise_et_se_remplace_sans_jamais_s_afficher(db_session):
    org, user, jeton = await _monde(db_session, "ident")
    async with client_http() as c:
        cle = (await c.post("/api/v1/credentials/", headers=entetes(jeton, org), json={"name": "Agenda", "credential_type": "api_key", "credential_data": {"header_name": "X-Key", "api_key": "ancienne-valeur"}})).json()["uuid"]
        libre = (await c.post("/api/v1/credentials/", headers=entetes(jeton, org), json={"name": "Libre", "credential_type": "bearer_token", "credential_data": {"token": "t"}})).json()["uuid"]
        definition = {**HTTP, "config": {**HTTP["config"], "credential_uuid": cle}}
        await c.post("/api/v1/tools/", headers=entetes(jeton, org), json={"name": "Lire agenda", "definition": definition})
        usage = (await c.get("/api/v1/credentials/utilisation", headers=entetes(jeton, org))).json()
        remplace = await c.put(f"/api/v1/credentials/{cle}/valeur", headers=entetes(jeton, org), json={"valeur": "nouvelle-valeur-secrete"})
        relu = await c.get(f"/api/v1/credentials/{cle}", headers=entetes(jeton, org))
    assert usage[cle] == [{"tool_uuid": usage[cle][0]["tool_uuid"], "nom": "Lire agenda", "categorie": "http_api"}]
    assert libre not in usage
    assert remplace.status_code == 200 and remplace.json() == {"uuid": cle, "remplacee": True}
    assert "nouvelle-valeur-secrete" not in remplace.text + relu.text
    stocke = await db_session.get_credential_by_uuid(cle, org)
    # Seule la valeur secrète change : le nom d'en-tête reste.
    assert stocke.credential_data == {"header_name": "X-Key", "api_key": "nouvelle-valeur-secrete"}


async def test_le_remplacement_refuse_le_vide_et_une_autre_organisation(db_session):
    org_a, _, jeton_a = await _monde(db_session, "rep-a")
    org_b, _, jeton_b = await _monde(db_session, "rep-b")
    async with client_http() as c:
        cle = (await c.post("/api/v1/credentials/", headers=entetes(jeton_a, org_a), json={"name": "A", "credential_type": "bearer_token", "credential_data": {"token": "t"}})).json()["uuid"]
        vide = await c.put(f"/api/v1/credentials/{cle}/valeur", headers=entetes(jeton_a, org_a), json={"valeur": "   "})
        autre = await c.put(f"/api/v1/credentials/{cle}/valeur", headers=entetes(jeton_b, org_b), json={"valeur": "vol"})
        usage_b = (await c.get("/api/v1/credentials/utilisation", headers=entetes(jeton_b, org_b))).json()
    assert vide.status_code == 422 and autre.status_code == 404 and usage_b == {}
    assert (await db_session.get_credential_by_uuid(cle, org_a)).credential_data == {"token": "t"}
