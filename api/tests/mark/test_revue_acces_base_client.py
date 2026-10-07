"""[.mark] Non-regression test of the access corrections of the review (l-agent-collegue, migration 014).

The questions this file answers, on a REAL client database and real logins:

    Does the interface role read NOTHING of ``verification`` (no filter by establishment existed)?
    When an employee's access is withdrawn, is a session ALREADY OPEN cut, the reconnection
    refused, the group and the role row gone -- not only the login disabled?
    Can an employee no longer ask the database who a role is (the two helper functions)?
    Is the owner's rule « see a site » closed for an employee even by mistake?
    Is the migration replayable (a second application changes nothing)?
"""

from __future__ import annotations

import uuid
from urllib.parse import urlsplit

from types import SimpleNamespace

import asyncpg
import httpx
import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients.equipe import ecrire_equipe
from api.db.bases_clients.gestes import donner_acces, retirer_acces
from api.schemas.base_client import Equipe, Personne
from api.tests.mark.test_base_client import _serveur


MOT_DE_PASSE = "essai-revue-" + uuid.uuid4().hex[:8]


@pytest.fixture
async def base_revue(base_prete):
    connexion = await schema.connecter(base_prete)
    try:
        await connexion.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('Entreprise')")
        await connexion.execute("INSERT INTO mark.site (entreprise_id, cle, nom) SELECT id, 'site-a', 'A' FROM mark.entreprise")
        await ecrire_equipe(connexion, Equipe(personnes=[
            Personne(cle="alice", prenom="Alice", nom="Martin", etablissement="site-a", mail="alice@example.org"),
            Personne(cle="bruno", prenom="Bruno", nom="Petit", etablissement="site-a", mail="bruno@example.org"),
        ]), "test")
    finally:
        await connexion.close()
    return base_prete


_COUPEE = (asyncpg.PostgresError, asyncpg.InterfaceError, asyncpg.exceptions._base.InternalClientError,
           OSError, ConnectionError)


async def _plus_de_session(proprietaire, role) -> bool:
    """The server itself no longer lists a session of this role (a closed session, not a guess)."""
    import asyncio

    for _ in range(40):
        if await proprietaire.fetchval("SELECT count(*) FROM pg_stat_activity WHERE usename = $1", role) == 0:
            return True
        await asyncio.sleep(0.1)
    return False


async def _connexion_du_salarie(nom_base, role):
    hote = urlsplit(_serveur()).netloc.rsplit("@", 1)[-1]
    return await asyncpg.connect(f"postgresql://{role}:{MOT_DE_PASSE}@{hote}/{nom_base}", timeout=5)


async def test_le_schema_est_en_version_14_et_la_migration_se_rejoue(base_revue):
    assert schema.version_attendue() >= 14
    proprietaire = await schema.connecter_proprietaire(base_revue)
    try:
        assert await schema.version_de(proprietaire) == schema.version_attendue()
        sql = next(m for m in schema.migrations() if m.version == 14).sql
        # Played a second time (without its line in schema_version): nothing fails, nothing changes.
        await proprietaire.execute(sql.split("INSERT INTO schema_version")[0])
    finally:
        await proprietaire.close()


async def test_l_interface_ne_lit_rien_de_la_table_verification(base_revue):
    proprietaire = await schema.connecter_proprietaire(base_revue)
    role = f"{base_revue}_i_essai"
    try:
        await proprietaire.execute(f'CREATE ROLE "{role}" NOLOGIN IN ROLE "{base_revue}_interface"')
        await proprietaire.execute(f'SET ROLE "{role}"')
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await proprietaire.fetchval("SELECT count(*) FROM mark.verification")
        await proprietaire.execute("RESET ROLE")
        # The writing account of Dograh (purge, after-call) keeps its rights.
        assert await proprietaire.fetchval(
            "SELECT has_table_privilege('mark_ecriture', 'mark.verification', 'SELECT,INSERT,DELETE')")
        assert not await proprietaire.fetchval(
            "SELECT has_table_privilege('mark_interface', 'mark.verification', 'SELECT')")
    finally:
        await proprietaire.execute("RESET ROLE")
        await proprietaire.execute(f'DROP OWNED BY "{role}"')
        await proprietaire.execute(f'DROP ROLE IF EXISTS "{role}"')
        await proprietaire.close()


