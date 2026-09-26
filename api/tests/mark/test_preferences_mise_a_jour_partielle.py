"""[.mark] Une mise à jour partielle des préférences ne perd aucun réglage de l'organisation.

Remise à niveau sur l'amont `4e6cb22b`, relecture indépendante du 26/09/2026 (point 4).
L'amont fait des préférences une mise à jour partielle et le prouve dans
`tests/test_call_event_sinks.py::test_partial_preferences_updates_preserve_legacy_settings_and_sink`.
Ce test-là commence par enregistrer un export BigQuery, que nous refusons (décision E3) :
il est déclaré en échec attendu (`divergences_amont.py`), et sa partie qui ne touche pas
à l'export n'était plus vérifiée par personne. La voici, sans BigQuery :

- l'ancienne clé de préférences (`MODEL_CONFIGURATION_PREFERENCES`) est reprise à la
  première mise à jour, champ par champ ;
- changer un champ garde tous les autres (numéro de test, correspondance des fins d'appel) ;
- vider un champ ne vide que lui.
"""

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from api.enums import OrganizationConfigurationKey
from api.routes import organization as routes
from api.services.observability.call_events import configuration

URL = "/organizations/preferences"
ORGANISATION = 7


@pytest.fixture
async def client_preferences(monkeypatch):
    lignes = {}
    utilisateur = SimpleNamespace(selected_organization_id=ORGANISATION)

    async def get(org_id, key):
        valeur = lignes.get((org_id, key))
        return SimpleNamespace(value=valeur) if valeur is not None else None

    async def put(org_id, key, value):
        lignes[(org_id, key)] = value

    async def delete(org_id, key):
        lignes.pop((org_id, key), None)

    monkeypatch.setattr(configuration.db_client, "get_configuration", get)
    monkeypatch.setattr(configuration.db_client, "upsert_configuration", put)
    monkeypatch.setattr(configuration.db_client, "delete_configuration", delete)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.get_user] = lambda: utilisateur
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, lignes


@pytest.mark.asyncio
async def test_une_mise_a_jour_partielle_garde_les_autres_reglages(client_preferences):
    client, lignes = client_preferences
    ancienne = OrganizationConfigurationKey.MODEL_CONFIGURATION_PREFERENCES.value
    nouvelle = OrganizationConfigurationKey.ORGANIZATION_PREFERENCES.value
    origine = {
        "timezone": "Europe/Paris",
        "test_phone_number": "+33123456789",
        "external_pbx_integrations_enabled": True,
        "disposition_mapping_enabled": True,
        "disposition_mapping": {"user_hangup": "HUNGUP"},
    }
    lignes[(ORGANISATION, ancienne)] = origine

    reponse = await client.put(URL, json={"timezone": "UTC"})
    assert reponse.status_code == 200
    assert lignes[(ORGANISATION, nouvelle)] == {**origine, "timezone": "UTC"}

    reponse = await client.put(URL, json={"test_phone_number": None})
    assert reponse.status_code == 200
    assert reponse.json()["test_phone_number"] is None
    assert reponse.json()["timezone"] == "UTC"

    relu = (await client.get(URL)).json()
    assert relu["disposition_mapping"] == origine["disposition_mapping"]
    assert relu["disposition_mapping_enabled"] is True
    assert relu["external_pbx_integrations_enabled"] is True
    assert relu["call_events"]["enabled"] is False
