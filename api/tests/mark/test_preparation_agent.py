"""[.mark] builder partie 2, D1 (U4, E42) : la liste de préparation d'un agent est calculée, rien n'est stocké.

| Test | Ce qu'il prouve |
|---|---|
| variables | une variable lue par un prompt et fournie par ni le modèle ni une extraction est nommée ; fournie, elle disparaît |
| briques | cerveau, transcription ou voix absents sont nommés (requis) ; temps réel : ``realtime`` suffit |
| outils | un outil porté par une étape mais absent ou archivé est nommé ; aucun outil : sans objet |
| tests | un test obligatoire non à jour rend l'étape requise ; aucun test : conseillée ; des tests à jour : faite |
| conseillées | fiche d'établissement, fiche d'appel, panne, phrases : faites seulement quand réglées |
| route | lecture par un membre, 404 pour l'agent d'une autre organisation, aucune clé dans la réponse, rien d'écrit |
"""

import json
from types import SimpleNamespace

import pytest

from api.services import preparation
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)

GRAPHE = {
    "nodes": [
        {
            "id": "1",
            "type": "startCall",
            "position": {"x": 0, "y": 0},
            "data": {
                "name": "Accueil",
                "prompt": "Bonjour {{prenom}}, ville {{ville}}",
                "is_start": True,
                "allow_interrupt": False,
                "add_global_prompt": False,
                "tool_uuids": ["outil-1"],
            },
        },
        {"id": "2", "type": "endCall", "position": {"x": 0, "y": 100}, "data": {"name": "Fin", "prompt": "Au revoir"}},
    ],
    "edges": [{"id": "e", "source": "1", "target": "2", "data": {"label": "fin", "condition": "toujours"}}],
}


def _complete(**remplacements):
    base = dict(
        definition=GRAPHE,
        variables_du_modele={"prenom": "Camille", "ville": "Lille"},
        configurations={},
        effective=SimpleNamespace(llm=1, stt=1, tts=1, realtime=None, is_realtime=False),
        outils_actifs={"outil-1"},
        fiche=None,
        tests=[],
        problemes_tests_obligatoires=[],
    )
    base.update(remplacements)
    return {e.id: e for e in preparation.calculer(**base)}


def test_les_variables_non_fournies_sont_nommees():
    assert _complete(variables_du_modele={"prenom": "Camille"})["variables"].manquants == ["ville"]
    assert _complete(variables_du_modele={"prenom": "Camille", "ville": ""})["variables"].manquants == ["ville"]
    ok = _complete()["variables"]
    assert (ok.etat, ok.niveau) == ("fait", "requis")


def test_une_variable_extraite_par_le_graphe_n_est_pas_a_remplir():
    graphe = json.loads(json.dumps(GRAPHE))
    graphe["nodes"][1]["data"]["extraction_variables"] = [{"name": "ville", "type": "string", "prompt": "la ville"}]
    assert _complete(definition=graphe, variables_du_modele={"prenom": "x"})["variables"].etat == "fait"


def test_les_briques_absentes_sont_nommees():
    etape = _complete(effective=SimpleNamespace(llm=1, stt=None, tts=None, realtime=None, is_realtime=False))["briques"]
    assert (etape.etat, etape.niveau, etape.manquants) == ("a_faire", "requis", ["stt", "tts"])
    assert _complete(effective=None)["briques"].manquants == ["llm", "stt", "tts"]
    temps_reel = SimpleNamespace(llm=None, stt=None, tts=None, realtime=object(), is_realtime=True)
    assert _complete(effective=temps_reel)["briques"].etat == "fait"


def test_les_outils_perdus_sont_nommes():
    assert _complete(outils_actifs=set())["outils"].manquants == ["outil-1"]
    assert _complete()["outils"].etat == "fait"
    sans_outil = json.loads(json.dumps(GRAPHE))
    sans_outil["nodes"][0]["data"].pop("tool_uuids")
    assert _complete(definition=sans_outil)["outils"].etat == "sans_objet"


def test_les_tests_obligatoires_rendent_l_etape_requise():
    probleme = [{"slug": "t1", "nom": "Prise de rendez-vous", "raison": "never replayed"}]
    etape = _complete(problemes_tests_obligatoires=probleme, tests=[{"slug": "t1"}])["tests"]
    assert (etape.niveau, etape.etat, etape.manquants) == ("requis", "a_faire", ["Prise de rendez-vous"])
    aucun = _complete()["tests"]
    assert (aucun.niveau, aucun.etat) == ("conseille", "a_faire")
    assert _complete(tests=[{"slug": "t1"}])["tests"].etat == "fait"


def test_les_etapes_conseillees():
    vide = _complete()
    for ident in ("etablissement", "fiche", "panne", "phrases"):
        assert (vide[ident].niveau, vide[ident].etat) == ("conseille", "a_faire"), ident
    fiche = SimpleNamespace(nom="Site nord", adresse=None, horaires_ouverture="Mo-Fr 09:00-18:00")
    pleine = _complete(
        configurations={"etablissement_id": "site-nord", "fiche_champs": [{"nom": "x"}], "panne": {"a": 1}, "phrases_regles": [{"a": 1}]},
        fiche=fiche,
    )
    for ident in ("etablissement", "fiche", "panne", "phrases"):
        assert pleine[ident].etat == "fait", ident
    # Une fiche choisie qui n'existe plus est nommée.
    perdue = _complete(configurations={"etablissement_id": "disparue"}, fiche=None)["etablissement"]
    assert perdue.etat == "a_faire" and perdue.manquants == ["disparue"]


pytestmark_route = pytest.mark.usefixtures("sans_preparation_des_organisations")


@pytest.mark.usefixtures("sans_preparation_des_organisations")
async def test_la_route_lit_sans_rien_ecrire_et_cloisonne(db_session):
    org = await creer_organisation(db_session, "prep-a")
    autre = await creer_organisation(db_session, "prep-b")
    user, jeton = await creer_compte(db_session, "prep-a@example.com", role="Membre", organisations=[org])
    autre_user, autre_jeton = await creer_compte(db_session, "prep-b@example.com", role="Administrateur", organisations=[autre])
    agent = await db_session.create_workflow(name="A", workflow_definition=GRAPHE, user_id=user.id, organization_id=org)
    async with client_http() as c:
        lu = await c.get(f"/api/v1/workflow/{agent.id}/preparation", headers=entetes(jeton, org))
        chez_l_autre = await c.get(f"/api/v1/workflow/{agent.id}/preparation", headers=entetes(autre_jeton, autre))
    assert lu.status_code == 200
    etapes = {e["id"]: e for e in lu.json()["etapes"]}
    assert set(etapes) == {"variables", "briques", "outils", "tests", "etablissement", "fiche", "panne", "phrases"}
    assert etapes["variables"]["manquants"] == ["prenom", "ville"]
    assert etapes["outils"]["manquants"] == ["outil-1"]
    assert chez_l_autre.status_code == 404
    corps = lu.text.lower()
    assert "api_key" not in corps and "sk-" not in corps
