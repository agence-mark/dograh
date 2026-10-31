"""[.mark] builder-agent-vocal, lots 1 et 2 : les routes ``/builder`` (écran).

Ce qui doit tenir : la clé du cerveau n'est jamais renvoyée (ni relue, ni dans une erreur) et ne se range que dans le
coffre ; seule l'équipe .mark règle le cerveau et écrit dans la bibliothèque, toute organisation la lit ; l'écran
est le seul à approuver le document de conception, valider la fiche, passer en Recette, rejeter ou accepter ; la
conversation est diffusée en flux ; un agent d'une autre organisation est un 404 ;
``POST /workflow/create/template`` ne sort plus vers le service hébergé.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import builder as route
from api.routes import workflow as route_workflow
from api.services.auth.depends import get_user, get_user_with_selected_organization
from api.services.builder import conception, contexte, fiche
from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.modele import Banc
from api.services.builder.cerveau.factice import CerveauFactice, appel, texte, tour
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, ORG_MARK, utilisateur

CLE = "cle-factice-VALEUR-SECRETE-0123456789"
EQUIPE = utilisateur(1, ORG_CLIENT)  # membre de l'organisation .mark, au travail chez un client
AUTRE = utilisateur(2, 8)  # une autre organisation, pas de l'équipe
CONCEPTION = conception.Conception(objectif="o", reussite="r")


def client_pour(user, monde_=None) -> TestClient:
    app = FastAPI()
    app.include_router(route.router)
    app.include_router(route_workflow.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: user
    app.dependency_overrides[get_user] = lambda: user
    return TestClient(app)


def evenements(reponse) -> list[dict]:
    lignes = [ligne for ligne in reponse.text.split("\n\n") if ligne.startswith("data: ")]
    return [json.loads(ligne[6:]) for ligne in lignes]


@pytest.fixture(autouse=True)
def _la_base_des_routes(monde, monkeypatch):
    """Les routes lisent l'agent dans la base : la même base en mémoire que le reste du monde simulé."""
    monkeypatch.setattr(route, "db_client", monde)


REGLAGES = {"format": "anthropic", "modele": "claude-x", "plafond_jetons": 50_000}


# --- le cerveau : la clé ne sort jamais ----------------------------------------------------------------------------------


def test_la_cle_va_au_coffre_et_n_est_jamais_renvoyee(monde):
    c = client_pour(EQUIPE)
    reponse = c.put("/builder/cerveau", json={**REGLAGES, "cle": CLE})
    assert reponse.status_code == 200 and reponse.json()["cle_posee"] is True
    assert CLE not in reponse.text and "cle_ref" not in reponse.json()
    lu = c.get("/builder/cerveau")
    assert CLE not in lu.text and lu.json()["modele"] == "claude-x" and lu.json()["cle_posee"] is True
    # Rangée dans le coffre de l'organisation .mark, jamais dans la ligne de réglages.
    ligne = monde.configs[(ORG_MARK, "MARK_BUILDER_CERVEAU")]
    assert CLE not in json.dumps(ligne)
    (identifiant,) = monde.credentials.values()
    assert identifiant.credential_data["token"] == CLE and identifiant.organization_id == ORG_MARK
    assert "mark_bibliotheque" not in identifiant.credential_data  # pas proposée comme clé d'un agent client


def test_remettre_les_reglages_sans_cle_garde_la_cle_et_une_nouvelle_la_remplace(monde):
    c = client_pour(EQUIPE)
    c.put("/builder/cerveau", json={**REGLAGES, "cle": CLE})
    c.put("/builder/cerveau", json={**REGLAGES, "modele": "claude-y"})
    assert c.get("/builder/cerveau").json()["cle_posee"] is True and len(monde.credentials) == 1
    c.put("/builder/cerveau", json={**REGLAGES, "cle": "cle-factice-AUTRE-9876543210"})
    assert len(monde.credentials) == 1 and next(iter(monde.credentials.values())).credential_data["token"].startswith("cle-factice-AUTRE")


