"""[.mark] builder-agent-vocal : le monde simulé des tests du builder (aucune base, aucun appel réel).

``FauxDb`` tient en mémoire ce que le builder lit et écrit dans ``db_client`` ; la fixture ``monde`` le branche
partout où le code du builder importe ``db_client`` et règle l'organisation .mark de la bibliothèque.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

ORG_MARK = 1
ORG_CLIENT = 7
ORG_AUTRE = 8
AGENT = 42


def graphe_depart() -> dict:
    return {
        "nodes": [
            {"id": "1", "type": "startCall", "position": {"x": 0, "y": 0}, "data": {"name": "Départ", "prompt": "p1"}},
            {"id": "2", "type": "endCall", "position": {"x": 0, "y": 100}, "data": {"name": "Fin", "prompt": "p2"}},
        ],
        "edges": [{"id": "1-2", "source": "1", "target": "2", "data": {"label": "Fini", "condition": "c"}}],
    }


def utilisateur(identifiant: int = 1, organisation: int = ORG_CLIENT):
    return SimpleNamespace(
        id=identifiant,
        provider_id=f"p{identifiant}",
        email=f"u{identifiant}@exemple.test",
        selected_organization_id=organisation,
        mark_auteur=None,
    )


class FauxDb:
    def __init__(self):
        self.configs: dict[tuple[int, str], dict] = {}
        self.membres: set[tuple[int, int]] = set()
        self.workflows: dict[int, SimpleNamespace] = {}
        self.brouillons: dict[int, SimpleNamespace] = {}
        self.credentials: dict[str, SimpleNamespace] = {}
        self.configs_utilisateur: dict[tuple[int, str], dict] = {}
        self.ecritures_de_reglages: list[dict] = []
        self._prochain = 100

    # -- organization_configurations --
    async def get_configuration(self, organization_id, key):
        valeur = self.configs.get((organization_id, key))
        return SimpleNamespace(key=key, value=valeur) if valeur is not None else None

    async def upsert_configuration(self, organization_id, key, value, last_validated_at=None):
        self.configs[(organization_id, key)] = value
        return SimpleNamespace(key=key, value=value)

    async def delete_configuration(self, organization_id, key):
        return self.configs.pop((organization_id, key), None) is not None

    async def get_all_configurations(self, organization_id):
        return [SimpleNamespace(key=k, value=v) for (o, k), v in self.configs.items() if o == organization_id]

    async def get_configurations_by_prefix(self, organization_id, prefix):
        return sorted(
            (SimpleNamespace(key=k, value=v) for (o, k), v in self.configs.items() if o == organization_id and k.startswith(prefix)),
            key=lambda ligne: ligne.key,
        )

    # -- membres --
    async def is_user_member_of_organization(self, user_id, organization_id):
        return (user_id, organization_id) in self.membres

    # -- agents --
    def ajouter_agent(self, organization_id=ORG_CLIENT, identifiant=AGENT, graphe=None, configurations=None):
        definition = SimpleNamespace(
            workflow_json=graphe or graphe_depart(), version_number=1, status="published", workflow_configurations=configurations or {}
        )
        self.workflows[identifiant] = SimpleNamespace(
            id=identifiant,
            name=f"agent-{identifiant}",
            organization_id=organization_id,
            status="active",
            released_definition=definition,
            workflow_definition=definition.workflow_json,
            workflow_configurations=configurations or {},
            current_definition_id=1,
            template_context_variables={},
            call_disposition_codes=None,
            created_at=datetime.now(UTC),
        )
        return self.workflows[identifiant]

    async def get_workflow(self, workflow_id, organization_id=None):
        w = self.workflows.get(workflow_id)
        if w is None or (organization_id is not None and w.organization_id != organization_id):
            return None
        return w

    async def get_all_workflows_for_listing(self, organization_id, status=None):
        return [
            SimpleNamespace(id=w.id, name=w.name, status=w.status, created_at=w.created_at)
            for w in self.workflows.values()
            if w.organization_id == organization_id and status in (None, w.status)
        ]

    async def get_draft_version(self, workflow_id):
        return self.brouillons.get(workflow_id)

    async def save_workflow_draft(self, workflow_id, workflow_definition=None, workflow_configurations=None, template_context_variables=None):
        ancien = self.brouillons.get(workflow_id)
        numero = (ancien.version_number if ancien else self.workflows[workflow_id].released_definition.version_number) + 1
        self.brouillons[workflow_id] = SimpleNamespace(
            workflow_json=workflow_definition or (ancien.workflow_json if ancien else None),
            version_number=numero,
            status="draft",
            workflow_configurations=workflow_configurations or {},
        )
        return self.brouillons[workflow_id]

    async def update_workflow(self, workflow_id, name, workflow_definition, template_context_variables, workflow_configurations, user_id=None, organization_id=None):
        self.ecritures_de_reglages.append({"workflow_id": workflow_id, "configurations": workflow_configurations})
        await self.save_workflow_draft(workflow_id, None, workflow_configurations)
        return self.workflows[workflow_id]

    async def create_workflow(self, name, workflow_definition, user_id, organization_id=None, workflow_configurations=None):
        self._prochain += 1
        w = self.ajouter_agent(organization_id, self._prochain, workflow_definition, workflow_configurations)
        w.name = name
        return w

    # -- coffre --
    async def get_credential_by_uuid(self, credential_uuid, organization_id, active_only=True):
        c = self.credentials.get(credential_uuid)
        return c if c is not None and c.organization_id == organization_id else None

    async def create_credential(self, organization_id, user_id, name, credential_type, credential_data, description=None):
        self._prochain += 1
        c = SimpleNamespace(credential_uuid=f"cred-{self._prochain}", organization_id=organization_id, name=name, credential_data=credential_data)
        self.credentials[c.credential_uuid] = c
        return c

    async def update_credential(self, credential_uuid, organization_id, name=None, description=None, credential_type=None, credential_data=None):
        c = self.credentials[credential_uuid]
        if credential_data is not None:
            c.credential_data = credential_data
        return c

    # -- préférences de la personne --
    async def get_user_configuration_value(self, user_id, key):
        return self.configs_utilisateur.get((user_id, key))

    async def upsert_user_configuration_value(self, user_id, key, value):
        self.configs_utilisateur[(user_id, key)] = value
        return value


MODULES_AVEC_DB = (
    "api.services.builder.stock",
    "api.services.builder.cerveau.reglages",
    "api.services.builder.bibliotheque.droits",
    "api.services.builder.brouillon",
    "api.services.builder.contexte",
    "api.services.builder.creation",
    "api.services.builder.actions._commun",
    "api.mcp_server.tools._workflow_projection",
    "api.services.modeles_reglages.service",
    "api.services.builder.reglages_agent",
    "api.services.lexique.stockage",
    "api.mcp_server.tools.workflows",
)


@pytest.fixture
def monde(monkeypatch):
    """Un monde en mémoire : une organisation .mark (1), un client (7), un agent (42) à lui."""
    import importlib

    db = FauxDb()
    for chemin in MODULES_AVEC_DB:
        monkeypatch.setattr(importlib.import_module(chemin), "db_client", db)
    monkeypatch.setenv("MARK_BIBLIOTHEQUE_ORGANISATION_ID", str(ORG_MARK))
    from api.services.groupe import groupe
    from api.services.workflow import schema_du_parcours, tool_name_validation

    monkeypatch.setattr(groupe, "recopier_dans_les_specialises", AsyncMock(return_value=[]))
    monkeypatch.setattr(schema_du_parcours, "a_l_enregistrement", AsyncMock(return_value=None))
    monkeypatch.setattr(tool_name_validation, "validate_workflow_tool_name_collisions", AsyncMock(return_value=[]))
    db.membres.add((1, ORG_MARK))  # l'utilisateur 1 est de l'équipe .mark ; l'utilisateur 2 ne l'est pas
    db.ajouter_agent()
    return db
