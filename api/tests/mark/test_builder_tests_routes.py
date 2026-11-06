"""[.mark] builder-agent-vocal, lot 6 : les routes de la page « Tests et corrections » (``/builder/tests``) et le tri (assigné, origine).

Ce qui doit tenir : la création par la route passe par la MÊME fonction que l'action (deux portes) ; un agent d'une autre
organisation est un 404 ; l'export est un fichier téléchargeable ; la publication dit ce qui la bloque ; le retour arrière est un
brouillon ; l'assigné est une personne de l'organisation ; l'origine se pose et se filtre.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import builder_tests as route
from api.routes import tri as route_tri
from api.services.auth.depends import get_user_with_selected_organization
from api.services.builder.tests_agent import execution
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, graphe_depart, utilisateur
from api.tests.mark.test_builder_tests_agent import banc, essai, un_rejeu  # noqa: F401 -- la fixture et les aides du lot

EQUIPE = utilisateur(1, ORG_CLIENT)
AUTRE = utilisateur(2, 8)
CRITERE = {"type": "texte_absent", "texte": "outil_interne"}


def client_pour(user) -> TestClient:
    app = FastAPI()
    app.include_router(route.router)
    app.include_router(route_tri.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: user
    return TestClient(app)


@pytest.fixture(autouse=True)
def _base_des_routes(banc, monkeypatch):  # noqa: F811
    monkeypatch.setattr(route, "db_client", banc)


def creer(c, nom="Numéro dit", **plus):
    return c.post(f"/builder/tests/{AGENT}", json={"nom": nom, "replique": "Bonjour, un renseignement.", "criteres": [CRITERE], **plus})


def test_creer_lister_lire_changer_supprimer_un_test():
    c = client_pour(EQUIPE)
    r = creer(c, obligatoire=True, dossier="Sécurité")
    assert r.status_code == 200 and r.json()["ok"] is True
    slug = r.json()["test"]["slug"]
    lignes = c.get(f"/builder/tests/{AGENT}").json()["tests"]
    assert [(l["slug"], l["obligatoire"], l["dossier"], l["derniere"]) for l in lignes] == [(slug, True, "Sécurité", None)]
    detail = c.get(f"/builder/tests/{AGENT}/{slug}").json()
    assert detail["test"]["replique"].startswith("Bonjour") and detail["resultats"] == []
    changé = c.patch(f"/builder/tests/{AGENT}/{slug}", json={"obligatoire": False, "dossier": "Autre"})
    assert changé.json()["obligatoire"] is False and changé.json()["dossier"] == "Autre"
    assert c.delete(f"/builder/tests/{AGENT}/{slug}").status_code == 200
    assert c.get(f"/builder/tests/{AGENT}/{slug}").status_code == 404 and c.delete(f"/builder/tests/{AGENT}/{slug}").status_code == 404


def test_une_creation_invalide_est_refusee_avec_la_raison():
    c = client_pour(EQUIPE)
    r = c.post(f"/builder/tests/{AGENT}", json={"nom": "x", "replique": "bonjour", "criteres": []})
    assert r.status_code == 422 and "criterion" in r.json()["detail"]


def test_un_agent_d_une_autre_organisation_est_un_404_partout():
    c = client_pour(AUTRE)
    for appel in (
        c.get(f"/builder/tests/{AGENT}"),
        creer(c),
        c.post(f"/builder/tests/{AGENT}/rejouer", json={}),
        c.get(f"/builder/tests/{AGENT}/publication"),
        c.get(f"/builder/tests/{AGENT}/export"),
        c.get(f"/builder/tests/{AGENT}/corrections"),
        c.post(f"/builder/tests/{AGENT}/corrections/c1/retour"),
        c.get(f"/builder/tests/{AGENT}/x"),
    ):
        assert appel.status_code == 404


def test_rejouer_par_la_route_rend_le_contrat_de_l_action_et_la_liste_montre_la_derniere_execution():
    c = client_pour(EQUIPE)
    slug = creer(c).json()["test"]["slug"]
    execution.DEPENDANCES.rejouer_un_tour = un_rejeu([essai(i, "Bien.") for i in (1, 2, 3)])
    r = c.post(f"/builder/tests/{AGENT}/rejouer", json={"repetitions": 3}).json()
    assert (r["ok"], r["echecs"], r["total"]) == (True, [], 1)
    ligne = c.get(f"/builder/tests/{AGENT}").json()["tests"][0]
    assert ligne["derniere"]["statut"] == "ok" and ligne["derniere"]["version"] == 2
    assert len(c.get(f"/builder/tests/{AGENT}/{slug}").json()["resultats"]) == 1


def test_rejouer_sans_test_dit_que_ce_n_est_pas_disponible_sans_erreur_http():
    r = client_pour(EQUIPE).post(f"/builder/tests/{AGENT}/rejouer", json={})
    assert r.status_code == 200 and r.json()["disponible"] is False


def test_l_etat_de_la_publication_dit_ce_qui_bloque():
    c = client_pour(EQUIPE)
    creer(c, obligatoire=True)
    etat = c.get(f"/builder/tests/{AGENT}/publication").json()
    assert etat["brouillon"] is True and etat["version"] == 2 and etat["bloque"] is True
    assert etat["tests_obligatoires"][0]["raison"] == "never replayed" and etat["controle"]["ok"] is True
    execution.DEPENDANCES.rejouer_un_tour = un_rejeu([essai(i, "Bien.") for i in (1, 2, 3)])
    c.post(f"/builder/tests/{AGENT}/rejouer", json={})
    assert c.get(f"/builder/tests/{AGENT}/publication").json()["bloque"] is False


def test_l_export_est_un_fichier_a_telecharger():
    c = client_pour(EQUIPE)
    creer(c)
    r = c.get(f"/builder/tests/{AGENT}/export")
    assert r.status_code == 200 and r.headers["content-disposition"].startswith("attachment;") and r.json()["format"] == "tests-agent-mark"


def test_l_historique_et_le_retour_arriere_par_la_route(banc):
    c = client_pour(EQUIPE)
    creer(c)
    execution.DEPENDANCES.rejouer_un_tour = un_rejeu([essai(i, "Bien.") for i in (1, 2, 3)])
    c.post(f"/builder/tests/{AGENT}/rejouer", json={})
    corrections = c.get(f"/builder/tests/{AGENT}/corrections").json()["corrections"]
    assert len(corrections) == 1 and "instantane" not in corrections[0]
    retour = c.post(f"/builder/tests/{AGENT}/corrections/{corrections[0]['id']}/retour")
    assert retour.status_code == 200 and retour.json()["ok"] is True
    assert c.post(f"/builder/tests/{AGENT}/corrections/c99/retour").status_code == 409
    assert banc.workflows[AGENT].released_definition.version_number == 1


def test_noter_un_avis_du_juge():
    r = client_pour(EQUIPE).post(f"/builder/tests/{AGENT}/juge/notes", json={"identifiant": "t:1", "ok": True})
    assert r.json() == {"ok": True, "notes": 1}


# --- le tri : assigné, statut, origine --------------------------------------------------------------------------------------------------------


class FauxTri:
    def __init__(self):
        self.annotations: dict = {}
        self.ecritures: list[dict] = []
        self.membres = {5}

    async def get_organization_users(self, organization_id):
        return [SimpleNamespace(id=5, email="a@exemple.test"), SimpleNamespace(id=6, email=None)] if organization_id == ORG_CLIENT else []

    async def run_de_l_organisation(self, organisation, run_id):
        if organisation != ORG_CLIENT:
            return None
        return {"run_id": run_id, "gathered_context": {"signalements": [{"source": "agent", "motif": "m", "categorie": "autre", "tour": 1}]}, "annotations": self.annotations}

    async def ecrire_le_tri(self, organisation, run_id, identifiant, statut, par=None, **plus):
        self.ecritures.append({"identifiant": identifiant, "statut": statut, **plus})
        entree = {**self.annotations.get("tri", {}).get(identifiant, {}), **({"statut": statut} if statut else {}), **{k: v for k, v in plus.items()}}
        self.annotations = {"tri": {identifiant: {"statut": "ouvert", **entree}}}
        return True

    async def is_user_member_of_organization(self, user_id, organization_id):
        return user_id in self.membres and organization_id == ORG_CLIENT

    async def runs_avec(self, organisation, **k):
        return [{"run_id": 1, "workflow_id": AGENT, "workflow_nom": "a", "cree_le": None, "extrait": {"signalements": [{"source": "agent", "motif": "m", "categorie": "autre", "tour": 1}]}, "annotations": self.annotations}], False


@pytest.fixture
def faux_tri(monkeypatch):
    faux = FauxTri()
    monkeypatch.setattr(route_tri, "db_client", faux)
    return faux


def test_assigner_un_signalement_a_une_personne_de_l_organisation_et_poser_son_origine(faux_tri):
    c = client_pour(EQUIPE)
    r = c.put("/tri/1", json={"identifiant": "agent:0", "assigne": 5, "origine": "client"})
    assert r.status_code == 200 and r.json()["assigne"] == 5 and r.json()["origine"] == "client" and r.json()["statut"] == "ouvert"
    assert faux_tri.ecritures[0]["assigne"] == 5
    # Un statut seul ne touche ni l'assigné ni l'origine ; ``assigne: null`` retire la personne.
    r = c.put("/tri/1", json={"identifiant": "agent:0", "statut": "en cours"})
    assert r.json()["statut"] == "en cours" and "assigne" not in faux_tri.ecritures[1]
    r = c.put("/tri/1", json={"identifiant": "agent:0", "assigne": None})
    assert faux_tri.ecritures[2]["assigne"] is None and r.json()["assigne"] is None


def test_on_n_assigne_pas_quelqu_un_d_une_autre_organisation_et_on_ne_change_rien_sans_rien(faux_tri):
    c = client_pour(EQUIPE)
    assert c.put("/tri/1", json={"identifiant": "agent:0", "assigne": 999}).status_code == 404
    assert c.put("/tri/1", json={"identifiant": "agent:0"}).status_code == 422
    assert c.put("/tri/1", json={"identifiant": "agent:0", "origine": "ailleurs"}).status_code == 422
    assert faux_tri.ecritures == []


def test_la_file_de_tri_montre_l_assigne_l_origine_et_se_filtre_par_origine(faux_tri):
    c = client_pour(EQUIPE)
    ligne = c.get("/tri").json()["lignes"][0]
    assert (ligne["assigne"], ligne["origine"], ligne["origine_suggeree"]) == (None, None, "recette")
    c.put("/tri/1", json={"identifiant": "agent:0", "origine": "code", "assigne": 5})
    assert [l["id"] for l in c.get("/tri", params={"origine": "code"}).json()["lignes"]] == ["agent:0"]
    assert c.get("/tri", params={"origine": "client"}).json()["lignes"] == []
    assert c.get("/tri").json()["lignes"][0]["assigne"] == 5



def test_les_personnes_assignables_sont_celles_de_l_organisation_seulement(faux_tri):
    assert client_pour(EQUIPE).get("/tri/personnes").json() == [{"id": 5, "nom": "a@exemple.test"}, {"id": 6, "nom": "#6"}]
    assert client_pour(AUTRE).get("/tri/personnes").json() == []
