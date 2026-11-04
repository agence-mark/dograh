"""[.mark] Partie 3, lot 15 (SE-29, P-6) : la permission « relation.ecrire » des écritures du Hub.

| Test | Ce qu'il prouve |
|---|---|
| refus | un membre de l'équipe SANS la permission ne répond pas, ne note pas, ne témoigne pas (403 qui la nomme) ; il lit toujours |
| accord | avec la permission, la porte s'ouvre pour les trois gestes (la route répond ensuite pour son compte) |
| migration | la montée l'accorde aux rôles qui ont ``clients.ouvrir_portail`` et à eux seuls, deux fois de suite sans doublon ; la descente la retire |
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa

from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")

MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "f1a8c3d5e702_relation_ecrire.py"


async def _role(db, nom: str, permissions) -> int:
    return await db.creer_role(nom=nom, labo_ouvert=True, tous_les_clients=True, permissions=list(permissions), organisations=[])


async def _compte(db, adresse: str, role: int, org: int):
    user, jeton = await creer_compte(db, adresse, organisations=[org])
    await db.poser_membre(user.id, role)
    return jeton


GESTES = [
    ("post", "/api/v1/relation/clients/{org}/fils/1/messages", {"cote": "mark", "texte": "Bonjour"}),
    ("post", "/api/v1/relation/clients/{org}/notes", {"texte": "Une note"}),
    ("post", "/api/v1/relation/clients/{org}/temoignages", {"texte": "Un témoignage"}),
    ("delete", "/api/v1/relation/clients/{org}/notes/1", None),
    ("patch", "/api/v1/relation/clients/{org}/fils/1", {"suivi_par": None}),
]


async def test_sans_la_permission_les_ecritures_du_hub_sont_refusees_et_la_lecture_reste_ouverte(db_session):
    org = await creer_organisation(db_session, "relation-ecrire-1")
    sans = await _compte(db_session, "sans-relation@example.com", await _role(db_session, "Lecteur-relation", ["conversations.voir"]), org)
    avec = await _compte(db_session, "avec-relation@example.com", await _role(db_session, "Ecrivain-relation", ["relation.ecrire"]), org)
    async with client_http() as c:
        for methode, chemin, corps in GESTES:
            url = chemin.format(org=org)
            refuse = await getattr(c, methode)(url, headers=entetes(sans, org), **({"json": corps} if corps is not None else {}))
            assert refuse.status_code == 403, (methode, chemin)
            assert "relation.ecrire" in refuse.json()["detail"]
            ouvert = await getattr(c, methode)(url, headers=entetes(avec, org), **({"json": corps} if corps is not None else {}))
            assert ouvert.status_code != 403, (methode, chemin)  # la porte s'ouvre ; la route répond ensuite pour son compte
        lecture = await c.get(f"/api/v1/relation/clients/{org}/notes", headers=entetes(sans, org))
    assert lecture.status_code != 403


async def test_la_migration_accorde_la_permission_aux_roles_qui_ouvrent_un_portail_et_se_defait(db_session):
    spec = importlib.util.spec_from_file_location("migration_relation_ecrire", MIGRATION)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    ouvre = await _role(db_session, "Ouvre-portail-test", ["clients.ouvrir_portail", "conversations.voir"])
    autre = await _role(db_session, "Autre-test", ["conversations.voir"])

    async def permissions(role: int) -> list[str]:
        async with db_session.async_session() as session:
            lignes = await session.execute(sa.text("SELECT permission FROM mark_role_permissions WHERE role_id = :r ORDER BY permission"), {"r": role})
            return [x for (x,) in lignes.all()]

    async def jouer(sql: str):
        async with db_session.async_session() as session:
            await session.execute(sa.text(sql))
            await session.commit()

    await jouer(migration.MONTEE)
    await jouer(migration.MONTEE)  # idempotente : pas de doublon
    assert await permissions(ouvre) == ["clients.ouvrir_portail", "conversations.voir", "relation.ecrire"]
    assert await permissions(autre) == ["conversations.voir"]
    await jouer(migration.DESCENTE)
    assert await permissions(ouvre) == ["clients.ouvrir_portail", "conversations.voir"]