def test_une_cle_mal_saisie_n_est_pas_renvoyee_dans_l_erreur(monde):
    reponse = client_pour(EQUIPE).put("/builder/cerveau", json={**REGLAGES, "cle": "court"})
    assert reponse.status_code == 422 and "court" not in reponse.text.replace("A key holds", "")


def test_l_adresse_d_un_fournisseur_est_en_https(monde):
    c = client_pour(EQUIPE)
    assert c.put("/builder/cerveau", json={**REGLAGES, "adresse": "http://exemple.test/v1", "cle": CLE}).status_code == 422
    assert not monde.credentials  # rien n'est rangé avant la vérification
    assert c.put("/builder/cerveau", json={**REGLAGES, "adresse": "https://api.exemple.test/v1", "cle": CLE}).status_code == 200


def test_seule_l_equipe_regle_le_cerveau(monde):
    reponse = client_pour(AUTRE).put("/builder/cerveau", json={**REGLAGES, "cle": CLE})
    assert reponse.status_code == 403 and not monde.credentials
    # Revue N3 : le modèle, le plafond et la présence d'une clé sont ceux de .mark, pas ceux d'un client.
    assert client_pour(AUTRE).get("/builder/cerveau").status_code == 403
    assert client_pour(EQUIPE).get("/builder/cerveau").status_code == 200


# --- la conversation en flux ----------------------------------------------------------------------------------------------


def preparer_le_cerveau(monde, monkeypatch, cerveau):
    client_pour(EQUIPE).put("/builder/cerveau", json={**REGLAGES, "cle": CLE})
    vus = []

    def fabrique(reglages, cle):
        vus.append((reglages, cle))
        return cerveau

    monkeypatch.setattr(route, "fabriquer_le_cerveau", fabrique)
    return vus


def test_la_conversation_est_diffusee_en_flux_et_la_cle_ne_va_qu_au_fabricant_du_cerveau(monde, monkeypatch):
    cerveau = CerveauFactice(tour(texte("Bonjour."), appel("fiche_lire", {}, "f1")), tour(texte("Fiche vide.")))
    vus = preparer_le_cerveau(monde, monkeypatch, cerveau)
    reponse = client_pour(EQUIPE).post("/builder/conversation", json={"workflow_id": AGENT, "message": "Où en est-on ?"})
    assert reponse.status_code == 200 and reponse.headers["content-type"].startswith("text/event-stream")
    genres = [e["type"] for e in evenements(reponse)]
    assert genres == ["texte", "action", "depense", "resultat", "texte", "depense", "fin"]
    assert CLE not in reponse.text
    assert vus[0][1] == CLE and vus[0][0].modele == "claude-x"
    historique = client_pour(EQUIPE).get(f"/builder/conversation/{AGENT}").json()
    assert [m["role"] for m in historique["messages"]] == ["user", "assistant", "assistant"]
    assert historique["depense"]["jetons"] == 300 and historique["en_cours"] is False


def test_sans_cerveau_regle_la_conversation_est_refusee_sans_rien_depenser(monde):
    reponse = client_pour(EQUIPE).post("/builder/conversation", json={"workflow_id": AGENT, "message": "Salut"})
    assert reponse.status_code == 409 and "brain" in reponse.json()["detail"]


def test_un_agent_d_une_autre_organisation_est_un_404(monde, monkeypatch):
    monde.ajouter_agent(organization_id=8, identifiant=77)
    preparer_le_cerveau(monde, monkeypatch, CerveauFactice())
    c = client_pour(EQUIPE)
    assert c.post("/builder/conversation", json={"workflow_id": 77, "message": "x"}).status_code == 404
    for chemin in ("conversation/77", "conception/77", "fiche/77"):
        assert c.get(f"/builder/{chemin}").status_code == 404, chemin
    assert c.post("/builder/conception/77/decision", json={"approuve": True}).status_code == 404
    assert c.post("/builder/fiche/77/valider").status_code == 404


