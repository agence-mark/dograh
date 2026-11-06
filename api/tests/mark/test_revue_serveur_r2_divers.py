"""[.mark] Revue serveur, passage 1, corrections R2 : mineurs 1, 4 et 7.

| Test | Ce qu'il prouve |
|---|---|
| mineur 1 : adresse de métadonnées | ``/tools/mcp/tester`` refuse 169.254.169.254 et un lien local (422), même en mode ``oss`` |
| mineur 1 : message générique | l'échec d'une connexion ne dit pas le nom de la classe d'erreur |
| mineur 4 : un domaine au moins | un site sans domaine (création, réglage) est refusé ; un site avec domaine passe |
| mineur 7 : fin de période | la recherche dans les transcriptions borne aussi les candidats par la fin de période |
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from api.db import appels_liste
from api.services.outils_mark import mcp as mcp_mark
from api.tests.mark.equipe_commun import (  # noqa: F401
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,
)
from api.tests.mark.test_conversations_colonnes import _liste, _monde, _replique, _run

API = "/api/v1"
TESTER = f"{API}/tools/mcp/tester"


async def _admin(db, nom):
    org = await creer_organisation(db, f"r2-div-{nom}")
    _user, jeton = await creer_compte(db, f"r2-div-{nom}@example.com", role="Administrateur", organisations=[org])
    return org, jeton


@pytest.mark.usefixtures("sans_preparation_des_organisations")
async def test_mineur_1_le_test_mcp_refuse_les_adresses_de_metadonnees_meme_en_oss(db_session):
    org, jeton = await _admin(db_session, "mcp")
    async with client_http() as c:
        for url in ("http://169.254.169.254/latest/meta-data", "https://169.254.1.1/mcp", "http://[fe80::1]/mcp", "http://0.0.0.0/mcp"):
            r = await c.post(TESTER, headers=entetes(jeton, org), json={"url": url})
            assert r.status_code == 422, (url, r.text)
            assert r.json()["detail"] == "This address is not allowed"


async def test_mineur_1_l_echec_de_connexion_ne_dit_pas_la_classe_d_erreur():
    class ErreurSecrete(Exception):
        pass

    with patch.object(mcp_mark, "discover_mcp_tools", side_effect=ErreurSecrete("10.0.0.7 refusé")):
        resultat = await mcp_mark.tester_la_connexion(
            url="http://x.example/mcp", transport="sse", timeout_secs=1, sse_read_timeout_secs=1,
            credential=None, entrees_en_tetes=[], organization_id=1,
        )
    assert resultat["ok"] is False
    assert "ErreurSecrete" not in resultat["erreur"] and "10.0.0.7" not in resultat["erreur"]


@pytest.mark.usefixtures("sans_preparation_des_organisations")
async def test_mineur_4_un_site_exige_au_moins_un_domaine(db_session):
    org, jeton = await _admin(db_session, "site")
    h = entetes(jeton, org)
    async with client_http() as c:
        assert (await c.post(f"{API}/organizations/sites", headers=h, json={"nom": "Sans domaine", "allowed_domains": []})).status_code == 422
        assert (await c.post(f"{API}/organizations/sites", headers=h, json={"nom": "Vide", "allowed_domains": ["  "]})).status_code == 422
        site = await c.post(f"{API}/organizations/sites", headers=h, json={"nom": "Client", "allowed_domains": ["client.fr"]})
        assert site.status_code == 200, site.text
        site_id = site.json()["id"]
        assert (await c.put(f"{API}/organizations/sites/{site_id}", headers=h, json={"allowed_domains": []})).status_code == 422
        assert (await c.put(f"{API}/organizations/sites/{site_id}", headers=h, json={"nom": "Renommé"})).status_code == 200  # sans toucher aux domaines


async def test_mineur_7_la_recherche_borne_aussi_les_candidats_par_la_fin_de_periode(db_session, async_session):
    org, agent = await _monde(async_session, db_session, "r2-fin")
    await _run(async_session, agent, jours=10, journal=[_replique("Le devis de la période")])
    await _run(async_session, agent, jours=1, journal=[_replique("Un devis récent hors période")])
    debut = datetime.now(UTC) - timedelta(days=30)
    fin = datetime.now(UTC) - timedelta(days=5)
    # Un seul candidat lu : sans la borne de fin, c'est le run récent (hors période) qui l'occupe et la période semble vide.
    with patch.object(appels_liste, "RECHERCHE_APPELS_MAX", 1):
        runs, total = await _liste(db_session, org, recherche="devis", start_date=debut, end_date=fin)
    assert total == 1 and len(runs) == 1


# ----------------------------------------------------------------------------- mineur 6 étendu
async def test_mineur_6_le_run_se_lit_avec_l_organisation_dans_la_requete(db_session, async_session):
    org_a, agent_a = await _monde(async_session, db_session, "r2-m6-a")
    org_b, _agent_b = await _monde(async_session, db_session, "r2-m6-b")
    run = await _run(async_session, agent_a, journal=[_replique("bonjour")])
    lu, organisation = await db_session.get_workflow_run_with_context(run.id, organization_id=org_a.id)
    assert lu is not None and organisation == org_a.id
    assert await db_session.get_workflow_run_with_context(run.id, organization_id=org_b.id) == (None, None)
    # Sans organisation : la lecture système des tâches de fond, inchangée.
    assert (await db_session.get_workflow_run_with_context(run.id))[1] == org_a.id


async def test_mineur_6_les_appelants_passent_l_organisation(db_session, async_session):
    from unittest.mock import AsyncMock

    from api.services.juge import a_ameliorer
    from api.services.tests_rejouables import creation

    espion = AsyncMock(return_value=(None, None))
    with patch.object(creation.db_client, "get_workflow_run_with_context", espion):
        with pytest.raises(creation.ErreurTestRejouable):
            await creation.creer_depuis_un_run(5, 42, 0, {"type": "texte_present", "texte": "x"}, "nom", "")
    assert espion.await_args.kwargs == {"organization_id": 42}

    espion = AsyncMock(return_value=(None, None))
    with patch.object(a_ameliorer.db_client, "get_workflow_run_with_context", espion):
        try:
            await a_ameliorer.signaler(42, {"run_id": 9, "workflow_id": 1}, [], [], "claude_code")
        except Exception:  # noqa: BLE001 : seul l'appel de lecture compte ici
            pass
    assert espion.await_args.kwargs == {"organization_id": 42}
