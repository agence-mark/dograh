"""[.mark] Builder partie 2, U7 (sous-lot 2) : le MCP de la bibliothèque, les deux recettes et les scénarios types versés.

| Test | Ce qu'il prouve |
|---|---|
| versement | tout le contenu du dépôt entre sans erreur dans la bibliothèque locale (donc conforme au schéma de sa famille), en Candidat, une seule fois |
| deux recettes | façon Tala et façon PolyAI sont rangées chacune dans son sous-dossier, avec sa seule étiquette, et ne se mélangent pas |
| personnages | les 18 comportements et les 6 personnages ont description, but, fin et comportements ; les scénarios n'en citent aucun d'absent |
| scénarios | ils gardent leur origine et leur licence ; leurs critères sont valides |
| deux portes | la méthode et les conventions rendues à Claude Code (MCP) sont celles de l'écran ; le guide de rédaction rend nos règles AVANT celles de l'amont |
| copie d'un scénario | ce qui manque à l'agent est signalé AVANT la copie ; rien n'est copié sans « copier quand même » |
| rangement au versement | le sous-dossier posé par le versement n'est jamais refait contre une personne |
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.mcp_server import server as serveur_mcp
from api.mcp_server.tools import voice_prompting_guide as guide
from api.routes import builder as route
from api.services.auth.depends import get_user, get_user_with_selected_organization
from api.services.builder import contexte, methode, versement
from api.services.builder.actions.registre import PORTE_MCP, Contexte, executer
from api.services.builder.bibliotheque import fiches, scenarios_types, service
from api.services.builder.bibliotheque.modele import Statut
from api.services.builder.tests_agent import stockage, verdict
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, utilisateur

EQUIPE = utilisateur(1, ORG_CLIENT)
MCP = Contexte(user=EQUIPE, porte=PORTE_MCP)


@pytest.fixture
async def verse(monde):
    """Tout le contenu du dépôt, versé dans la bibliothèque locale."""
    rapport = await versement.verser()
    assert rapport.erreurs == [], rapport.erreurs
    return rapport


async def tous():
    return {(r.famille, r.slug): r for r in await service.lister()}


# --- le versement -------------------------------------------------------------------------------------------------


async def test_tout_le_contenu_du_depot_entre_en_candidat_sans_erreur_et_une_seule_fois(verse):
    assert len(verse.crees) >= 60 and verse.gardes == [] and len(verse.fiches) == 34
    elements = await tous()
    assert all(r.statut is Statut.CANDIDAT for r in elements.values())  # le passage en Recette est un clic humain
    second = await versement.verser()
    assert second.crees == [] and second.mis_a_jour == [] and len(second.inchanges) == len(verse.crees) + len(verse.mis_a_jour) + len(verse.inchanges)
    for f, s in list(elements)[:10]:
        assert len((await service.lire_element(f, s)).versions) == 1


async def test_les_recettes_gardent_la_trace_de_leur_banc_dans_les_notes(verse):
    element = await service.lire_element("prompt-general", "facon-tala-telephone")
    assert "274" in element.courante.notes and "288" in element.courante.notes and "30/10" in element.courante.notes


# --- les deux recettes, jamais fusionnées -------------------------------------------------------------------------


async def test_chaque_recette_a_son_sous_dossier_et_sa_seule_etiquette(verse):
    elements = await tous()
    tala = {k: r for k, r in elements.items() if k[1].startswith("facon-tala")}
    polyai = {k: r for k, r in elements.items() if k[1].startswith("facon-polyai")}
    assert len(tala) >= 10 and len(polyai) >= 10
    assert all(r.dossier == "facon-tala" and r.etiquettes == ["facon-tala"] for r in tala.values())
    assert all(r.dossier == "facon-polyai" and r.etiquettes == ["facon-polyai"] for r in polyai.values())
    # Aucun élément hors de ces slugs ne porte l'étiquette d'une recette.
    autres = [k for k, r in elements.items() if k not in tala and k not in polyai and {"facon-tala", "facon-polyai"} & set(r.etiquettes)]
    assert autres == []


async def test_les_deux_recettes_ne_se_melangent_pas_dans_leur_contenu(verse):
    for (famille, slug), _ in (await tous()).items():
        if not slug.startswith("facon-") or famille == "recettes-agent":  # la fiche d'une recette n'est pas une pièce (lot M)
            continue
        texte = (await service.lire_element(famille, slug)).courante.contenu["texte"]
        if slug.startswith("facon-tala"):
            # Aucune pièce propre à PolyAI chez Tala : porte à deux appels, règle de descente, verdicts, outil de départ.
            for propre_a_polyai in ("confirme = oui", "règle de descente", "PAS ENCORE ENREGISTRÉ", "outil de départ"):
                assert propre_a_polyai not in texte, (slug, propre_a_polyai)
        else:
            assert "POINT D'ACTION PRINCIPAL" not in texte, slug  # le moule Tala n'est pas le prompt de tâche de PolyAI
            assert "Déclencher cette transition" not in texte, slug


async def test_la_porte_a_deux_appels_et_la_regle_de_descente_n_existent_que_chez_polyai(verse):
    elements = await tous()
    assert ("modeles-outils", "facon-polyai-porte-a-deux-appels") in elements
    assert ("regles-redaction", "facon-polyai-regle-de-descente") in elements
    assert not [k for k in elements if "descente" in k[1] and not k[1].startswith("facon-polyai")]
    porte = (await service.lire_element("modeles-outils", "facon-polyai-porte-a-deux-appels")).courante.contenu["texte"]
    for test_a_jouer in ("Aucune écriture sans `confirme = oui`", "Une correction n'est pas un oui", "ne reprend que ce qui a changé", "ne réserve JAMAIS deux fois", "plafond de tentatives", "Même résultat au clavier et au téléphone"):
        assert test_a_jouer.lower() in porte.lower(), test_a_jouer
    pieces = (await service.lire_element("modeles-outils", "facon-polyai-pieces-de-wren")).courante.contenu["texte"]
    for piece in ("Refus contrôlé", "Vérification à la volée", "Provenance", "Vérité métier", "Aveu franc", "Modification d'un rendez-vous", "Urgence tenue"):
        assert piece.lower() in pieces.lower(), piece


# --- personnages et comportements ---------------------------------------------------------------------------------


async def test_les_dix_huit_comportements_et_les_six_personnages_sont_complets(verse):
    elements = await tous()
    comportements = [k for k in elements if k[0] == "personnages-appelant" and k[1].startswith("comportement-")]
    personnages = [k for k in elements if k[0] == "personnages-appelant" and not k[1].startswith("comportement-") and k[1] != "consigne"]  # U6 : « consigne » est la consigne générale, pas un personnage
    assert len(comportements) == 18 and len(personnages) == 6
    for famille, slug in comportements + personnages:
        contenu = (await service.lire_element(famille, slug)).courante.contenu
        assert contenu["description"] and contenu["but"] and contenu["fin"] and contenu["comportements"], slug
    assert {elements[k].dossier for k in comportements} == {"comportements"} and {elements[k].dossier for k in personnages} == {"personnages"}


async def test_chaque_personnage_cite_par_un_scenario_existe(verse):
    elements = await tous()
    for (famille, slug), _ in elements.items():
        if famille != "scenarios-test":
            continue
        personnage = (await service.lire_element(famille, slug)).courante.contenu.get("personnage")
        assert ("personnages-appelant", personnage) in elements, (slug, personnage)


# --- scénarios types ----------------------------------------------------------------------------------------------


async def test_les_scenarios_gardent_leur_origine_leur_licence_et_ont_des_criteres_valides(verse):
    scenarios = [k for k in await tous() if k[0] == "scenarios-test"]
    assert len(scenarios) >= 12
    for famille, slug in scenarios:
        element = await service.lire_element(famille, slug)
        origine = element.courante.origine
        assert origine is not None and origine.licence == "MIT" and ("tau2-bench" in origine.source or "abcd" in origine.source), slug
        verdict.valider_criteres(element.courante.contenu["criteres"])
    abcd = (await service.lire_element("scenarios-test", "rdv-cas-normal")).courante.origine
    assert "ASAPP Research" in abcd.source and "2021" in abcd.source  # la mention de copyright d'ABCD est gardée


async def test_la_grille_du_juge_est_en_candidat_avec_les_six_criteres(verse):
    element = await service.lire_element("criteres-types", "grille-du-juge-v1")
    assert element.statut is Statut.CANDIDAT
    grille = element.courante.contenu["critere"]["grille"]
    assert len(grille) == 6 and grille[0].startswith("Suit le parcours")
    assert "non_verifiable" in json.dumps(element.courante.contenu["critere"]["sortie"])


# --- les deux portes du MCP ---------------------------------------------------------------------------------------


async def test_claude_code_recoit_la_meme_methode_que_l_ecran(verse):
    via_mcp = await executer("builder_methode", {}, MCP)
    assert via_mcp["ok"] and via_mcp["methode"] == await methode.charger_methode() and via_mcp["methode"].strip()
    # L'écran construit sa consigne à partir du même texte.
    assert (await methode.systeme_complet(1)).startswith(via_mcp["methode"])


async def test_les_conventions_sont_les_memes_aux_deux_portes(verse):
    await service.creer("conventions-mark", "conventions", "Conventions", {"texte": "Toujours dire la vérité des actions."}, "evan")
    via_mcp = await executer("builder_conventions", {}, MCP)
    assert via_mcp["conventions"] == await contexte.conventions() == "Toujours dire la vérité des actions."
    assert "Toujours dire la vérité des actions." in await methode.systeme_complet(1)


async def test_le_serveur_mcp_expose_la_methode_les_conventions_et_la_bibliotheque():
    for nom in ("builder_methode", "builder_conventions", "bibliotheque_lister", "bibliotheque_chercher", "bibliotheque_lire", "tests_depuis_la_bibliotheque"):
        assert await serveur_mcp.mcp.get_tool(nom) is not None, nom
    assert "builder_methode" in serveur_mcp.DOGRAH_MCP_INSTRUCTIONS and "bibliotheque_lister" in serveur_mcp.DOGRAH_MCP_INSTRUCTIONS
    # Les instructions disent de les lire AVANT de construire.
    assert serveur_mcp.DOGRAH_MCP_INSTRUCTIONS.index("builder_methode") < serveur_mcp.DOGRAH_MCP_INSTRUCTIONS.index("## Planning and workflow creation")


async def test_claude_code_lit_les_recettes_par_famille_et_leur_fiche(verse):
    familles = await executer("bibliotheque_lister", {}, MCP)
    redaction = next(f for f in familles["familles"] if f["slug"] == "regles-redaction")
    assert redaction["fiche"]["comment"]
    liste = await executer("bibliotheque_lister", {"famille": "prompt-general"}, MCP)
    assert {e["slug"] for e in liste["elements"]} == {"facon-tala-telephone", "facon-polyai-telephone"}
    assert set(liste["dossiers"]) == {"facon-tala", "facon-polyai"}
    lu = await executer("bibliotheque_lire", {"famille": "prompt-general", "slug": "facon-polyai-telephone"}, MCP)
    assert lu["statut"] == "candidat" and "not proven" in lu["avertissement"] and "Sécurité d'abord" in lu["contenu"]["texte"]


async def test_le_guide_de_redaction_rend_nos_regles_avant_celles_de_l_amont(verse, monkeypatch):
    monkeypatch.setattr(guide, "authenticate_mcp_request", AsyncMock(return_value=EQUIPE))
    rendu = await guide.get_voice_prompting_guide()
    cles = list(rendu)
    assert cles[0] == "regles_mark" and "topics" in cles[1:]  # nos règles d'abord, le guide de l'amont ensuite
    regles = {r["slug"]: r for r in rendu["regles_mark"]["regles"]}
    assert regles["facon-tala-interdits-mesures"]["recette"] == "facon-tala"
    assert regles["facon-polyai-principes"]["recette"] == "facon-polyai"
    assert "BEFORE" in rendu["regles_mark"]["lire_en_premier"]
    par_etape = await guide.get_voice_prompting_guide(stage="plan")
    assert list(par_etape)[0] == "regles_mark" and "intro" in par_etape


async def test_sans_regle_le_guide_de_l_amont_est_rendu_tel_quel(monde, monkeypatch):
    monkeypatch.setattr(guide, "authenticate_mcp_request", AsyncMock(return_value=EQUIPE))
    assert "regles_mark" not in await guide.get_voice_prompting_guide()


async def test_un_regle_rejetee_n_est_pas_rendue(verse, monkeypatch):
    monkeypatch.setattr(guide, "authenticate_mcp_request", AsyncMock(return_value=EQUIPE))
    await service.marquer("regles-redaction", "facon-polyai-principes", 1, Statut.REJETE, "evan", raison="ne tient pas au banc")
    rendu = await guide.get_voice_prompting_guide()
    assert "facon-polyai-principes" not in {r["slug"] for r in rendu["regles_mark"]["regles"]}


# --- copier un scénario type dans un agent ------------------------------------------------------------------------


async def test_ce_qui_manque_a_l_agent_est_signale_avant_la_copie_et_rien_n_est_copie(verse, monde):
    workflow = monde.workflows[AGENT]
    bilan = await scenarios_types.examiner(workflow, ORG_CLIENT, "rdv-cas-normal")
    assert {"critere": 0, "type": "outil", "manque": "reserver_creneau", "sorte": "outil"} in bilan["absents"]
    refus = await scenarios_types.copier(workflow, ORG_CLIENT, "rdv-cas-normal", "evan")
    assert refus["copie"] is False and refus["absents"]
    assert await stockage.lister(ORG_CLIENT, AGENT) == []


async def test_un_champ_et_une_issue_absents_sont_signales_aussi(verse, monde):
    workflow = monde.workflows[AGENT]
    champ = await scenarios_types.examiner(workflow, ORG_CLIENT, "capture-nom-epele")
    assert {"critere": 0, "type": "coordonnees_prises", "manque": "nom", "sorte": "champ"} in champ["absents"]
    issue = await scenarios_types.examiner(workflow, ORG_CLIENT, "urgence-prioritaire")
    assert [a["sorte"] for a in issue["absents"]] == ["issue"]
    workflow.workflow_configurations = {"fiche_champs": [{"nom": "nom"}]}
    assert not (await scenarios_types.examiner(workflow, ORG_CLIENT, "capture-nom-epele"))["absents"]


async def test_copier_quand_meme_cree_un_test_de_l_agent_avec_l_origine_du_scenario(verse, monde):
    workflow = monde.workflows[AGENT]
    rendu = await scenarios_types.copier(workflow, ORG_CLIENT, "rdv-cas-normal", "evan", copier_quand_meme=True)
    assert rendu["copie"] is True and rendu["test"]["nom"] == "Service : prise de rendez-vous, cas normal"
    (test,) = await stockage.lister(ORG_CLIENT, AGENT)
    assert test["scenario"]["personnage"] == "presse" and test["questions_juge"]
    assert "scenarios-test/rdv-cas-normal" in test["description"] and "MIT" in test["description"] and "ASAPP" in test["description"]
    assert (await service.utilisation("scenarios-test", "rdv-cas-normal"))[0]["agent"] == AGENT


async def test_un_scenario_dont_tout_existe_se_copie_directement(monde):
    await service.creer("personnages-appelant", "calme", "Calme", {"description": "Un appelant calme."}, "evan")
    await service.creer(
        "scenarios-test", "simple", "Simple", {"but": "Dire bonjour", "personnage": "calme", "criteres": [{"type": "etape", "attendue": "Fin"}]}, "evan"
    )
    rendu = await scenarios_types.copier(monde.workflows[AGENT], ORG_CLIENT, "simple", "evan")
    assert rendu["copie"] is True and rendu["absents"] == []


async def test_un_personnage_absent_de_la_bibliotheque_est_signale(monde):
    await service.creer("scenarios-test", "orphelin", "Orphelin", {"but": "x", "personnage": "inconnu", "criteres": [{"type": "etape", "attendue": "Fin"}]}, "evan")
    bilan = await scenarios_types.examiner(monde.workflows[AGENT], ORG_CLIENT, "orphelin")
    assert bilan["personnage_absent"] is True
    assert (await scenarios_types.copier(monde.workflows[AGENT], ORG_CLIENT, "orphelin", "evan"))["copie"] is False


async def test_le_builder_copie_un_scenario_par_l_action(verse, monde):
    ctx = Contexte(user=EQUIPE, workflow_id=AGENT)
    verifie = await executer("tests_depuis_la_bibliotheque", {"slug": "rdv-cas-normal", "verifier_seulement": True}, ctx)
    assert verifie["ok"] and verifie["absents"] and await stockage.lister(ORG_CLIENT, AGENT) == []
    sans = await executer("tests_depuis_la_bibliotheque", {"slug": "rdv-cas-normal"}, ctx)
    assert sans["copie"] is False
    avec = await executer("tests_depuis_la_bibliotheque", {"slug": "rdv-cas-normal", "copier_quand_meme": True}, ctx)
    assert avec["copie"] is True and len(await stockage.lister(ORG_CLIENT, AGENT)) == 1


async def test_la_route_signale_puis_copie_et_garde_l_isolation_des_organisations(verse, monde, monkeypatch):
    monkeypatch.setattr("api.db.db_client", monde)
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: EQUIPE
    app.dependency_overrides[get_user] = lambda: EQUIPE
    c = TestClient(app)
    base = "/builder/bibliotheque/scenarios-types/rdv-cas-normal"
    examen = c.post(f"{base}/examiner", json={"workflow_id": AGENT})
    assert examen.status_code == 200 and examen.json()["absents"]
    assert c.post(f"{base}/copier", json={"workflow_id": AGENT}).json()["copie"] is False
    assert c.post(f"{base}/copier", json={"workflow_id": AGENT, "copier_quand_meme": True}).json()["copie"] is True
    # Un agent d'une autre organisation est un 404, jamais un test créé chez lui.
    monde.workflows[77] = monde.workflows[AGENT].__class__(**{**vars(monde.workflows[AGENT]), "id": 77, "organization_id": 8})
    assert c.post(f"{base}/copier", json={"workflow_id": 77}).status_code == 404
    assert c.post("/builder/bibliotheque/scenarios-types/inconnu/examiner", json={"workflow_id": AGENT}).status_code == 404


# --- le rangement posé par le versement ---------------------------------------------------------------------------


def _ecrire(racine, famille, slug, contenu, **champs):
    (racine / famille).mkdir(parents=True, exist_ok=True)
    (racine / famille / f"{slug}.json").write_text(json.dumps({"titre": "T", "contenu": contenu, **champs}), encoding="utf-8")


async def test_le_versement_range_a_la_creation_et_ne_refait_jamais_le_rangement_d_une_personne(monde, tmp_path):
    from api.services.builder.bibliotheque import rangement

    _ecrire(tmp_path, "moules-etape", "a", {"texte": "1"}, dossier="recette-x", etiquettes=["x"])
    await versement.verser(tmp_path)
    element = await service.lire_element("moules-etape", "a")
    assert element.dossier == "recette-x" and element.etiquettes == ["x"]
    assert [e["nom"] for e in await rangement.etiquettes()] == ["x"]
    # Une personne le déplace et retire l'étiquette : un versement ultérieur n'y touche pas.
    await rangement.ranger("moules-etape", "a", dossier="ailleurs", etiquettes_posees=["perso"])
    _ecrire(tmp_path, "moules-etape", "a", {"texte": "2"}, dossier="recette-x", etiquettes=["x"])
    await versement.verser(tmp_path)
    element = await service.lire_element("moules-etape", "a")
    assert element.dossier == "ailleurs" and element.etiquettes == ["perso"]


async def test_les_fiches_de_depart_sont_versees_avec_le_contenu(verse):
    toutes = await fiches.toutes()
    assert len([f for f in toutes.values() if f.comment]) >= 30
