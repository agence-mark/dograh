"""[.mark] Partie 3, N3b, sous-lot 2 (décision 20) : les tests d'un agent lancés par une automatisation (n8n) avec la clé de l'organisation.

| Test | Ce qu'il prouve |
|---|---|
| liste fermée | ``tests.automatiser`` est dans la liste des clés, ``tests.jouer`` n'y est toujours pas (il ouvre aussi les appels réels) |
| clé | la clé du client joue les tests de SON agent et reçoit un JSON que n8n lit (``ok``, ``statut``, compteurs, tests, échecs) |
| cloisonnement | la clé du client B reçoit 404 sur l'agent du client A, en lançant comme en relisant ; une clé reste refusée sur les routes du builder |
| statuts | ok, échec, incomplet, plafond (budget atteint) et sans test se disent en un mot ; rien de la pile ni du fournisseur n'en sort |
| garde-fous | un second rejeu du même agent pendant le premier = 409 ; au-delà du délai = 504 ; un agent sans test ne joue rien |
| relecture | ``dernier`` relit les exécutions rangées sans rien jouer |
| rôles | un rôle qui a ``tests.jouer`` lance aussi par l'API, un rôle sans l'une ni l'autre non, un rôle qui n'a que la nouvelle oui (aucune migration) |
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services import verrou
from api.services.builder.tests_agent import automatisation, execution, stockage
from api.services.equipe_mark import espaces
from api.services.equipe_mark.permissions import PERMISSIONS, PERMISSIONS_DE_CLE
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")

GRAPHE = {"nodes": [{"id": "1", "type": "startCall", "data": {"name": "Start", "prompt": "Hello"}}], "edges": []}


@pytest.fixture(autouse=True)
def _cache_du_labo_propre():
    espaces.reinitialiser_cache()
    yield
    espaces.reinitialiser_cache()


@pytest.fixture(autouse=True)
def _budget_du_mois_regle(monkeypatch):
    """RV (point 2) : une clé exige un budget du mois réglé ; ces tests ne portent pas là-dessus (voir ``test_rv_depense_des_tests.py``)."""
    monkeypatch.setattr(automatisation, "verifier_le_budget", AsyncMock(return_value=None))


async def _monde(db, s: str):
    a = await creer_organisation(db, f"n3b-a-{s}")
    b = await creer_organisation(db, f"n3b-b-{s}")
    admin, _ = await creer_compte(db, f"n3b-admin-{s}@example.com", role="Administrateur", organisations=[a, b])
    _, cle_a = await db.create_api_key(a, "n8n A", admin.id)
    _, cle_b = await db.create_api_key(b, "n8n B", admin.id)
    agent = await db.create_workflow(name="Agent A", workflow_definition=GRAPHE, user_id=admin.id, organization_id=a)
    return SimpleNamespace(a=a, b=b, cle_a={"X-API-Key": cle_a}, cle_b={"X-API-Key": cle_b}, agent=agent, admin=admin)


RENDU_OK = {
    "ok": True, "echecs": [], "total": 2, "reussis": 2, "suite_complete": True, "partiel": False, "refus": False, "version": 4,
    "resultats": [
        {"slug": "a", "nom": "A", "obligatoire": True, "statut": "ok", "reussis": 3, "total": 3, "essais": [{"secret": "x"}], "juge": {"x": 1}},
        {"slug": "b", "nom": "B", "obligatoire": False, "statut": "ok", "reussis": 3, "total": 3, "essais": []},
    ],
    "plafond": None, "depense": {"jetons": 300, "cout": 0.003}, "message": "", "elements": [], "carte": {},
}


# --------------------------------------------------------------------------- la liste fermée


def test_la_permission_est_dans_la_liste_des_cles_et_tests_jouer_n_y_est_toujours_pas():
    assert "tests.automatiser" in PERMISSIONS and "tests.automatiser" in PERMISSIONS_DE_CLE
    assert "tests.jouer" not in PERMISSIONS_DE_CLE  # il ouvre aussi les appels réels et les séries du simulateur


# --------------------------------------------------------------------------- les statuts (pur)


@pytest.mark.parametrize(
    "rendu, statut",
    [
        (RENDU_OK, "ok"),
        ({**RENDU_OK, "ok": False, "reussis": 1}, "echec"),
        ({**RENDU_OK, "ok": False, "suite_complete": False, "partiel": True}, "incomplet"),
        ({**RENDU_OK, "ok": False, "suite_complete": False, "plafond": "role budget"}, "plafond"),
        ({"disponible": False, "ok": False, "echecs": [], "total": 0, "message": "no test"}, "sans_test"),
        ({"ok": False, "echecs": [], "total": 0, "message": "None of these tests exists.", "disponible": True}, "sans_test"),
    ],
)
def test_chaque_issue_se_dit_en_un_mot(rendu, statut):
    lu = automatisation.lisible(7, rendu)
    assert lu["statut"] == statut and lu["ok"] is (statut == "ok") and lu["agent_id"] == 7


def test_la_reponse_ne_porte_que_ce_qu_une_automatisation_lit():
    lu = automatisation.lisible(7, {**RENDU_OK, "echecs": [{"test": "a", "nom": "A", "obligatoire": True, "raison": "r", "diagnostic": {"interne": 1}, "essai": 1}]})
    assert set(lu["tests"][0]) == {"slug", "nom", "obligatoire", "statut", "reussis", "total"}  # ni les essais, ni le juge
    assert set(lu["echecs"][0]) == set(automatisation.CHAMPS_ECHEC)  # ni le diagnostic interne
    assert lu["depense"] == {"jetons": 300, "cout": 0.003} and lu["message"] is None


# --------------------------------------------------------------------------- par la clé de l'organisation


async def test_la_cle_du_client_joue_les_tests_de_son_agent_et_lit_un_json_clair(db_session, monkeypatch):
    cas = await _monde(db_session, "ok")
    jouer = AsyncMock(return_value=RENDU_OK)
    monkeypatch.setattr(execution, "rejouer_la_suite", jouer)
    async with client_http() as c:
        r = await c.post(f"/api/v1/automatisation/agents/{cas.agent.id}/tests/lancer", headers=cas.cle_a, json={"repetitions": 2})
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["ok"] is True and corps["statut"] == "ok" and corps["tests_total"] == 2 and corps["tests_reussis"] == 2
    assert [t["slug"] for t in corps["tests"]] == ["a", "b"] and corps["version"] == 4
    assert jouer.await_args.kwargs["repetitions"] == 2 and jouer.await_args.args[1].id == cas.agent.id
    assert jouer.await_args.args[0].selected_organization_id == cas.a  # l'organisation de la clé, jamais celle d'un corps


async def test_sans_corps_une_repetition_et_toute_la_suite(db_session, monkeypatch):
    cas = await _monde(db_session, "def")
    jouer = AsyncMock(return_value=RENDU_OK)
    monkeypatch.setattr(execution, "rejouer_la_suite", jouer)
    async with client_http() as c:
        r = await c.post(f"/api/v1/automatisation/agents/{cas.agent.id}/tests/lancer", headers=cas.cle_a)
    assert r.status_code == 200
    assert jouer.await_args.kwargs == {"noms": None, "repetitions": 1}


async def test_l_adresse_d_un_test_ne_joue_que_ce_test(db_session, monkeypatch):
    cas = await _monde(db_session, "un")
    jouer = AsyncMock(return_value=RENDU_OK)
    monkeypatch.setattr(execution, "rejouer_la_suite", jouer)
    async with client_http() as c:
        r = await c.post(f"/api/v1/automatisation/agents/{cas.agent.id}/tests/lancer?test=urgence-gaz&test=b", headers=cas.cle_a)
    assert r.status_code == 200 and jouer.await_args.kwargs["noms"] == ["urgence-gaz", "b"]


async def test_la_cle_du_client_b_ne_touche_pas_l_agent_du_client_a(db_session, monkeypatch):
    cas = await _monde(db_session, "iso")
    jouer = AsyncMock(return_value=RENDU_OK)
    monkeypatch.setattr(execution, "rejouer_la_suite", jouer)
    async with client_http() as c:
        lancer = await c.post(f"/api/v1/automatisation/agents/{cas.agent.id}/tests/lancer", headers=cas.cle_b)
        relire = await c.get(f"/api/v1/automatisation/agents/{cas.agent.id}/tests/dernier", headers=cas.cle_b)
        mine = await c.get(f"/api/v1/automatisation/agents/{cas.agent.id}/tests/dernier", headers=cas.cle_a)
    assert lancer.status_code == 404 and relire.status_code == 404 and mine.status_code == 200
    jouer.assert_not_awaited()  # rien n'a été joué, donc rien dépensé


async def test_une_cle_reste_refusee_sur_les_routes_du_builder_qui_jouent_les_tests(db_session):
    cas = await _monde(db_session, "ferme")
    async with client_http() as c:
        r = await c.post(f"/api/v1/builder/tests/{cas.agent.id}/rejouer", headers=cas.cle_a, json={})
        s = await c.post("/api/v1/appel-simule/agents/1/series", headers=cas.cle_a, json={})
    assert r.status_code == 403 and s.status_code == 403 and "API key" in r.json()["detail"]


async def test_sans_cle_ni_session_la_route_est_refusee(db_session):
    cas = await _monde(db_session, "anon")
    async with client_http() as c:
        r = await c.post(f"/api/v1/automatisation/agents/{cas.agent.id}/tests/lancer")
    assert r.status_code in (401, 403)


async def test_un_agent_sans_test_ne_joue_rien_et_le_dit(db_session):
    cas = await _monde(db_session, "vide")
    async with client_http() as c:
        r = await c.post(f"/api/v1/automatisation/agents/{cas.agent.id}/tests/lancer", headers=cas.cle_a)
    assert r.status_code == 200 and r.json()["statut"] == "sans_test" and r.json()["ok"] is False and r.json()["tests_total"] == 0


async def test_un_budget_atteint_arrete_la_suite_et_se_dit_plafond(db_session, monkeypatch):
    cas = await _monde(db_session, "plaf")
    arretee = {**RENDU_OK, "ok": False, "suite_complete": False, "reussis": 1, "plafond": "monthly budget of the judge", "message": "Stopped."}
    monkeypatch.setattr(execution, "rejouer_la_suite", AsyncMock(return_value=arretee))
    async with client_http() as c:
        r = await c.post(f"/api/v1/automatisation/agents/{cas.agent.id}/tests/lancer", headers=cas.cle_a)
    assert r.json()["statut"] == "plafond" and r.json()["plafond"] == "monthly budget of the judge" and r.json()["ok"] is False


async def test_un_second_rejeu_du_meme_agent_pendant_le_premier_est_refuse(db_session, monkeypatch):
    cas = await _monde(db_session, "conc")
    debut, fin = asyncio.Event(), asyncio.Event()

    async def lent(*_a, **_k):
        debut.set()
        await fin.wait()
        return RENDU_OK

    monkeypatch.setattr(execution, "rejouer_la_suite", lent)
    adresse = f"/api/v1/automatisation/agents/{cas.agent.id}/tests/lancer"
    async with client_http() as c:
        premier = asyncio.create_task(c.post(adresse, headers=cas.cle_a))
        await asyncio.wait_for(debut.wait(), 10)
        second = await c.post(adresse, headers=cas.cle_a)
        fin.set()
        rendu = await premier
    assert second.status_code == 409 and rendu.status_code == 200  # le premier va au bout, le second ne dépense rien
    async with client_http() as c:  # le verrou est rendu : un nouveau rejeu passe
        monkeypatch.setattr(execution, "rejouer_la_suite", AsyncMock(return_value=RENDU_OK))
        assert (await c.post(adresse, headers=cas.cle_a)).status_code == 200


async def test_un_rejeu_trop_long_est_arrete_avec_un_504(db_session, monkeypatch):
    cas = await _monde(db_session, "long")

    async def sans_fin(*_a, **_k):
        await asyncio.sleep(60)

    monkeypatch.setattr(execution, "rejouer_la_suite", sans_fin)
    monkeypatch.setattr(automatisation, "DELAI_MAX_S", 0.2)
    async with client_http() as c:
        r = await c.post(f"/api/v1/automatisation/agents/{cas.agent.id}/tests/lancer", headers=cas.cle_a)
    assert r.status_code == 504 and "dernier" in r.json()["detail"]


async def test_une_panne_du_verrou_est_un_409_et_jamais_un_rejeu(db_session, monkeypatch):
    cas = await _monde(db_session, "occupe")
    jouer = AsyncMock(return_value=RENDU_OK)
    monkeypatch.setattr(execution, "rejouer_la_suite", jouer)

    class Occupe:
        async def __aenter__(self):
            raise verrou.Occupe("busy")

        async def __aexit__(self, *_):
            return False

    monkeypatch.setattr(verrou, "verrou", lambda *a, **k: Occupe())
    async with client_http() as c:
        r = await c.post(f"/api/v1/automatisation/agents/{cas.agent.id}/tests/lancer", headers=cas.cle_a)
    assert r.status_code == 409
    jouer.assert_not_awaited()


# --------------------------------------------------------------------------- relire sans jouer


async def test_dernier_relit_les_executions_rangees_sans_rien_jouer(db_session, monkeypatch):
    cas = await _monde(db_session, "der")
    jouer = AsyncMock()
    monkeypatch.setattr(execution, "rejouer_la_suite", jouer)
    tests = [{"slug": "a", "nom": "A", "obligatoire": True}, {"slug": "b", "nom": "B"}]
    rangees = {
        "a": [{"statut": "ok", "reussis": 3, "total": 3, "le": "2026-11-05T10:00:00+00:00", "version": 4}],
        "b": [{"statut": "erreur", "reussis": 1, "total": 3, "le": "2026-11-05T10:01:00+00:00", "version": 4}],
    }
    monkeypatch.setattr(stockage, "lister", AsyncMock(return_value=tests))
    monkeypatch.setattr(stockage, "resultats", AsyncMock(side_effect=lambda o, w, slug: rangees[slug]))
    async with client_http() as c:
        r = await c.get(f"/api/v1/automatisation/agents/{cas.agent.id}/tests/dernier", headers=cas.cle_a)
    corps = r.json()
    assert r.status_code == 200 and corps["statut"] == "echec" and corps["ok"] is False
    assert corps["tests_total"] == 2 and corps["tests_reussis"] == 1 and corps["suite_complete"] is True and corps["version"] == 4
    assert corps["obligatoire_en_echec"] is False  # le test obligatoire est vert
    jouer.assert_not_awaited()


async def test_dernier_dit_incomplet_tant_qu_un_test_n_a_jamais_ete_joue(monkeypatch):
    monkeypatch.setattr(stockage, "lister", AsyncMock(return_value=[{"slug": "a", "nom": "A"}, {"slug": "b", "nom": "B"}]))
    monkeypatch.setattr(
        stockage, "resultats", AsyncMock(side_effect=lambda o, w, slug: [{"statut": "ok", "reussis": 1, "total": 1}] if slug == "a" else [])
    )
    lu = await automatisation.dernier(1, 2)
    assert lu["statut"] == "incomplet" and lu["ok"] is False and lu["tests_total"] == 2


# --------------------------------------------------------------------------- les rôles de l'équipe (aucune migration)


async def test_un_role_qui_joue_les_tests_peut_aussi_les_lancer_par_l_api_et_les_autres_non(db_session, monkeypatch):
    cas = await _monde(db_session, "roles")
    monkeypatch.setattr(execution, "rejouer_la_suite", AsyncMock(return_value=RENDU_OK))
    await db_session.creer_role(nom="N3b-joue", labo_ouvert=False, tous_les_clients=True, permissions=["tests.jouer"], organisations=[])
    await db_session.creer_role(nom="N3b-voit", labo_ouvert=False, tous_les_clients=True, permissions=["conversations.voir"], organisations=[])
    await db_session.creer_role(nom="N3b-seule", labo_ouvert=False, tous_les_clients=True, permissions=["tests.automatiser"], organisations=[])
    adresse = f"/api/v1/automatisation/agents/{cas.agent.id}/tests/lancer"
    attendu = {"N3b-joue": 200, "N3b-voit": 403, "N3b-seule": 200}
    async with client_http() as c:
        for nom, statut in attendu.items():
            _, jeton = await creer_compte(db_session, f"{nom}@example.com", role=nom, organisations=[cas.a])
            r = await c.post(adresse, headers=entetes(jeton, cas.a))
            assert r.status_code == statut, (nom, r.status_code, r.text[:200])
