"""[.mark] Builder partie 2, lot M (méthodes de Cognigy, § 17) : sauvegarde avant modification, aperçu avant restauration, consigne de
suite, rendu du graphe, recettes d'agent en données.

Monde simulé (aucune base, aucun appel réel). Pour chaque pièce : éteinte ou non choisie, rien ne change.

| Test | Ce qu'il prouve |
|---|---|
| suite | ajout seulement ; un refus a son avertissement ; une suite déjà présente est gardée ; le moteur la pose |
| graphe | texte et Mermaid par le code, avec les changements en attente si on les demande |
| sauvegarde éteinte | aucune garde, aucune ligne écrite |
| sauvegarde allumée | refus tant qu'aucune sauvegarde ni refus explicite ; rien sur une lecture ni sur un agent créé ici |
| aperçu | ce qui sera perdu et retrouvé, sans rien écrire |
| recettes | liste lue en bibliothèque, défaut réglable, rejet, méthode lue par agent, agents existants, choix à la création |
"""

from __future__ import annotations

import copy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import builder as route
from api.routes import workflow as route_workflow
from api.services.auth.depends import get_user, get_user_with_selected_organization
from api.services.builder import apercu, methode, options, recettes, rendu_graphe, revue, sauvegarde, stock, suites, versement
from api.services.builder.actions.registre import Contexte, executer
from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.modele import Statut
from api.services.builder.tests_agent import publication as garde_publication
from api.services.builder.tests_agent import stockage as stockage_tests
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, ORG_MARK, graphe_depart, utilisateur

EQUIPE = utilisateur(1, ORG_CLIENT)
AUTRE = utilisateur(2, 8)


def ctx(**extras) -> Contexte:
    return Contexte(user=EQUIPE, workflow_id=AGENT, **{"conversation": {}, **extras})