def test_la_correction_en_flux_dit_que_les_tests_ne_sont_pas_encore_la(monde, monkeypatch):
    preparer_le_cerveau(monde, monkeypatch, CerveauFactice())
    reponse = client_pour(EQUIPE).post(f"/builder/conversation/{AGENT}/corriger")
    assert [e.get("etat") or e["type"] for e in evenements(reponse)] == ["tests_non_disponibles", "fin"]


# --- les gestes humains -----------------------------------------------------------------------------------------------------


async def test_seul_l_ecran_approuve_le_document_et_renvoyer_demande_une_note(monde):
    await conception.ecrire(ORG_CLIENT, AGENT, CONCEPTION)
    c = client_pour(EQUIPE)
    assert c.post(f"/builder/conception/{AGENT}/decision", json={"approuve": False}).status_code == 422
    renvoye = c.post(f"/builder/conception/{AGENT}/decision", json={"approuve": False, "note": "Manque les urgences"}).json()
    assert renvoye["conception"]["etat"] == "renvoye" and renvoye["conception"]["note"] == "Manque les urgences"
    approuve = c.post(f"/builder/conception/{AGENT}/decision", json={"approuve": True}).json()
    assert approuve["conception"]["etat"] == "approuve" and approuve["conception"]["decide_par"] == "dograh:p1"
    assert c.get(f"/builder/conception/{AGENT}").json()["conception"]["etat"] == "approuve"


async def test_la_fiche_se_valide_par_une_personne_et_pas_avec_un_trou_ouvert(monde):
    await fiche.ecrire(ORG_CLIENT, AGENT, {"a": fiche.ChampFiche(valeur=1, source="s")}, [fiche.Trou(champ="b", question="Quoi ?")])
    c = client_pour(EQUIPE)
    assert c.post(f"/builder/fiche/{AGENT}/valider").status_code == 422
    await fiche.ecrire(ORG_CLIENT, AGENT, {"b": fiche.ChampFiche(valeur=2, source="s")})
    validee = c.post(f"/builder/fiche/{AGENT}/valider").json()["fiche"]
    assert validee["valide_par"] == "dograh:p1" and c.get(f"/builder/fiche/{AGENT}").json()["fiche"]["valide_par"]


def test_les_actions_des_deux_portes_se_listent_avec_leur_disponibilite(monde):
    actions = {a["nom"]: a for a in client_pour(AUTRE).get("/builder/actions").json()}
    assert actions["tests_rejouer"]["disponible"] is True and actions["fiche_lire"]["disponible"] is True
    assert actions["brouillon_operation"]["ecriture"] is True and actions["fiche_lire"]["ecriture"] is False


async def test_les_preferences_sont_celles_de_la_personne(monde):
    client_pour(EQUIPE).put("/builder/preferences", json={"texte": "Réponses courtes."})
    assert client_pour(EQUIPE).get("/builder/preferences").json()["texte"] == "Réponses courtes."
    assert client_pour(AUTRE).get("/builder/preferences").json()["texte"] == ""


# --- la bibliothèque : lecture pour tous, écriture et gestes humains pour l'équipe -----------------------------------------


NOUVEAU = {"slug": "qualifier", "titre": "Qualifier", "contenu": {"texte": "v1"}}


