"""[.mark] L'export BigQuery de l'amont est NEUTRALISÉ (décision E3 d'Evan, 25/09/2026).

Remise à niveau sur l'amont `4e6cb22b` (`0d5b68fb` ajoute l'export des
événements d'appel vers BigQuery, seule destination possible). « Un gros non » :
impossible à allumer, refusé côté serveur même si une configuration enregistrée
le demande, absent de l'écran (`ui/src/app/settings/page.tsx`).

| Test | La garantie |
|---|---|
| enregistrement | la route des préférences refuse une destination BigQuery (422) |
| envoi | une configuration BigQuery déjà en base n'envoie RIEN (pas même mis en file) |
| journal | chaque refus laisse une ligne `[.mark] BigQuery export refused` |
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from loguru import logger

from api.routes import organization as route_organisation
from api.schemas.call_events import CallEventsSettings
from api.services.auth.depends import get_user_with_selected_organization
from api.services.observability.call_events import configuration, delivery

BIGQUERY = {
    "enabled": True,
    "sink_type": "bigquery",
    "config": {"table": "projet-exemple.jeu.table", "auth_mode": "application_default"},
}


@pytest.fixture
def journal():
    lignes = []
    ident = logger.add(lambda m: lignes.append(str(m)), level="WARNING")
    yield lignes
    logger.remove(ident)


def test_la_route_des_preferences_refuse_bigquery(journal):
    app = FastAPI()
    app.include_router(route_organisation.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: type(
        "U", (), {"selected_organization_id": 1, "id": 1}
    )()
    reponse = TestClient(app).put("/organizations/preferences", json={"call_events": BIGQUERY})
    assert reponse.status_code == 422, reponse.text
    assert any("[.mark] BigQuery export refused" in ligne for ligne in journal)


def test_une_configuration_bigquery_deja_en_base_n_envoie_rien(journal):
    reglages = CallEventsSettings.model_validate(BIGQUERY)
    avant = len(delivery._tasks)
    assert delivery.submit(1, reglages, (object(),), 10) is False
    assert len(delivery._tasks) == avant, "une tâche d'envoi a été créée"
    assert any("[.mark] BigQuery export refused" in ligne for ligne in journal)


def test_toute_resolution_de_la_destination_est_refusee(journal):
    with pytest.raises(ValueError):
        configuration.registration("bigquery")
    assert any("[.mark] BigQuery export refused" in ligne for ligne in journal)
