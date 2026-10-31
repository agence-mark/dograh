"""[.mark] Builder, revue R2 : la clé du cerveau du builder ne part par aucun outil.

| Test | Ce qu'il prouve |
|---|---|
| marque | seul un identifiant marqué est reconnu |
| liste HTTP | ``GET /credentials`` ne la propose pas |
| liste MCP | ``list_credentials`` ne la propose pas |
| outil HTTP | ``execute_http_tool`` la refuse : aucune requête ne part, aucun en-tête d'autorisation |
| création d'outil | ``validate_tool_references`` la refuse (403) |
| récupération avant l'appel | ``execute_pre_call_fetch`` ne l'applique pas |
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.services.builder.cerveau.marque import MARQUE_CLE_DU_CERVEAU, est_la_cle_du_cerveau

CLE = SimpleNamespace(
    credential_uuid="cle-cerveau", name="builder-cerveau", description="", credential_type="bearer_token",
    credential_data={"token": "SECRET-A-NE-JAMAIS-ENVOYER", MARQUE_CLE_DU_CERVEAU: True}, created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
)
ORDINAIRE = SimpleNamespace(
    credential_uuid="ordinaire", name="agenda", description="", credential_type="bearer_token",
    credential_data={"token": "ordinaire"}, created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
)


def test_seul_un_identifiant_marque_est_la_cle_du_cerveau():
    assert est_la_cle_du_cerveau(CLE) and not est_la_cle_du_cerveau(ORDINAIRE)
    assert not est_la_cle_du_cerveau(SimpleNamespace(credential_data=None)) and not est_la_cle_du_cerveau(None)
    assert not est_la_cle_du_cerveau(SimpleNamespace(credential_data={MARQUE_CLE_DU_CERVEAU: "oui"}))


async def test_la_liste_http_des_identifiants_ne_propose_pas_la_cle():
    from api.routes import credentials

    with patch.object(credentials.db_client, "get_credentials_for_organization", AsyncMock(return_value=[CLE, ORDINAIRE])):
        liste = await credentials.list_credentials(SimpleNamespace(selected_organization_id=1))
    assert [c.uuid for c in liste] == ["ordinaire"]


async def test_la_liste_mcp_des_identifiants_ne_propose_pas_la_cle():
    from api.mcp_server.tools import catalog

    with patch.object(catalog, "authenticate_mcp_request", AsyncMock(return_value=SimpleNamespace(selected_organization_id=1))), patch.object(
        catalog.db_client, "get_credentials_for_organization", AsyncMock(return_value=[CLE, ORDINAIRE])
    ):
        liste = await catalog.list_credentials()
    assert [c["credential_uuid"] for c in liste] == ["ordinaire"]


def _outil(uuid):
    return SimpleNamespace(
        tool_uuid="t", name="Essai", description="", category="http_api",
        definition={"schema_version": 1, "type": "http_api", "config": {"method": "GET", "url": "https://agenda.example.test/x", "credential_uuid": uuid}},
    )


async def test_un_outil_http_ne_peut_pas_envoyer_la_cle_et_aucune_requete_ne_part():
    from api.services.workflow.tools import custom_tool

    for uuid, identifiant, attendu_envoi in (("cle-cerveau", CLE, False), ("ordinaire", ORDINAIRE, True)):
        with patch.object(custom_tool.db_client, "get_credential_by_uuid", AsyncMock(return_value=identifiant)), patch(
            f"{custom_tool.__name__}.httpx.AsyncClient"
        ) as client:
            session = AsyncMock()
            reponse = SimpleNamespace(status_code=200, text="{}", json=lambda: {})
            session.request.return_value = reponse
            client.return_value.__aenter__.return_value = session
            resultat = await custom_tool.execute_http_tool(_outil(uuid), {}, organization_id=1)
        if attendu_envoi:
            assert session.request.call_count == 1 and resultat["status"] == "success"
        else:
            assert session.request.call_count == 0 and resultat["status"] == "error"
            assert "SECRET" not in str(resultat) and "reserved" in resultat["error"]


async def test_creer_un_outil_qui_nomme_la_cle_est_refuse():
    from api.services import tool_management

    definition = {"type": "http_api", "config": {"method": "GET", "url": "https://x.example.test", "credential_uuid": "cle-cerveau"}}
    with patch.object(tool_management.db_client, "get_credential_by_uuid", AsyncMock(return_value=CLE)):
        with pytest.raises(tool_management.ToolManagementError) as e:
            await tool_management.validate_tool_references(definition, organization_id=1)
    assert e.value.status_code == 403
    with patch.object(tool_management.db_client, "get_credential_by_uuid", AsyncMock(return_value=ORDINAIRE)):
        await tool_management.validate_tool_references(definition, organization_id=1)  # un identifiant ordinaire passe


async def test_la_recuperation_avant_l_appel_n_applique_pas_la_cle():
    from api.services.pipecat import pre_call_fetch

    envoyes = []

    class _Client:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None, **k):
            envoyes.append(headers)
            return SimpleNamespace(status_code=200, json=lambda: {}, text="{}", raise_for_status=lambda: None)

    with patch.object(pre_call_fetch.db_client, "get_credential_by_uuid", AsyncMock(return_value=CLE)), patch.object(
        pre_call_fetch.httpx, "AsyncClient", _Client
    ):
        try:
            await pre_call_fetch.execute_pre_call_fetch(
                url="https://x.example.test/y", credential_uuid="cle-cerveau", call_context_vars={}, workflow_id=1, organization_id=1
            )
        except Exception:  # noqa: BLE001 -- seul l'en-tête compte
            pass
    assert all("SECRET" not in str(h) and "Authorization" not in (h or {}) for h in envoyes)


# --- suite de R2 : webhook, transfert, enregistrement d'un nœud webhook -----------------------------------------------


async def test_l_envoi_d_un_webhook_n_applique_pas_la_cle():
    from api.tasks import webhook_delivery

    livraison = SimpleNamespace(credential_uuid="cle-cerveau", organization_id=1, webhook_name="w", id=1, custom_headers=None, delivery_uuid="d", workflow_run_id=1)
    for identifiant, attendu in ((CLE, False), (ORDINAIRE, True)):
        with patch.object(webhook_delivery.db_client, "get_credential_by_uuid", AsyncMock(return_value=identifiant)):
            entetes = await webhook_delivery._build_headers(livraison, 1)
        assert ("Authorization" in entetes) is attendu
        assert "SECRET" not in str(entetes)


async def test_le_resolveur_de_transfert_refuse_la_cle():
    from api.services.workflow.tools import transfer_resolver as tr

    with patch.object(tr.db_client, "get_credential_by_uuid", AsyncMock(return_value=CLE)), patch.object(
        tr, "validate_user_configured_service_url", lambda *a, **k: None
    ):
        with pytest.raises(tr.TransferResolutionError) as e:
            await tr._execute_http_resolver(
                resolver={"url": "https://x.example.test", "credential_uuid": "cle-cerveau"}, resolved_arguments={}, organization_id=1, resolution_id="r"
            )
    assert e.value.reason == "credential_reserved"


async def test_un_noeud_webhook_qui_nomme_la_cle_est_refuse_a_l_enregistrement():
    from api.services.builder.cerveau import refus_webhook

    def graphe(uuid):
        return {"nodes": [{"id": "w1", "type": "webhook", "data": {"credential_uuid": uuid}}]}

    with patch.object(refus_webhook.db_client, "get_credential_by_uuid", AsyncMock(return_value=CLE)):
        erreurs = await refus_webhook.erreurs_cle_reservee_des_webhooks(graphe("cle-cerveau"), 1)
    assert len(erreurs) == 1 and erreurs[0]["id"] == "w1" and "SECRET" not in str(erreurs)
    with patch.object(refus_webhook.db_client, "get_credential_by_uuid", AsyncMock(return_value=ORDINAIRE)):
        assert await refus_webhook.erreurs_cle_reservee_des_webhooks(graphe("ordinaire"), 1) == []