def test_toute_organisation_lit_la_bibliotheque_et_seule_l_equipe_ecrit(monde):
    equipe, autre = client_pour(EQUIPE), client_pour(AUTRE)
    assert equipe.post("/builder/bibliotheque/moules-etape", json=NOUVEAU).status_code == 201
    assert autre.post("/builder/bibliotheque/moules-etape", json={**NOUVEAU, "slug": "autre"}).status_code == 403
    assert [e["slug"] for e in autre.get("/builder/bibliotheque", params={"famille": "moules-etape"}).json()] == ["qualifier"]
    assert autre.get("/builder/bibliotheque/moules-etape/qualifier").json()["versions"][0]["contenu"] == {"texte": "v1"}
    assert len(autre.get("/builder/bibliotheque/familles").json()) >= 30
    for methode, chemin, corps in (
        ("post", "/builder/bibliotheque/moules-etape/qualifier/versions", {"contenu": {"t": 2}}),
        ("post", "/builder/bibliotheque/moules-etape/qualifier/retour", {"version": 1}),
        ("post", "/builder/bibliotheque/moules-etape/qualifier/statut", {"version": 1, "statut": "rejete", "raison": "x"}),
        ("post", "/builder/bibliotheque/import", {"famille": "regles-redaction", "slug": "g", "titre": "G", "contenu": {}, "origine": {"source": "s", "licence": "MIT", "date": "2026-10-31"}}),
        ("post", "/builder/bibliotheque/propositions", {"type": "version", "famille": "moules-etape", "slug": "q", "justification": "x", "contenu": {"t": 1}}),
        ("post", "/builder/bibliotheque/propositions/abc/accepter", {}),
        ("post", "/builder/bibliotheque/propositions/abc/refuser", {"motif": "non"}),
    ):
        assert getattr(autre, methode)(chemin, json=corps).status_code == 403, chemin


def test_versions_retour_arriere_et_statuts_par_l_ecran(monde):
    c = client_pour(EQUIPE)
    c.post("/builder/bibliotheque/moules-etape", json=NOUVEAU)
    c.post("/builder/bibliotheque/moules-etape/qualifier/versions", json={"contenu": {"texte": "v2"}, "notes": "plus court"})
    sans_banc = c.post("/builder/bibliotheque/moules-etape/qualifier/statut", json={"version": 2, "statut": "recette"})
    assert sans_banc.status_code == 422
    recette = c.post(
        "/builder/bibliotheque/moules-etape/qualifier/statut",
        json={"version": 2, "statut": "recette", "banc": {"description": "v12, 31 propres sur 39"}},
    ).json()
    assert recette["versions"][1]["statut"] == "recette" and recette["versions"][1]["banc"]["description"].startswith("v12")
    retour = c.post("/builder/bibliotheque/moules-etape/qualifier/retour", json={"version": 1}).json()
    assert [v["numero"] for v in retour["versions"]] == [1, 2, 3] and retour["version_courante"] == 3
    liste = c.get("/builder/bibliotheque", params={"statut": "candidat"}).json()
    assert [(e["slug"], e["version_courante"]) for e in liste] == [("qualifier", 3)]
    assert c.get("/builder/bibliotheque/moules-etape/absent").status_code == 404
    assert c.get("/builder/bibliotheque", params={"famille": "inconnue"}).status_code == 404


async def test_utilisee_par_n_agents_et_import_avec_comparatif_par_l_ecran(monde):
    c = client_pour(EQUIPE)
    c.post("/builder/bibliotheque/moules-etape", json=NOUVEAU)
    await service.enregistrer_utilisation("moules-etape", "qualifier", 1, ORG_CLIENT, AGENT)
    assert client_pour(EQUIPE).get("/builder/bibliotheque/moules-etape/qualifier/utilisation").json() == {
        "nombre": 1,
        "agents": [{"organisation": ORG_CLIENT, "agent": AGENT, "version": 1}],
    }
    # Revue N3 : la liste nomme les organisations et les agents d'autres clients, elle est réservée à l'équipe .mark.
    assert client_pour(AUTRE).get("/builder/bibliotheque/moules-etape/qualifier/utilisation").status_code == 403
    corps = {"famille": "regles-redaction", "slug": "guide", "titre": "Guide", "contenu": {"texte": "a"}, "origine": {"source": "https://x.test/g", "licence": "MIT", "date": "2026-10-31"}}
    premier = c.post("/builder/bibliotheque/import", json=corps).json()
    assert premier["cree"] is True and premier["element"]["versions"][0]["origine"]["licence"] == "MIT"
    deuxieme = c.post("/builder/bibliotheque/import", json={**corps, "contenu": {"texte": "b"}}).json()
    assert deuxieme["cree"] is False and deuxieme["comparatif"]["identique"] is False and "texte" in deuxieme["comparatif"]["diff"]


