"""[.mark] Clôture, lot 0 : deux écritures relisaient un attribut APRÈS le commit, sur une session qui expire ses objets.

Le commit expire l'objet, la lecture relance une requête hors du contexte asynchrone : ``MissingGreenlet``. Sur le journal du builder,
cela refusait TOUTE écriture du builder (« Nothing was done: the journal of the builder cannot be written »). Les tests du builder
remplacent ``db_client`` et ne pouvaient pas le voir : ceux-ci passent par la vraie base de test.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete

from api.db import db_client
from api.db.models import OrganizationModel, WorkflowDefinitionModel, WorkflowModel
from api.db.models_builder import MarkBuilderJournalModel, WorkflowBranchModel


@pytest.fixture
async def organisation():
    async with db_client.async_session() as session:
        org = OrganizationModel(provider_id=f"test-apres-commit-{uuid.uuid4()}")
        session.add(org)
        await session.flush()
        identifiant = org.id
        await session.commit()
    yield identifiant
    async with db_client.async_session() as session:
        agents = WorkflowModel.__table__.c
        await session.execute(delete(MarkBuilderJournalModel).where(MarkBuilderJournalModel.organization_id == identifiant))
        await session.execute(delete(WorkflowBranchModel).where(WorkflowBranchModel.organization_id == identifiant))
        await session.execute(WorkflowModel.__table__.update().where(agents.organization_id == identifiant).values(released_definition_id=None))
        ids = (await session.execute(WorkflowModel.__table__.select().where(agents.organization_id == identifiant))).all()
        for ligne in ids:
            await session.execute(delete(WorkflowDefinitionModel).where(WorkflowDefinitionModel.workflow_id == ligne.id))
        await session.execute(delete(WorkflowModel).where(WorkflowModel.organization_id == identifiant))
        await session.execute(delete(OrganizationModel).where(OrganizationModel.id == identifiant))
        await session.commit()


async def test_le_journal_du_builder_s_ecrit_sur_une_vraie_base(organisation):
    identifiant = await db_client.ecrire_journal_builder(
        organisation, auteur="test", porte="ecran", action="tests_creer", famille="brouillon", statut="en_cours", arguments={}
    )
    assert isinstance(identifiant, int)
    assert (await db_client.lire_journal_builder(organisation, identifiant))["action"] == "tests_creer"


async def test_defaire_une_fusion_rend_le_numero_de_version(organisation):
    async with db_client.async_session() as session:
        agent = WorkflowModel(name="agent", organization_id=organisation, workflow_definition={}, workflow_configurations={})
        session.add(agent)
        await session.flush()
        version = WorkflowDefinitionModel(workflow_json={}, workflow_id=agent.id, status="published", version_number=7, is_current=True)
        session.add(version)
        await session.flush()
        agent.released_definition_id = version.id
        session.add(WorkflowBranchModel(organization_id=organisation, workflow_id=agent.id, nom="Principale", est_principale=True))
        branche = WorkflowBranchModel(organization_id=organisation, workflow_id=agent.id, nom="essai")
        session.add(branche)
        await session.flush()
        agent_id, branche_id, version_id = agent.id, branche.id, version.id
        await session.commit()

    numero = await db_client.defaire_la_fusion(
        organisation,
        agent_id,
        branche_id,
        {"version_creee": version_id, "ancienne_en_ligne": None, "ancienne_tete_principale": None, "part_de_la_principale": 100, "part_de_la_branche": 0},
    )
    assert numero == 7
