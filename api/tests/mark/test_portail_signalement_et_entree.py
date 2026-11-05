"""[.mark] Builder partie 3, sous-lot 17b : ce que le portail attend du fork, par la vraie application et la vraie clé d'API.

| Test | Ce qu'il prouve |
|---|---|
| signalement | un fil de sorte ``signalement`` lié à un appel du client crée, dans le même geste, un problème « À améliorer » relevé par le client (agent de l'appel, citation) et s'y relie ; le même appel signalé deux fois retrouve le même problème |
| signalement refusé | sans appel : 422 ; un appel d'un AUTRE client : 404 et aucun fil ni problème chez personne ; un appel sur un fil qui n'est pas un signalement : 422 |
| auteur et « les miens » | le fil garde son auteur d'ouverture ; ``miens`` ne rend que les fils de l'auteur de l'en-tête (422 sans en-tête) ; jamais ceux d'un autre client |
| pagination | ``page`` et ``limit`` bornent la liste, le total est dans ``X-Total-Count`` ; ``limit`` au-delà du maximum : 422 |
| lien d'entrée | le lien « client.jeton » vérifié par la clé de CE client rend l'adresse du membre ; rejoué, ou présenté par la clé d'un autre client : 403, et l'autre client ne brûle pas le lien |
| historique des gestes | autoriser et couper un logiciel entrent au journal avec l'auteur réel du portail ; la clé d'un autre client n'en voit rien ; le filtre par logiciel et la pagination marchent |
| migration | la montée ajoute les trois colonnes et l'index, la descente les retire (schéma à part) |
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from api.services.equipe_mark import espaces
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)
from api.tests.mark.test_connecteurs_catalogue_f3 import base, relais  # noqa: F401  (fixtures)

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")

MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "b8d3f6a1c4e2_signalement_et_auteur_des_fils.py"
FILS = "/api/v1/organizations/relation/fils"


@pytest.fixture(autouse=True)
def _cache_du_labo_propre():
    espaces.reinitialiser_cache()
    yield
    espaces.reinitialiser_cache()


def _cle(cle: str, auteur: str | None = None) -> dict:
    h = {"X-API-Key": cle}
    if auteur:
        h["X-Mark-Auteur"] = auteur
    return h


async def _deux_clients(db, s: str):
    a = await creer_organisation(db, f"pf-a-{s}")
    b = await creer_organisation(db, f"pf-b-{s}")
    admin, jeton = await creer_compte(db, f"pf-admin-{s}@example.com", role="Administrateur", organisations=[a, b])
    _, cle_a = await db.create_api_key(a, "portail A", admin.id)
    _, cle_b = await db.create_api_key(b, "portail B", admin.id)
    definition = {"nodes": [], "edges": []}
    runs, agents = {}, {}
    for org, nom in ((a, f"agent A {s}"), (b, f"agent B {s}")):
        wf = await db.create_workflow(nom, definition, admin.id, org)
        run = await db.create_workflow_run("run " + nom, wf.id, "chat", admin.id, organization_id=org)
        runs[org], agents[org] = run.id, wf.id
    return SimpleNamespace(a=a, b=b, cle_a=cle_a, cle_b=cle_b, admin=admin, jeton=jeton, runs=runs, agents=agents)


# --------------------------------------------------------------------------- signalement


async def test_un_signalement_lie_a_un_appel_cree_le_probleme_releve_par_le_client(db_session):
    cas = await _deux_clients(db_session, "s1")
    corps = {"sorte": "signalement", "sujet": "Le rendez-vous est faux", "texte": "L'agent a dit jeudi, pas mardi.", "run_id": cas.runs[cas.a]}
    async with client_http() as c:
        r = await c.post(FILS, headers=_cle(cas.cle_a, "portail : Martine Leroy"), json=corps)
        assert r.status_code == 201, r.text
        fil = r.json()
        # Le même appel signalé une seconde fois : un nouveau fil, le MÊME problème.
        r2 = await c.post(FILS, headers=_cle(cas.cle_a, "portail : Martine Leroy"), json={**corps, "sujet": "Encore", "texte": "Toujours faux."})
        assert r2.status_code == 201, r2.text
    assert fil["sorte"] == "signalement" and fil["run_id"] == cas.runs[cas.a] and fil["ouvert_par"] == "portail : Martine Leroy"
    lignes, _ = await db_session.lister_les_ameliorations(cas.a, etat="a_trier")
    assert len(lignes) == 1
    probleme = lignes[0]
    assert probleme["releve_par"] == "client" and probleme["workflow_id"] == cas.agents[cas.a]
    assert probleme["titre"] == "Le rendez-vous est faux" and probleme["nb_cas"] == 1
    assert probleme["cas"][0]["run_id"] == cas.runs[cas.a]
    # Le fil est relié au problème (côté base), l'autre client n'a rien.
    complet = await db_session.lire_fil_relation(cas.a, fil["id"], avec_internes=True)
    assert complet["amelioration_id"] == probleme["id"]
    assert (await db_session.lister_les_ameliorations(cas.b, etat="a_trier"))[0] == []
    # La ligne « Signalement » de la fiche du client (statistiques du Hub) compte ce problème.
    assert (await db_session.statistiques_des_clients_relation([cas.a]))[cas.a]["signalements"] == 1


async def test_un_signalement_refuse_ne_laisse_ni_fil_ni_probleme(db_session):
    cas = await _deux_clients(db_session, "s2")
    async with client_http() as c:
        sans_appel = await c.post(FILS, headers=_cle(cas.cle_a), json={"sorte": "signalement", "sujet": "x", "texte": "y"})
        appel_d_un_autre = await c.post(
            FILS, headers=_cle(cas.cle_a), json={"sorte": "signalement", "sujet": "x", "texte": "y", "run_id": cas.runs[cas.b]}
        )
        inconnu = await c.post(FILS, headers=_cle(cas.cle_a), json={"sorte": "signalement", "sujet": "x", "texte": "y", "run_id": 999_999_999})
        sur_un_message = await c.post(FILS, headers=_cle(cas.cle_a), json={"sorte": "message", "sujet": "x", "texte": "y", "run_id": cas.runs[cas.a]})
        chez_a = await c.get(FILS, headers=_cle(cas.cle_a))
    assert sans_appel.status_code == 422
    assert appel_d_un_autre.status_code == 404 and inconnu.status_code == 404  # même réponse : l'appel d'un autre n'existe pas
    assert sur_un_message.status_code == 422
    assert chez_a.json() == []
    for org in (cas.a, cas.b):
        assert (await db_session.lister_les_ameliorations(org, etat="a_trier"))[0] == []


# --------------------------------------------------------------------------- auteur, « les miens », pagination


async def test_les_miens_et_la_pagination_des_fils(db_session):
    cas = await _deux_clients(db_session, "p1")
    async with client_http() as c:
        for i in range(3):
            assert (await c.post(FILS, headers=_cle(cas.cle_a, "portail : Martine Leroy"), json={"sujet": f"M{i}", "texte": "t"})).status_code == 201
        assert (await c.post(FILS, headers=_cle(cas.cle_a, "portail : Paul Durand"), json={"sujet": "P", "texte": "t"})).status_code == 201
        assert (await c.post(FILS, headers=_cle(cas.cle_b, "portail : Martine Leroy"), json={"sujet": "Autre client", "texte": "t"})).status_code == 201
        premiere = await c.get(f"{FILS}?page=0&limit=2", headers=_cle(cas.cle_a))
        seconde = await c.get(f"{FILS}?page=1&limit=2", headers=_cle(cas.cle_a))
        troisieme = await c.get(f"{FILS}?page=2&limit=2", headers=_cle(cas.cle_a))
        miens = await c.get(f"{FILS}?miens=true", headers=_cle(cas.cle_a, "portail : Martine Leroy"))
        miens_de_paul = await c.get(f"{FILS}?miens=true&limit=1", headers=_cle(cas.cle_a, "portail : Paul Durand"))
        sans_auteur = await c.get(f"{FILS}?miens=true", headers=_cle(cas.cle_a))
        trop = await c.get(f"{FILS}?limit=101", headers=_cle(cas.cle_a))
    assert [len(r.json()) for r in (premiere, seconde, troisieme)] == [2, 2, 0]
    assert premiere.headers["x-total-count"] == "4"
    ids = [f["id"] for f in premiere.json() + seconde.json()]
    assert len(set(ids)) == 4  # aucune ligne deux fois, aucune perdue
    assert sorted(f["sujet"] for f in miens.json()) == ["M0", "M1", "M2"] and miens.headers["x-total-count"] == "3"
    assert [f["sujet"] for f in miens_de_paul.json()] == ["P"]
    assert all(f["ouvert_par"] == "portail : Martine Leroy" for f in miens.json())
    assert "Autre client" not in (premiere.text + seconde.text + miens.text)  # les fils de l'autre client n'apparaissent jamais
    assert sans_auteur.status_code == 422  # jamais « tous » en silence
    assert trop.status_code == 422


# --------------------------------------------------------------------------- lien d'entrée


async def test_le_lien_d_entree_porte_le_client_rend_l_adresse_du_membre_et_ne_sert_qu_une_fois(db_session):
    cas = await _deux_clients(db_session, "e1")
    async with client_http() as c:
        cree = await c.post(f"/api/v1/relation/clients/{cas.a}/entree", headers=entetes(cas.jeton), json={"motif": "Aider à régler le widget"})
        assert cree.status_code == 201, cree.text
        lien = cree.json()["lien"]
        assert lien == f"{cas.a}.{cree.json()['jeton']}"
        # La clé d'un AUTRE client le présente : refusé, et le lien n'est pas brûlé pour autant.
        autre = await c.post("/api/v1/organizations/relation/entree/verifier", headers=_cle(cas.cle_b), json={"jeton": lien})
        assert autre.status_code == 403
        bon = await c.post("/api/v1/organizations/relation/entree/verifier", headers=_cle(cas.cle_a), json={"jeton": lien})
        assert bon.status_code == 200, bon.text
        rejoue = await c.post("/api/v1/organizations/relation/entree/verifier", headers=_cle(cas.cle_a), json={"jeton": lien})
        assert rejoue.status_code == 403
        # La forme d'avant (le jeton seul) marche encore, pour son client seulement.
        seul = await c.post(f"/api/v1/relation/clients/{cas.a}/entree", headers=entetes(cas.jeton), json={})
        sans_client = await c.post("/api/v1/organizations/relation/entree/verifier", headers=_cle(cas.cle_a), json={"jeton": seul.json()["jeton"]})
        assert sans_client.status_code == 200
        # Un lien qui nomme un client mais présenté avec sa propre clé par B reste refusé.
        faux = await c.post("/api/v1/organizations/relation/entree/verifier", headers=_cle(cas.cle_b), json={"jeton": f"{cas.b}.{cree.json()['jeton']}"})
        assert faux.status_code == 403
    assert bon.json()["adresse"] == "pf-admin-e1@example.com" and bon.json()["motif"] == "Aider à régler le widget"
    assert cree.json()["jeton"] not in bon.text  # le jeton n'est jamais rendu


# --------------------------------------------------------------------------- historique des gestes d'un logiciel


async def test_l_historique_des_gestes_dit_qui_a_autorise_ou_coupe_et_reste_a_son_client(db_session, base, relais):  # noqa: F811
    cas = await _deux_clients(db_session, "h1")
    async with client_http() as c:
        for compte in ("equipe sav", "equipe vente"):
            r = await c.post("/api/v1/connecteurs/lien", headers=_cle(cas.cle_a, "portail : Martine Leroy"), json={"connecteurs": ["slack"], "compte": compte})
            assert r.status_code == 200, r.text
        r = await c.post("/api/v1/connecteurs/lien", headers=_cle(cas.cle_a, "portail : Paul Durand"), json={"connecteurs": ["notion"]})
        assert r.status_code == 200
        coupe = await c.delete("/api/v1/connecteurs/connexions/slack", headers=_cle(cas.cle_a, "portail : Paul Durand"))
        assert coupe.status_code == 404  # rien à couper (aucune connexion réelle) : pas de geste noté
        tout = await c.get("/api/v1/connecteurs/historique", headers=_cle(cas.cle_a))
        slack = await c.get("/api/v1/connecteurs/historique?logiciel=slack", headers=_cle(cas.cle_a))
        page = await c.get("/api/v1/connecteurs/historique?limit=1&page=1", headers=_cle(cas.cle_a))
        chez_b = await c.get("/api/v1/connecteurs/historique", headers=_cle(cas.cle_b))
    assert tout.status_code == 200, tout.text
    gestes = tout.json()["gestes"]
    assert tout.json()["total"] == 3
    assert [(g["geste"], g["logiciel"], g["auteur"]) for g in gestes] == [
        ("autoriser", "notion", "portail : Paul Durand"),
        ("autoriser", "slack", "portail : Martine Leroy"),
        ("autoriser", "slack", "portail : Martine Leroy"),
    ]
    assert sorted(g["compte"] or "" for g in gestes if g["logiciel"] == "slack") == ["equipe sav", "equipe vente"]
    assert slack.json()["total"] == 2 and all(g["logiciel"] == "slack" for g in slack.json()["gestes"])
    assert len(page.json()["gestes"]) == 1 and page.json()["total"] == 3
    assert chez_b.json() == {"gestes": [], "total": 0, "page": 0, "limit": 25}


# --------------------------------------------------------------------------- migration


async def test_la_migration_ajoute_les_colonnes_et_se_defait(db_session):
    spec = importlib.util.spec_from_file_location("migration_signalement", MIGRATION)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    async with db_session.async_session() as session:
        colonnes = {c for (c,) in await session.execute(sa.text("SELECT column_name FROM information_schema.columns WHERE table_name = 'mark_relation_fils'"))}
        index = {i for (i,) in await session.execute(sa.text("SELECT indexname FROM pg_indexes WHERE tablename = 'mark_relation_fils'"))}
    assert {"run_id", "amelioration_id", "ouvert_par"} <= colonnes
    assert "ix_mark_relation_fils_ouvert_par" in index
    assert migration.down_revision == "a7c2e9d4b6f1"