async def test_les_propositions_se_decident_par_l_ecran(monde):
    c = client_pour(EQUIPE)
    c.post("/builder/bibliotheque/moules-etape", json=NOUVEAU)
    creee = c.post(
        "/builder/bibliotheque/propositions",
        json={"type": "passage_recette", "famille": "moules-etape", "slug": "qualifier", "justification": "3 x 3 verts", "version": 1},
    ).json()
    assert [p["id"] for p in client_pour(AUTRE).get("/builder/bibliotheque/propositions").json()] == [creee["id"]]
    assert c.post(f"/builder/bibliotheque/propositions/{creee['id']}/accepter", json={}).status_code == 422  # sans banc
    acceptee = c.post(
        f"/builder/bibliotheque/propositions/{creee['id']}/accepter", json={"banc": {"description": "3 x 3 verts"}}
    ).json()
    assert acceptee["etat"] == "acceptee"
    assert c.get("/builder/bibliotheque/moules-etape/qualifier").json()["versions"][0]["statut"] == "recette"
    autre = c.post(
        "/builder/bibliotheque/propositions", json={"type": "rejet", "famille": "moules-etape", "slug": "qualifier", "justification": "Doublon", "version": 1}
    ).json()
    refus = c.post(f"/builder/bibliotheque/propositions/{autre['id']}/refuser", json={"motif": "Pas un doublon"}).json()
    assert refus["etat"] == "refusee" and c.get("/builder/bibliotheque/propositions").json() == []


def test_sans_organisation_de_bibliotheque_la_lecture_est_vide_et_l_ecriture_indisponible(monde, monkeypatch):
    monkeypatch.delenv("MARK_BIBLIOTHEQUE_ORGANISATION_ID")
    assert client_pour(EQUIPE).get("/builder/bibliotheque").json() == []
    assert client_pour(EQUIPE).post("/builder/bibliotheque/moules-etape", json=NOUVEAU).status_code == 503


def test_les_familles_et_le_banc_s_importent_dans_les_modeles(monde):
    # Garde le modèle de banc de l'écran aligné sur celui du service (un banc sans description est refusé).
    assert Banc(description="x").description == "x"
    assert client_pour(EQUIPE).post(
        "/builder/bibliotheque/moules-etape/qualifier/statut", json={"version": 1, "statut": "recette", "banc": {"description": ""}}
    ).status_code == 422


# --- POST /workflow/create/template ---------------------------------------------------------------------------------------


async def test_creer_a_partir_d_une_demande_ne_sort_plus_vers_le_service_heberge(monde, monkeypatch):
    monkeypatch.setattr(route_workflow, "capture_event", lambda **_: None)
    import api.services.mps_service_key_client as mps

    def interdit(*args, **kwargs):
        raise AssertionError("the hosted service must not be called")

    monkeypatch.setattr(mps.mps_service_key_client, "call_workflow_api", interdit)
    reponse = client_pour(EQUIPE).post(
        "/workflow/create/template", json={"call_type": "inbound", "use_case": "Prise de demande", "activity_description": "Un atelier."}
    )
    assert reponse.status_code == 200, reponse.text
    agent = reponse.json()
    assert agent["name"] == "Prise de demande - inbound" and agent["status"] == "active"
    assert [n["type"] for n in agent["workflow_definition"]["nodes"]] == ["startCall", "endCall"]
    cree = monde.workflows[agent["id"]]
    assert cree.organization_id == ORG_CLIENT
    notes = (await contexte.lire_contexte_agent(ORG_CLIENT, agent["id"]))["notes"]
    assert "Un atelier." in notes and "Prise de demande" in notes  # la demande devient le contexte de l'agent
    # Le squelette ne contient aucun texte de prompt inventé.
    assert all(n["data"]["prompt"] == "À définir avec le builder." for n in cree.released_definition.workflow_json["nodes"])