def client_pour(user) -> TestClient:
    app = FastAPI()
    app.include_router(route.router)
    app.include_router(route_workflow.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: user
    app.dependency_overrides[get_user] = lambda: user
    return TestClient(app)


@pytest.fixture(autouse=True)
def _base_des_routes(monde, monkeypatch):
    monkeypatch.setattr(route, "db_client", monde)


async def allumer_la_sauvegarde():
    await options.ecrire(ORG_MARK, options.Options(sauvegarde_avant_modification=True))


async def un_brouillon_a_enregistrer():
    ops = [{"op": "modifier_prompt", "id": "1", "prompt": "nouveau"}]
    await stock.ecrire(ORG_CLIENT, f"MARK_BUILDER:{AGENT}:conception", {"statut": "approuvee", "objectif": "o", "reussite": "r"})
    return ops


# --- pièce 3 : la consigne de suite --------------------------------------------------------------------------------------------


def test_la_suite_s_ajoute_sans_rien_changer_et_une_suite_presente_est_gardee():
    resultat = {"ok": True, "noeuds": 3}
    avec = suites.ajouter("brouillon_voir", resultat, ecriture=False)
    assert {k: v for k, v in avec.items() if k != "suite"} == resultat and avec["suite"]["prochaine"]
    assert resultat == {"ok": True, "noeuds": 3}  # la copie, jamais l'original
    deja = {"ok": True, "suite": {"avertissement": "a", "prochaine": "b"}}
    assert suites.ajouter("brouillon_voir", deja, ecriture=False) is deja


def test_un_refus_dit_de_ne_pas_l_annoncer_comme_fait():
    refus = suites.suite_de("brouillon_operation", {"ok": False, "code": "conception"}, ecriture=True)
    assert "design document" in refus["avertissement"] and "never repeat" in refus["prochaine"]
    inconnu = suites.suite_de("x", {"ok": False}, ecriture=False)
    assert "do not announce it as done" in inconnu["avertissement"]
    assert "not available" in suites.suite_de("x", {"disponible": False, "message": "m"}, ecriture=False)["avertissement"]


async def test_le_moteur_pose_la_suite_dans_le_resultat_que_le_cerveau_recoit(monde):
    from api.services.builder import contexte as contexte_agent
    from api.services.builder import moteur
    from api.services.builder.cerveau.factice import CerveauFactice, appel, texte, tour
    from api.services.builder.cerveau.reglages import ReglagesCerveau

    cerveau = CerveauFactice(tour(appel("brouillon_voir", {})), tour(texte("fait")))
    evenements = [
        e
        async for e in moteur.tours(
            ctx(), "montre", cerveau, ReglagesCerveau(modele="m"), await contexte_agent.charger(ORG_CLIENT, AGENT), enregistrer=_rien
        )
    ]
    resultat = next(e for e in evenements if e["type"] == "resultat")
    assert resultat["resultat"]["suite"]["prochaine"].startswith("If the graph is valid")


async def _rien(*_args):
    return None


# --- pièce 4 : le rendu du graphe par le code ---------------------------------------------------------------------------------


def test_le_rendu_est_deterministe_en_texte_et_en_mermaid():
    graphe = graphe_depart()
    texte = rendu_graphe.en_texte(graphe)
    assert texte.splitlines()[0] == "2 node(s), 1 link(s)"
    assert '[1] startCall "Départ"' in texte and '`-(Fini) -> [2] endCall "Fin"' in texte
    mermaid = rendu_graphe.en_mermaid(graphe)
    assert mermaid.startswith("flowchart TD") and "n1 -->|Fini| n2" in mermaid and 'n2["endCall: Fin"]' in mermaid
    assert rendu_graphe.en_texte(graphe) == texte and rendu_graphe.en_mermaid(graphe) == mermaid
    assert rendu_graphe.en_texte(None) == "(empty graph)"


def test_un_noeud_hors_du_depart_et_un_cycle_ne_font_pas_boucler_le_rendu():
    graphe = graphe_depart()
    graphe["edges"].append({"id": "2-1", "source": "2", "target": "1", "data": {"label": "Retour"}})
    graphe["nodes"] += [{"id": "8", "type": "agentNode", "data": {"name": "Huit"}}, {"id": "9", "type": "agentNode", "data": {"name": "Neuf"}}]
    graphe["edges"] += [{"id": "8-9", "source": "8", "target": "9"}, {"id": "9-8", "source": "9", "target": "8"}]
    texte = rendu_graphe.en_texte(graphe)
    assert "(see above)" in texte and "Not reachable from the start" in texte and '[9] agentNode "Neuf"' in texte


async def test_l_action_montre_le_graphe_et_les_changements_en_attente_si_on_le_demande(monde):
    sans = await executer("agent_montrer_le_graphe", {}, ctx())
    assert sans["ok"] and "Départ" in sans["texte"] and sans["mermaid"].startswith("flowchart")
    from api.services.builder import brouillon

    await brouillon.ecrire_en_attente(
        ORG_CLIENT, AGENT, {"operations": [{"op": "ajouter_noeud", "id": "3", "type": "agentNode", "nom": "Nouveau"}], "base_version": 1}
    )
    assert "Nouveau" not in (await executer("agent_montrer_le_graphe", {"format": "texte"}, ctx()))["texte"]
    avec = await executer("agent_montrer_le_graphe", {"format": "texte", "avec_les_changements_en_attente": True}, ctx())
    assert "Nouveau" in avec["texte"] and "mermaid" not in avec


# --- pièce 1 : la sauvegarde avant la première modification --------------------------------------------------------------------


async def test_sauvegarde_eteinte_rien_ne_change(monde):
    await un_brouillon_a_enregistrer()
    resultat = await executer("brouillon_enregistrer", {}, ctx())
    assert resultat.get("code") != "sauvegarde_requise"
    assert await sauvegarde.etat(ORG_CLIENT, AGENT) is None  # aucune ligne écrite
    assert not [c for (o, c) in monde.configs if c.startswith("MARK_BUILDER_OPTIONS")]  # l'option elle-même n'a même pas été écrite


async def test_sauvegarde_allumee_refuse_la_premiere_modification_puis_laisse_passer(monde):
    await allumer_la_sauvegarde()
    refus = await executer("brouillon_enregistrer", {}, ctx())
    assert refus["ok"] is False and refus["code"] == "sauvegarde_requise" and "NOTHING WAS CHANGED" in refus["erreur"]
    # N1 : en « Demander », un réglage pose d'abord une carte ; sur « Tout permettre sur cet agent », c'est la sauvegarde qui refuse.
    refus_reglage = await executer("reglages_regler", {"valeurs": {"relecture_des_numeros": True}}, ctx(conversation={"mode": "agent"}))
    assert refus_reglage["code"] == "sauvegarde_requise"
    pris = await executer("sauvegarde_prendre", {}, ctx())
    assert pris["ok"] and pris["instantane"] == 1
    assert (await sauvegarde.etat(ORG_CLIENT, AGENT))["etat"] == "faite"
    suivant = await executer("brouillon_enregistrer", {}, ctx())
    assert suivant.get("code") != "sauvegarde_requise"
    instantanes = await revue.instantanes(ORG_CLIENT, AGENT, complets=True)
    assert instantanes[0]["cause"] == "sauvegarde du builder" and instantanes[0]["avant"]["nodes"]  # « Revenir avant » peut la restaurer


async def test_une_lecture_et_un_agent_cree_ici_ne_sont_pas_retenus(monde):
    await allumer_la_sauvegarde()
    for lecture, arguments in (("brouillon_voir", {}), ("reglages_lire", {}), ("agent_montrer_le_graphe", {}), ("tests_lister", {})):
        assert (await executer(lecture, arguments, ctx())).get("code") != "sauvegarde_requise", lecture
    await sauvegarde.apres_creation(ctx(), {"ok": True, "workflow_id": 55})
    assert (await sauvegarde.etat(ORG_CLIENT, 55))["etat"] == "cree_ici"
    monde.ajouter_agent(ORG_CLIENT, 55)
    assert (await executer("reglages_regler", {"workflow_id": 55, "valeurs": {"relecture_des_numeros": True}}, ctx())).get("code") != "sauvegarde_requise"


async def test_un_refus_explicite_de_la_personne_leve_la_garde_et_garde_sa_raison(monde):
    await allumer_la_sauvegarde()
    sans_accord = await executer("sauvegarde_refuser", {"raison": "x", "la_personne_a_dit_non": False}, ctx())
    assert sans_accord["ok"] is False  # « Only true if the person explicitly said no » : False est refusé
    ok = await executer("sauvegarde_refuser", {"raison": "Elle ne veut pas.", "la_personne_a_dit_non": True}, ctx())
    assert ok["ok"] and (await sauvegarde.etat(ORG_CLIENT, AGENT))["etat"] == "refusee"
    assert (await executer("reglages_regler", {"valeurs": {"relecture_des_numeros": True}}, ctx())).get("code") != "sauvegarde_requise"


# --- pièce 2 : l'aperçu avant de revenir -------------------------------------------------------------------------------------


def test_comparer_dit_ce_qui_sera_perdu_et_ce_qui_sera_retrouve():
    cible = graphe_depart()
    actuel = copy.deepcopy(cible)
    actuel["nodes"][0]["data"]["prompt"] = "autre"
    actuel["nodes"].append({"id": "3", "type": "agentNode", "data": {"name": "Ajouté"}})
    actuel["edges"].append({"id": "1-3", "source": "1", "target": "3", "data": {"label": "x"}})
    del actuel["nodes"][1]
    comparaison = apercu.comparer(actuel, cible)
    perdus = {(p["genre"], p["cible"]) for p in comparaison["sera_perdu"]}
    assert perdus == {("node_changed", "1"), ("node_added", "3"), ("link_added", "1-3")}
    assert [p["champs"] for p in comparaison["sera_perdu"] if p["genre"] == "node_changed"] == [["prompt"]]
    assert {(r["genre"], r["cible"]) for r in comparaison["sera_retrouve"]} == {("node_removed", "2")}
    assert apercu.comparer(cible, cible)["total_perdu"] == 0
    # V4 : le genre d'une ligne est un identifiant neutre, jamais une phrase française.
    tous = {l["genre"] for l in comparaison["sera_perdu"] + comparaison["sera_retrouve"]}
    assert tous <= set(apercu.GENRES) and all(" " not in g for g in tous)


async def test_la_route_d_apercu_n_ecrit_rien_et_un_autre_client_a_un_404(monde):
    pris = await executer("sauvegarde_prendre", {}, ctx())
    avant = dict(monde.configs)
    c = client_pour(EQUIPE)
    reponse = c.get(f"/builder/agents/{AGENT}/versions/{pris['instantane']}/apercu")
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["numero"] == pris["instantane"] and corps["total_perdu"] == 0 and corps["inchanges"] == 2
    assert monde.configs == avant and AGENT not in monde.brouillons  # lecture seule
    assert c.get(f"/builder/agents/{AGENT}/versions/99/apercu").status_code == 404
    assert client_pour(AUTRE).get(f"/builder/agents/{AGENT}/versions/1/apercu").status_code == 404


# --- pièce 7 : les recettes d'agent en données --------------------------------------------------------------------------------


def fiche_de_recette(nom, **extras):
    base = {"nom": nom, "quand": "q", "methode_de_construction": f"Construire avec {nom}.", "pieces": [], "tests": [], "capacites": []}
    return {**base, **extras}


async def avec_les_deux_premieres(monde):
    rapport = await versement.verser()
    assert rapport.erreurs == []
    return rapport


async def test_les_deux_premieres_fiches_reprennent_les_deux_recettes_actuelles(monde):
    await avec_les_deux_premieres(monde)
    liste = await recettes.lister()
    assert sorted(r.slug for r in liste) == ["facon-polyai", "facon-tala"]
    tala = await recettes.lire("facon-tala")
    polyai = await recettes.lire("facon-polyai")
    assert tala.fiche.defaut_de_depart and tala.fiche.capacites == []
    assert recettes.CAPACITE_REGLE_DE_DESCENTE in polyai.fiche.capacites
    # Lot L8 (SA-T1) : la recette façon Tala d'Evan remplace celle du fork (10 pièces d'avant, 38 ajoutées).
    assert len(tala.fiche.pieces) == 48 and len(polyai.fiche.pieces) == 10
    # Chaque pièce citée existe vraiment dans la bibliothèque versée.
    rendu = await recettes.lire_avec_les_pieces("facon-tala")
    assert not [p for p in rendu["pieces"] if p.get("manque")]


async def test_les_deux_recettes_versees_se_decrivent_dans_les_deux_langues(monde):
    # V4 : la description d'une recette est une donnée versée, en français ET en anglais (jamais le français seul à l'écran).
    await avec_les_deux_premieres(monde)
    c = client_pour(EQUIPE)
    vues = {r["slug"]: r for r in c.get("/builder/recettes").json()["recettes"]}
    assert sorted(vues) == ["facon-polyai", "facon-tala"]
    for vue in vues.values():
        assert vue["quand"] and vue["quand_en"] and vue["quand_en"] != vue["quand"]
        assert "é" not in vue["quand_en"]  # une phrase anglaise, pas le français recopié


async def test_une_recette_ajoutee_en_bibliotheque_seule_apparait_et_sert_a_construire(monde):
    await service.creer("moules-etape", "perso-accueil", "Accueil perso", {"texte": "Moule perso."}, "t")
    await service.creer(
        "recettes-agent",
        "ma-recette",
        "Ma recette",
        fiche_de_recette("Ma recette", pieces=[{"famille": "moules-etape", "slug": "perso-accueil", "role": "l'accueil"}], capacites=["x"]),
        "t",
    )
    assert [r.slug for r in await recettes.lister()] == ["ma-recette"]
    c = client_pour(EQUIPE)
    assert [r["slug"] for r in c.get("/builder/recettes").json()["recettes"]] == ["ma-recette"]
    cree = c.post(
        "/workflow/create/template", json={"call_type": "inbound", "use_case": "Cas", "activity_description": "d", "recette": "ma-recette"}
    )
    assert cree.status_code == 200, cree.text
    identifiant = cree.json()["id"]
    assert await recettes.choisie_de_l_agent(ORG_CLIENT, identifiant) == "ma-recette"
    systeme = await methode.systeme_complet(1, identifiant, ORG_CLIENT)
    assert "Construire avec Ma recette." in systeme and "moules-etape/perso-accueil" in systeme and "pas prouvée" in systeme
    lue = await executer("recette_lire", {"workflow_id": identifiant}, ctx())
    assert lue["ok"] and lue["indiquee_sur_l_agent"] and lue["recette"]["pieces"][0]["contenu"] == {"texte": "Moule perso."}


async def test_une_recette_inconnue_est_refusee_avant_toute_creation(monde):
    await avec_les_deux_premieres(monde)
    avant = set(monde.workflows)
    reponse = client_pour(EQUIPE).post(
        "/workflow/create/template", json={"call_type": "inbound", "use_case": "Cas", "activity_description": "d", "recette": "n-existe-pas"}
    )
    assert reponse.status_code == 422 and set(monde.workflows) == avant


async def test_une_recette_rejetee_disparait_de_la_liste_sans_toucher_les_agents_qui_l_utilisent(monde):
    await avec_les_deux_premieres(monde)
    await recettes.definir(ORG_CLIENT, AGENT, "facon-polyai")
    await service.marquer("recettes-agent", "facon-polyai", 1, Statut.REJETE, "evan", raison="plus voulue")
    assert [r.slug for r in await recettes.lister()] == ["facon-tala"]
    assert [r["slug"] for r in client_pour(EQUIPE).get("/builder/recettes").json()["recettes"]] == ["facon-tala"]
    recette, indiquee = await recettes.de_l_agent(ORG_CLIENT, AGENT)
    assert recette.slug == "facon-polyai" and indiquee  # l'agent la garde, avec ses pièces
    assert recettes.CAPACITE_REGLE_DE_DESCENTE in await recettes.capacites_de_l_agent(ORG_CLIENT, AGENT)
    assert "Construction : Tu construis avec les pièces de cette recette" in await methode.systeme_complet(1, AGENT, ORG_CLIENT)
    refus = client_pour(EQUIPE).put(f"/builder/agents/{AGENT}/recette", json={"recette": "facon-polyai"})
    assert refus.status_code == 422  # on ne la choisit plus


async def test_un_agent_sans_recette_se_construit_comme_avant_avec_la_recette_de_depart(monde):
    await avec_les_deux_premieres(monde)
    systeme = await methode.systeme_complet(1, AGENT, ORG_CLIENT)
    assert "« Façon Tala » (facon-tala)" in systeme and "Aucune recette n'est indiquée sur cet agent" in systeme
    assert "Tu construis uniquement avec les pièces de cette recette (prompt général, étapes au moule, conditions de passage)" in systeme
    assert "règle de descente" not in systeme.split("## La recette de cet agent")[1].split("Pièces")[0]  # rien de PolyAI chez Tala
    # Sans organisation (appel d'avant) : le texte est celui de la méthode, rien d'ajouté.
    assert "La recette de cet agent" not in await methode.systeme_complet(1)
    # Sans aucune recette en bibliothèque : rien n'est ajouté non plus.
    monde.configs = {k: v for k, v in monde.configs.items() if "recettes-agent" not in k[1]}
    assert "La recette de cet agent" not in await methode.systeme_complet(1, AGENT, ORG_CLIENT)


async def test_le_defaut_se_regle_et_une_conversation_sans_agent_propose_le_defaut_en_le_disant(monde):
    await avec_les_deux_premieres(monde)
    assert (await recettes.par_defaut(ORG_CLIENT)).slug == "facon-tala"
    c = client_pour(EQUIPE)
    assert c.put("/builder/options", json={"recette_par_defaut": "facon-polyai"}).status_code == 200
    assert (await recettes.par_defaut(ORG_CLIENT)).slug == "facon-polyai"
    assert c.get("/builder/recettes").json()["defaut"] == "facon-polyai"
    sans_agent = await methode.systeme_complet(1, None, ORG_CLIENT)
    assert "pas encore d'agent" in sans_agent and "« Façon PolyAI » (facon-polyai)" in sans_agent and "dis-le" in sans_agent
    assert c.put("/builder/options", json={"recette_par_defaut": "inconnue"}).status_code == 422
    assert client_pour(AUTRE).put("/builder/options", json={"recette_par_defaut": ""}).status_code in (401, 403, 404)


async def test_la_recette_ne_change_plus_une_fois_l_agent_publie(monde):
    await avec_les_deux_premieres(monde)
    c = client_pour(EQUIPE)
    assert c.put(f"/builder/agents/{AGENT}/recette", json={"recette": "facon-polyai"}).json()["recette"]["slug"] == "facon-polyai"
    monde.publies = {AGENT}  # une vraie publication : une version après le squelette v1
    reponse = c.put(f"/builder/agents/{AGENT}/recette", json={"recette": "facon-tala"})
    assert reponse.status_code == 409
    lue = c.get(f"/builder/agents/{AGENT}/recette").json()
    assert lue["recette"]["slug"] == "facon-polyai" and lue["indiquee"] and lue["modifiable"] is False
    assert client_pour(AUTRE).get(f"/builder/agents/{AGENT}/recette").status_code == 404


async def test_le_versement_des_agents_existants_est_idempotent_et_ne_touche_pas_un_choix(monde):
    await avec_les_deux_premieres(monde)
    monde.ajouter_agent(ORG_CLIENT, 43)
    await recettes.definir(ORG_CLIENT, 43, "facon-polyai")
    avant_texte = await methode.systeme_complet(1, AGENT, ORG_CLIENT)
    premier = await recettes.verser_les_agents()
    assert premier["poses"] == 1 and premier["deja"] == 1
    assert await recettes.choisie_de_l_agent(ORG_CLIENT, AGENT) == "facon-tala"
    assert await recettes.choisie_de_l_agent(ORG_CLIENT, 43) == "facon-polyai"
    avant = dict(monde.configs)
    assert (await recettes.verser_les_agents()) == {"poses": 0, "deja": 2, "sans_recette": 0}
    assert monde.configs == avant
    # « Sans aucun changement de comportement » : la méthode de construction lue est la même avec ou sans la ligne posée.
    apres = await methode.systeme_complet(1, AGENT, ORG_CLIENT)
    assert "Aucune recette n'est indiquée" not in apres  # la seule différence : la recette est maintenant indiquée sur l'agent
    assert [l for l in apres.splitlines() if l.startswith("Construction :")] == [l for l in avant_texte.splitlines() if l.startswith("Construction :")]


async def test_sans_recette_en_bibliotheque_le_versement_ne_pose_rien_et_la_creation_marche_comme_avant(monde):
    assert await recettes.verser_les_agents() == {"poses": 0, "deja": 0, "sans_recette": 1}
    reponse = client_pour(EQUIPE).post("/workflow/create/template", json={"call_type": "inbound", "use_case": "Cas", "activity_description": "d"})
    assert reponse.status_code == 200
    assert await recettes.choisie_de_l_agent(ORG_CLIENT, reponse.json()["id"]) is None


def test_aucun_nom_de_recette_dans_le_code_des_gardes_et_de_la_methode():
    """Lot M (7) : ce code lit la bibliothèque et des capacités ; le nom d'une recette n'y figure pas."""
    from pathlib import Path

    racine = Path(recettes.__file__).parent
    for fichier in ("recettes.py", "methode.py", "creation.py", "actions/rapport_et_tests.py", "actions/recettes.py", "sauvegarde.py"):
        contenu = (racine / fichier).read_text(encoding="utf-8")
        assert "facon-" not in contenu and "façon Tala" not in contenu and "façon PolyAI" not in contenu, fichier
    assert "façon Tala" not in methode.texte_de_secours()


async def _un_test_joue(slug: str, quand: str, *, obligatoire: bool = False):
    await stockage_tests.ecrire(
        ORG_CLIENT, AGENT, {"slug": slug, "nom": slug, "origine": "manuel", "obligatoire": obligatoire}
    )
    await stockage_tests.ajouter_un_resultat(
        ORG_CLIENT, AGENT, slug, {"le": quand, "version": 3, "empreinte": "e", "statut": "ok", "reussis": 1, "total": 1}
    )


async def test_se6_la_recette_change_apres_publication_avec_confirmation_et_les_tests_sont_a_rejouer(monde):
    """SE-6 (A-1) : sans confirmation, 409 ; avec, la recette change et la date est notée ; changer vers la même recette ne note rien."""
    await avec_les_deux_premieres(monde)
    c = client_pour(EQUIPE)
    assert c.put(f"/builder/agents/{AGENT}/recette", json={"recette": "facon-polyai"}).status_code == 200
    monde.publies = {AGENT}
    assert c.put(f"/builder/agents/{AGENT}/recette", json={"recette": "facon-polyai", "confirmer": True}).json()["tests_a_rejouer_depuis"] is None
    assert c.put(f"/builder/agents/{AGENT}/recette", json={"recette": "facon-tala"}).status_code == 409
    assert (await recettes.choisie_de_l_agent(ORG_CLIENT, AGENT)) == "facon-polyai"
    rendu = c.put(f"/builder/agents/{AGENT}/recette", json={"recette": "facon-tala", "confirmer": True})
    assert rendu.status_code == 200 and rendu.json()["recette"]["slug"] == "facon-tala" and rendu.json()["tests_a_rejouer_depuis"]
    assert c.put(f"/builder/agents/{AGENT}/recette", json={"recette": "inconnue", "confirmer": True}).status_code == 422
    assert client_pour(AUTRE).put(f"/builder/agents/{AGENT}/recette", json={"recette": "facon-tala", "confirmer": True}).status_code == 404


async def test_se6_la_garde_de_publication_exige_les_tests_rejoues_depuis_le_changement_de_recette(monde):
    await avec_les_deux_premieres(monde)
    await _un_test_joue("facultatif", "2020-01-01T00:00:00+00:00")
    await _un_test_joue("obligatoire", "2020-01-01T00:00:00+00:00", obligatoire=True)
    # Avant tout changement de recette : un test facultatif ancien ne bloque pas (comportement d'avant).
    avant = await garde_publication.problemes_des_tests_obligatoires(ORG_CLIENT, AGENT, 3, "e")
    assert [p["slug"] for p in avant] == []
    monde.publies = {AGENT}
    assert client_pour(EQUIPE).put(f"/builder/agents/{AGENT}/recette", json={"recette": "facon-polyai", "confirmer": True}).status_code == 200
    apres = await garde_publication.problemes_des_tests_obligatoires(ORG_CLIENT, AGENT, 3, "e")
    assert sorted(p["slug"] for p in apres) == ["facultatif", "obligatoire"]
    assert all("recipe changed" in p["raison"] for p in apres)
    # Rejoués après le changement : la garde laisse passer.
    from api.services.builder.tests_agent import stockage

    for slug in ("facultatif", "obligatoire"):
        await stockage.ajouter_un_resultat(ORG_CLIENT, AGENT, slug, {"le": stockage.maintenant(), "version": 3, "empreinte": "e", "statut": "ok", "reussis": 1, "total": 1})
    assert await garde_publication.problemes_des_tests_obligatoires(ORG_CLIENT, AGENT, 3, "e") == []
