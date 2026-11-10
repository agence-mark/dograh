"""[.mark] Clôture, lot A : les méthodes de ``api/db/`` ajoutées ou changées, jouées sur la VRAIE base de test (leçon du lot 0).

Les tests qui remplacent ``db_client`` ne voient pas une lecture d'attribut après ``commit`` (``MissingGreenlet``). Ceux-ci passent par une vraie
session qui expire ses objets, puis nettoient ce qu'ils ont écrit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from api.db import db_client
from api.db.models import APIKeyModel, OrganizationModel, UserModel
from api.db.models_equipe import MarkJournalModel, MarkMembreModel, MarkReglageEquipeModel, MarkRoleModel


@pytest.fixture
async def monde():
    suffixe = uuid.uuid4().hex[:8]
    async with db_client.async_session() as session:
        org = OrganizationModel(provider_id=f"cl-reel-{suffixe}")
        user = UserModel(provider_id=f"cl-reel-u-{suffixe}", email=f"cl-reel-{suffixe}@example.com")
        session.add_all([org, user])
        await session.flush()
        ids = (org.id, user.id)
        await session.commit()
    org_id, user_id = ids
    role_id = await db_client.creer_role(
        nom=f"cl-reel-{suffixe}", labo_ouvert=False, tous_les_clients=False, permissions=["agents.modifier"], organisations=[]
    )
    yield org_id, user_id, role_id, suffixe
    async with db_client.async_session() as session:
        await session.execute(delete(APIKeyModel).where(APIKeyModel.organization_id == org_id))
        await session.execute(delete(MarkMembreModel).where(MarkMembreModel.user_id == user_id))
        await session.execute(delete(MarkRoleModel).where(MarkRoleModel.id == role_id))
        await session.execute(delete(MarkJournalModel).where(MarkJournalModel.auteur == f"reel-{suffixe}"))
        await session.execute(delete(MarkReglageEquipeModel).where(MarkReglageEquipeModel.cle == f"TEST_{suffixe}"))
        await session.execute(delete(UserModel).where(UserModel.id == user_id))
        await session.execute(delete(OrganizationModel).where(OrganizationModel.id == org_id))
        await session.commit()


async def test_cles_role_suspension_et_comptage_sur_une_vraie_base(monde):
    org, user, role, _ = monde
    cle, brut = await db_client.create_api_key(org, "reelle", user, role_id=role)
    assert cle.role_id == role and brut
    assert await db_client.count_api_keys_with_role(role) == 1
    assert (await db_client.get_api_key_by_id(org, cle.id)).role_id == role
    assert await db_client.get_api_key_by_id(org + 10_000, cle.id) is None  # filtre par organisation dans la requête
    assert await db_client.set_api_key_active(org, cle.id, False) is True
    assert await db_client.validate_api_key(brut) is None
    assert await db_client.set_api_key_active(org, cle.id, True) is True
    assert (await db_client.validate_api_key(brut)).role_id == role
    assert await db_client.set_api_key_role(org, cle.id, None) is True
    assert (await db_client.get_api_key_by_id(org, cle.id)).role_id is None
    await db_client.archive_api_key(cle.id)
    assert await db_client.set_api_key_active(org, cle.id, True) is False  # révoquée : ne se rétablit pas


async def test_acces_reglages_et_purge_du_journal_sur_une_vraie_base(monde):
    org, user, role, suffixe = monde
    assert await db_client.acces_est_actif(user) is True  # sans ligne d'équipe : jamais bloqué
    await db_client.poser_membre(user, role)
    assert await db_client.changer_acces_protege(user, False) == "ok"
    assert await db_client.acces_est_actif(user) is False
    assert await db_client.changer_acces_protege(user, True) == "ok"
    assert await db_client.acces_est_actif(user) is True
    assert await db_client.changer_acces_protege(user + 10_000, False) == "inconnu"

    cle = f"TEST_{suffixe}"
    assert await db_client.lire_reglage_equipe(cle) is None
    await db_client.poser_reglage_equipe(cle, {"fr": "a"}, user)
    await db_client.poser_reglage_equipe(cle, {"fr": "b"}, user)
    assert await db_client.lire_reglage_equipe(cle) == {"fr": "b"}

    auteur = f"reel-{suffixe}"
    await db_client.ecrire_journal(user_id=user, auteur=auteur, action="test.reel", organization_id=org, detail={"x": 1}, origine="mcp")
    async with db_client.async_session() as session:
        ligne = (await session.execute(MarkJournalModel.__table__.select().where(MarkJournalModel.auteur == auteur))).first()
        await session.execute(
            MarkJournalModel.__table__.update().where(MarkJournalModel.id == ligne.id).values(quand=datetime.now(UTC) - timedelta(days=400))
        )
        await session.commit()
    lignes, total = await db_client.lister_journal(limit=5, offset=0, organization_id=org, origine="mcp", actions=["test.reel"])
    assert total == 1 and lignes[0]["origine"] == "mcp"
    assert "test.reel" in await db_client.types_de_gestes_du_journal()
    assert await db_client.purger_journal(datetime.now(UTC) - timedelta(days=360)) >= 1
    _, apres = await db_client.lister_journal(limit=5, offset=0, organization_id=org)
    assert apres == 0