async def test_retirer_l_acces_coupe_la_session_ouverte_et_refuse_la_reconnexion(base_revue):
    proprietaire = await schema.connecter_proprietaire(base_revue)
    try:
        role = await donner_acces(proprietaire, "alice", MOT_DE_PASSE)
        alice = await _connexion_du_salarie(base_revue, role)
        try:
            # Before: her session reads her view.
            await alice.fetch("SELECT * FROM mark.v_mes_mentions")
            await retirer_acces(proprietaire, "alice")
            # The session that was open is closed (not just « cannot log in again »).
            with pytest.raises(_COUPEE):
                await alice.fetch("SELECT * FROM mark.v_mes_mentions")
            assert await _plus_de_session(proprietaire, role)
        finally:
            alice.terminate()
        with pytest.raises(asyncpg.InvalidAuthorizationSpecificationError):
            await _connexion_du_salarie(base_revue, role)
        # No longer in the employees' group, no row of role, no extra establishment.
        assert not await proprietaire.fetchval(
            "SELECT pg_has_role($1::name, $2::name, 'MEMBER')", role, f"{base_revue}_salarie")
        assert await proprietaire.fetchval("SELECT count(*) FROM mark.role_personne WHERE role = $1", role) == 0
        assert await proprietaire.fetchval("SELECT count(*) FROM mark.role_site WHERE role = $1", role) == 0
        # Giving the access back works again (a new login, the group again).
        role2 = await donner_acces(proprietaire, "alice", MOT_DE_PASSE)
        assert role2 == role
        retour = await _connexion_du_salarie(base_revue, role)
        try:
            await retour.fetch("SELECT * FROM mark.v_mes_mentions")
        finally:
            await retour.close()
    finally:
        await proprietaire.close()


async def test_la_desactivation_depuis_l_ecran_coupe_aussi_la_session_ouverte(base_revue):
    proprietaire = await schema.connecter_proprietaire(base_revue)
    try:
        role = await donner_acces(proprietaire, "alice", MOT_DE_PASSE)
        alice = await _connexion_du_salarie(base_revue, role)
        try:
            connexion = await schema.connecter(base_revue)
            try:
                await connexion.execute("UPDATE mark.personne SET actif = false WHERE cle = 'alice'")
            finally:
                await connexion.close()
            with pytest.raises(_COUPEE):
                await alice.fetch("SELECT * FROM mark.v_mes_mentions")
            assert await _plus_de_session(proprietaire, role)
        finally:
            alice.terminate()
    finally:
        await proprietaire.close()


async def test_un_salarie_ne_peut_plus_demander_qui_est_un_autre_role(base_revue):
    proprietaire = await schema.connecter_proprietaire(base_revue)
    try:
        role = await donner_acces(proprietaire, "alice", MOT_DE_PASSE)
        alice = await _connexion_du_salarie(base_revue, role)
        try:
            # About herself the helpers answer; about another role they say nothing (before: they told).
            assert await alice.fetchval("SELECT mark.personne_du_role($1::name)", role) is not None
            assert await proprietaire.fetchval("SELECT mark.personne_du_role($1::name)", role) is not None
            await donner_acces(proprietaire, "bruno", MOT_DE_PASSE, ["site-a"])
            autre = await proprietaire.fetchval(
                "SELECT rp.role FROM mark.role_personne rp JOIN mark.personne p ON p.id = rp.personne_id WHERE p.cle = 'bruno'")
            assert await alice.fetchval("SELECT mark.personne_du_role($1::name)", autre) is None
            assert await alice.fetch("SELECT * FROM mark.sites_du_salarie($1::name)", autre) == []
            assert await proprietaire.fetchval("SELECT mark.personne_du_role($1::name)", autre) is not None
            # Her own views still answer (they call the functions with their owner's rights).
            await alice.fetch("SELECT * FROM mark.v_mes_mentions")
            await alice.fetch("SELECT * FROM mark.v_appels_de_mon_etablissement")
            # The rule « see a site » is closed for an employee, even if a table were granted by mistake.
            assert not await proprietaire.fetchval("SELECT mark.voit_le_site(NULL, $1::name)", role)
            assert await proprietaire.fetchval("SELECT mark.voit_le_site(NULL, 'mark_ecriture')")
        finally:
            await alice.close()
    finally:
        await proprietaire.close()


async def test_une_base_anterieure_a_la_008_dit_quoi_faire_a_l_enregistrement_de_l_equipe(base_revue, monkeypatch):
    """Revue du 07/10 (g): the team saved on a database not yet upgraded used to end in an
    « Internal Server Error »; now it names the way out and saves nothing."""
    from fastapi import FastAPI

    from api.routes import base_client as route
    from api.services.auth.depends import get_user_with_selected_organization

    proprietaire = await schema.connecter_proprietaire(base_revue)
    try:
        # What a database at version 7 is: the four columns of 008 and the later versions are not there.
        for colonne in ("description", "divulguer_telephone", "divulguer_mail", "joignable_par_transfert"):
            await proprietaire.execute(f"ALTER TABLE mark.personne DROP COLUMN {colonne}")
        await proprietaire.execute("DELETE FROM mark.schema_version WHERE version >= 8")
    finally:
        await proprietaire.close()

    async def nom(_organisation):
        return base_revue

    monkeypatch.setattr(route.rattachement, "nom_de_la_base", nom)
    app = FastAPI()
    app.include_router(route.routeur_equipe)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: SimpleNamespace(
        id=1, provider_id="p", selected_organization_id=1, email="essai@example.org")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://essai") as client:
        r = await client.put("/organizations/equipe", json={"personnes": [{"cle": "alice", "prenom": "Alice"}]})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "Upgrade" in detail and "version 7" in detail and f"expected {schema.version_attendue()}" in detail
    assert "Nothing was saved" in detail


from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: E402, F401