def test_le_sens_de_l_appel_est_toujours_controle(monde):
    reponse = client_pour(EQUIPE).post("/workflow/create/template", json={"call_type": "autre", "use_case": "x", "activity_description": "y"})
    assert reponse.status_code == 422


# --- revue R5 : la route du geste humain « Lancer l'essai » -----------------------------------------------------------------------------


def _systeme_simule(monde, monkeypatch, appels):
    from types import SimpleNamespace

    import httpx

    from api.services.builder import essai_outil
    from api.services.workflow.tools import custom_tool

    vrai = httpx.AsyncClient

    def gestionnaire(requete):
        appels.append(requete)
        return httpx.Response(200, json={"ok": True, "creneau": "10h"})

    monkeypatch.setattr(custom_tool.httpx, "AsyncClient", lambda **o: vrai(transport=httpx.MockTransport(gestionnaire), **o))
    outil = SimpleNamespace(
        name="reserver", tool_uuid="u", category="http_api",
        definition={"config": {"method": "POST", "url": "https://systeme.exemple.test/api", "timeout_ms": 1000}},
    )

    async def liste(organization_id, *a, **k):
        return [outil] if organization_id == ORG_CLIENT else []

    monkeypatch.setattr(essai_outil.db_client, "get_tools_for_organization", liste)


def test_la_route_lance_l_essai_d_un_outil_qui_ecrit_sur_un_geste_humain(monde, monkeypatch):
    appels = []
    _systeme_simule(monde, monkeypatch, appels)
    corps = {"workflow_id": AGENT, "outil": "reserver", "donnees_test": {"email": "personne1@exemple.test"}}
    reponse = client_pour(EQUIPE).post("/builder/outils/essai", json=corps)
    assert reponse.status_code == 200 and reponse.json()["branche"] is True
    assert len(appels) == 1 and appels[0].method == "POST"
    # des données qui ont l'air réelles : 422, rien n'est appelé
    mauvais = client_pour(EQUIPE).post("/builder/outils/essai", json={**corps, "donnees_test": {"email": "marie.dupont@gmail.com"}})
    assert mauvais.status_code == 422 and len(appels) == 1


def test_la_route_de_l_essai_est_cloisonnee_par_organisation(monde, monkeypatch):
    appels = []
    _systeme_simule(monde, monkeypatch, appels)
    corps = {"workflow_id": AGENT, "outil": "reserver", "donnees_test": {}}
    assert client_pour(AUTRE).post("/builder/outils/essai", json=corps).status_code == 404  # l'agent n'est pas le sien
    assert appels == []


async def test_la_liste_des_agents_d_une_recette_est_filtree_sur_l_organisation_de_la_personne(monde):
    """Revue N3 : l'équipe .mark voit tous les clients ; toute autre personne ne voit que les agents de sa propre organisation."""
    from api.routes import builder_tests

    c = client_pour(EQUIPE)
    c.post("/builder/bibliotheque/moules-etape", json=NOUVEAU)
    await service.enregistrer_utilisation("moules-etape", "qualifier", 1, ORG_CLIENT, AGENT)
    await service.enregistrer_utilisation("moules-etape", "qualifier", 1, 8, 77)  # un agent de l'organisation de AUTRE
    await service.enregistrer_utilisation("moules-etape", "qualifier", 1, 9, 88)  # un agent d'une troisième organisation

    def appeler(user):
        app = FastAPI()
        app.include_router(builder_tests.router)
        app.dependency_overrides[get_user_with_selected_organization] = lambda: user
        return TestClient(app).get("/builder/tests/recette/moules-etape/qualifier/agents")

    tous = appeler(EQUIPE).json()["agents"]
    assert {(a["organisation"], a["agent"]) for a in tous} == {(ORG_CLIENT, AGENT), (8, 77), (9, 88)}
    chez_eux = appeler(AUTRE)
    assert chez_eux.status_code == 200
    assert [(a["organisation"], a["agent"]) for a in chez_eux.json()["agents"]] == [(8, 77)]
    assert "88" not in chez_eux.text
