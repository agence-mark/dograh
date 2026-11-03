"""[.mark] Partie 2, U12 (lot I1, sous-lot 1) : deux sources pour chaque cerveau (Claude Code ou clé d'API), l'appelant joué par Claude Code,
le juge qui remplit « À améliorer », la lecture du fork. Monde en mémoire, aucun fournisseur, aucune dépense.

| Test | Ce qu'il prouve |
|---|---|
| au départ tout sur Claude Code | cinq briques, la valeur de production (le conftest met les autres lots sur clé) |
| basculer ne change que sa brique | une brique à la fois, nom inconnu refusé, la ligne gagne sur l'ancien réglage du rôle |
| le chat du builder sur Claude Code | 409 « Claude Code », le compteur d'appels du cerveau reste à 0 ; sur clé, la garde laisse passer |
| l'appelant sur Claude Code | aucun cerveau construit (compteur à 0), l'essai dit pourquoi |
| test_demarrer / tour / finir | un appel d'essai joué tour par tour, vérifié par le code, rangé comme un test sur clé, mis « à juger » |
| cloisonnement et source | l'appel d'une autre organisation est introuvable, sur clé les outils refusent |
| juge_ecrire | remplit « À améliorer » par l'entrée unique, rejuger remplace, verdict sans citation refusé |
| lecture du fork | le résumé de session, les exécutions, les points, la qualité sont des lectures bornées |
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.schemas.appel_simule import ReglagesAppelantSimule, RoleSimule
from api.services import modifications_live, sources_cerveaux
from api.services.builder.actions import registre
from api.services.builder.actions.registre import PORTE_MCP, Contexte
from api.services.builder.cerveau import simules
from api.services.builder.cerveau.reglages import ReglagesCerveau
from api.services.builder.tests_agent import creation, execution, stockage
from api.services.juge import a_ameliorer, file
from api.tests.mark.builder_commun import AGENT, ORG_AUTRE, ORG_CLIENT, utilisateur
from api.tests.mark.test_builder_tests_agent import EQUIPE, MoteurFactice, banc  # noqa: F401 -- la fixture `banc`


@pytest.fixture(autouse=True)
def valeur_de_production(monkeypatch):
    """La vraie valeur par défaut (le conftest des tests la met sur clé pour les autres lots), et pas d'écriture en direct."""
    monkeypatch.setattr(sources_cerveaux, "DEFAUT", "claude_code")
    monkeypatch.setattr(modifications_live, "noter", AsyncMock(return_value=None))


def mcp(user_id=1, organisation=ORG_CLIENT) -> Contexte:
    return Contexte(user=utilisateur(user_id, organisation), workflow_id=AGENT, porte=PORTE_MCP)


# --- les sources -----------------------------------------------------------------------------------------------------


async def test_au_depart_tout_est_sur_claude_code(monde):
    assert await sources_cerveaux.toutes(1, ORG_CLIENT) == {b: "claude_code" for b in sources_cerveaux.BRIQUES}
    assert sources_cerveaux.BRIQUES == ("builder", "appelant", "juge_tests", "juge_appels", "analyse")


async def test_basculer_une_brique_ne_change_que_celle_la(monde):
    await sources_cerveaux.regler(ORG_CLIENT, "juge_appels", "cle_api")
    vues = await sources_cerveaux.toutes(1, ORG_CLIENT)
    assert vues["juge_appels"] == "cle_api"
    assert all(vues[b] == "claude_code" for b in vues if b != "juge_appels")
    with pytest.raises(sources_cerveaux.SourceInconnue):
        await sources_cerveaux.regler(ORG_CLIENT, "inconnue", "cle_api")
    with pytest.raises(sources_cerveaux.SourceInconnue):
        await sources_cerveaux.regler(ORG_CLIENT, "appelant", "autre")


async def test_la_ligne_gagne_sur_l_ancien_reglage_du_role(monde, monkeypatch):
    monkeypatch.setattr(sources_cerveaux, "DEFAUT", "cle_api")  # sans ligne, un rôle qui dit « claude_code » reste respecté
    assert await sources_cerveaux.source_de(ORG_CLIENT, "juge_tests", "claude_code") == "claude_code"
    assert await sources_cerveaux.source_de(ORG_CLIENT, "juge_tests", "cle_api") == "cle_api"
    await sources_cerveaux.regler(ORG_CLIENT, "juge_tests", "cle_api")
    assert await sources_cerveaux.source_de(ORG_CLIENT, "juge_tests", "claude_code") == "cle_api"


async def test_les_roles_relus_portent_la_source_effective_et_l_ecran_la_range_dans_la_ligne(monde):
    roles = ReglagesAppelantSimule(appelant=RoleSimule(consigne="c", source="cle_api"), juge=RoleSimule(consigne="j", source="cle_api"))
    vus = await sources_cerveaux.surcharger_les_roles(ORG_CLIENT, roles)
    assert (vus.appelant.source, vus.juge.source) == ("claude_code", "claude_code")
    await sources_cerveaux.ecrire_depuis_les_roles(ORG_CLIENT, roles)
    ranges = await sources_cerveaux.toutes(1, ORG_CLIENT)
    assert (ranges["appelant"], ranges["juge_tests"], ranges["juge_appels"]) == ("cle_api", "cle_api", "cle_api")
    assert ranges["builder"] == "claude_code"


# --- le chat du builder sur Claude Code : fermé, aucun fournisseur appelé -----------------------------------------------


async def test_le_chat_du_builder_sur_claude_code_est_ferme_et_n_appelle_aucun_fournisseur(monde, monkeypatch):
    from api.routes import builder as routes_builder

    appels = []
    monkeypatch.setattr(routes_builder, "fabriquer_le_cerveau", lambda *a, **k: appels.append(1))
    with pytest.raises(HTTPException) as refus:
        await routes_builder._cerveau_de(utilisateur(1, 1))
    assert refus.value.status_code == 409 and "Claude Code" in refus.value.detail
    assert appels == []
    # sur clé d'API la garde laisse passer : c'est alors l'absence de clé qui parle
    await sources_cerveaux.regler(1, "builder", "cle_api")
    with pytest.raises(HTTPException) as sans_cle:
        await routes_builder._cerveau_de(utilisateur(1, 1))
    assert "Claude Code" not in sans_cle.value.detail and appels == []


# --- l'appelant simulé sur Claude Code : aucun cerveau --------------------------------------------------------------------


async def _reglages_des_roles(monkeypatch, **plus):
    from api.services.appel_simule import reglages as appel_simule
    from api.services.builder.cerveau import reglages as reglages_cerveau

    roles = ReglagesAppelantSimule(
        appelant=RoleSimule(consigne="c", modele="mistral/appelant-m", identifiant="k1"),
        juge=RoleSimule(consigne="j", modele="openai/juge-m", identifiant="k2"),
    )
    monkeypatch.setattr(appel_simule, "lire_reglages", AsyncMock(return_value=roles))
    monkeypatch.setattr(reglages_cerveau, "lire", AsyncMock(return_value=ReglagesCerveau(modele="builder-m")))
    monkeypatch.setattr(reglages_cerveau, "organisation_des_reglages", AsyncMock(return_value=1))
    monkeypatch.setattr(execution, "_modele_de_l_agent", AsyncMock(return_value="agent-m"))


async def test_l_appelant_et_le_juge_sur_claude_code_ne_construisent_aucun_cerveau(banc, monkeypatch):
    await _reglages_des_roles(monkeypatch)
    construits = []
    monkeypatch.setattr(simules, "fabriquer", lambda *a, **k: construits.append(1))
    await creation.creer(ORG_CLIENT, AGENT, nom="Libre", scenario="Prendre un rendez-vous.", criteres=[{"type": "appel_clos_par_l_agent"}], questions_juge=["Le ton est-il naturel ?"])
    agent = SimpleNamespace(id=AGENT, user_id=1, organization_id=ORG_CLIENT, workflow_configurations={})
    r = await execution.rejouer_la_suite(EQUIPE.user, agent, repetitions=1)
    assert construits == []  # le compteur d'appels : aucun cerveau construit, donc aucun appel à un fournisseur
    essai = r["resultats"][0]["essais"][0]
    assert essai["reussi"] is False and "Claude Code" in essai["erreur"]
    assert r["resultats"][0]["juge"] is None  # rien à juger : l'appelant n'a pas joué


# --- test_demarrer / test_tour / test_finir ---------------------------------------------------------------------------------


async def _un_test_libre():
    await creation.creer(ORG_CLIENT, AGENT, nom="Libre", scenario="Prendre un rendez-vous.", criteres=[{"type": "appel_clos_par_l_agent"}], questions_juge=["Le ton est-il naturel ?"])


async def test_claude_code_joue_l_appelant_tour_par_tour_et_le_code_verifie(banc, monkeypatch):
    await _un_test_libre()
    moteur = MoteurFactice(["Bonjour, je vous écoute.", "Noté, au revoir."], fin_au_tour=1)
    execution.DEPENDANCES.moteur = moteur.en_moteur
    ouvert = await registre.executer("test_demarrer", {"workflow_id": AGENT, "test": "libre"}, mcp())
    assert ouvert["ok"] and ouvert["agent_dit"] == "Bonjour, je vous écoute." and ouvert["personnage"] and ouvert["termine"] is False
    tour = await registre.executer("test_tour", {"appel": ouvert["appel"], "replique": "Un rendez-vous mardi, merci, au revoir."}, mcp())
    assert tour["ok"] and tour["agent_dit"] == "Noté, au revoir." and tour["termine"] is True
    # l'appel est fini : une réplique de plus est refusée
    apres = await registre.executer("test_tour", {"appel": ouvert["appel"], "replique": "Allô ?"}, mcp())
    assert apres["ok"] is False and apres["code"] == "appel_termine"
    fin = await registre.executer("test_finir", {"appel": ouvert["appel"]}, mcp())
    assert fin["ok"] and fin["reussi"] is True and fin["statut"] == "ok" and fin["a_juger"] is True
    # rangé comme un test joué sur clé : mêmes exécutions, et le test attend dans « À juger »
    derniere = await stockage.derniere_execution(ORG_CLIENT, AGENT, "libre")
    assert derniere["statut"] == "ok" and derniere["essais"][0]["joue_par"] == "claude_code" and derniere["essais"][0]["lignes"]
    assert any(i["type"] == "test" and i["test"] == "libre" for i in await file.lister(ORG_CLIENT))
    assert moteur.clos is True
    # et l'appel n'existe plus
    encore = await registre.executer("test_finir", {"appel": ouvert["appel"]}, mcp())
    assert encore["ok"] is False and encore["code"] == "introuvable"


async def test_un_appel_d_essai_continue_dans_un_autre_processus_ou_apres_un_redemarrage(banc, monkeypatch):
    from api.services.builder import actions as _actions  # noqa: F401
    from api.services.builder.actions import appelant_claude_code as outils
    from api.services.builder.tests_agent import jeu

    await _un_test_libre()
    moteur = MoteurFactice(["Bonjour.", "Noté, au revoir."], fin_au_tour=1)
    execution.DEPENDANCES.moteur = moteur.en_moteur
    ouvert = await registre.executer("test_demarrer", {"workflow_id": AGENT, "test": "libre"}, mcp())
    outils._SESSIONS.clear()  # un autre worker, ou le serveur redémarré : plus rien en mémoire, tout est en base
    relues = []

    async def reouvrir(contexte, appel, ligne, workflow):
        relues.append((contexte.organisation_id, appel, ligne["test"]))
        return jeu.Session(appel, set(ligne["fins"]))

    monkeypatch.setattr(outils, "_reouvrir", reouvrir)
    tour = await registre.executer("test_tour", {"appel": ouvert["appel"], "replique": "Au revoir."}, mcp())
    assert tour["ok"] and tour["tour"] == 1 and relues == [(ORG_CLIENT, ouvert["appel"], "libre")]
    outils._SESSIONS.clear()
    fin = await registre.executer("test_finir", {"appel": ouvert["appel"]}, mcp())
    assert fin["ok"] and fin["reussi"] is True
    # un appel fini n existe plus nulle part (ni en mémoire ni en base)
    outils._SESSIONS.clear()
    assert (await registre.executer("test_tour", {"appel": ouvert["appel"], "replique": "x"}, mcp()))["code"] == "introuvable"


async def test_l_appel_d_une_autre_organisation_est_introuvable_et_sur_cle_les_outils_refusent(banc, monkeypatch):
    await _un_test_libre()
    execution.DEPENDANCES.moteur = MoteurFactice(["Bonjour.", "Au revoir."], fin_au_tour=1).en_moteur
    ouvert = await registre.executer("test_demarrer", {"workflow_id": AGENT, "test": "libre"}, mcp())
    vole = await registre.executer("test_tour", {"appel": ouvert["appel"], "replique": "x"}, mcp(2, ORG_AUTRE))
    assert vole["ok"] is False and vole["code"] == "introuvable"
    await sources_cerveaux.regler(ORG_CLIENT, "appelant", "cle_api")
    refuse = await registre.executer("test_demarrer", {"workflow_id": AGENT, "test": "libre"}, mcp())
    assert refuse["ok"] is False and refuse["code"] == "source_cle_api"


async def test_un_test_en_une_replique_n_a_pas_d_appelant_a_jouer(banc):
    await creation.creer(ORG_CLIENT, AGENT, nom="Une phrase", replique="Bonjour", criteres=[{"type": "texte_absent", "texte": "outil_interne"}])
    refus = await registre.executer("test_demarrer", {"workflow_id": AGENT, "test": "une-phrase"}, mcp())
    assert refus["ok"] is False and "single reply" in refus["erreur"]


# --- le juge remplit « À améliorer » -----------------------------------------------------------------------------------------

ITEM = {
    "id": "test-42-libre",
    "type": "test",
    "workflow_id": AGENT,
    "test": "libre",
    "criteres": ["Le ton est-il naturel ?"],
    "lignes": [["agent", "Bonjour monsieur"], ["moi", "salut"]],
}


def verdict(v, preuve="Bonjour monsieur"):
    return {"critere": "Le ton est-il naturel ?", "verdict": v, "replique": 1, "preuve": preuve, "confiance": 0.8}


async def test_juge_ecrire_remplit_a_ameliorer_par_l_entree_unique_et_rejuger_remplace(monde):
    await file.ajouter(ORG_CLIENT, ITEM)
    rate = await registre.executer("juge_ecrire", {"id": ITEM["id"], "verdicts": [verdict("rate")]}, mcp())
    assert rate["ok"] and rate["reussi"] is False and rate["a_ameliorer"] == 1
    points = await a_ameliorer.lister(ORG_CLIENT, AGENT)
    assert [(p["critere"], p["verdict"], p["replique"], p["source"]) for p in points] == [("Le ton est-il naturel ?", "rate", 1, "claude_code")]
    await file.ajouter(ORG_CLIENT, ITEM)
    bon = await registre.executer("juge_ecrire", {"id": ITEM["id"], "verdicts": [verdict("reussi")]}, mcp())
    assert bon["ok"] and bon["a_ameliorer"] == 0 and await a_ameliorer.lister(ORG_CLIENT) == []


async def test_un_verdict_sans_replique_citee_est_refuse_et_rien_n_est_range(monde):
    await file.ajouter(ORG_CLIENT, ITEM)
    sans = {"critere": "Le ton est-il naturel ?", "verdict": "rate", "preuve": "Bonjour monsieur", "confiance": 0.5}
    refus = await registre.executer("juge_ecrire", {"id": ITEM["id"], "verdicts": [sans]}, mcp())
    assert refus["ok"] is False and refus["code"] == "verdict_refuse"
    assert await a_ameliorer.lister(ORG_CLIENT) == [] and await file.trouver(ORG_CLIENT, ITEM["id"]) is not None


# --- lire le fork ----------------------------------------------------------------------------------------------------------


async def test_le_resume_de_session_compte_ce_qui_a_change(monde, monkeypatch):
    monkeypatch.setattr("api.services.builder.actions.lecture_fork.db_client", SimpleNamespace(lister_fils=AsyncMock(return_value=[])))
    await file.ajouter(ORG_CLIENT, ITEM)
    await a_ameliorer.signaler(ORG_CLIENT, ITEM, [verdict("rate")], "claude_code")
    await stockage.ajouter_un_resultat(ORG_CLIENT, AGENT, "libre", {"le": "2026-11-03T10:00:00+00:00", "statut": "echec", "reussis": 0, "total": 3, "essais": []})
    r = await registre.executer("fork_resume", {"depuis": "2020-01-01T00:00:00+00:00"}, mcp())
    assert r["ok"] and r["a_ameliorer"]["nouveaux"] == 1 and r["tests_en_echec"]["total"] == 1 and r["appels_a_juger"]["total"] == 1
    neuf = await registre.executer("fork_resume", {"depuis": "2999-01-01T00:00:00+00:00"}, mcp())
    assert neuf["a_ameliorer"]["nouveaux"] == 0
    mauvaise = await registre.executer("fork_resume", {"depuis": "hier"}, mcp())
    assert mauvaise["ok"] is False and mauvaise["code"] == "date_invalide"


async def test_les_executions_et_les_points_se_lisent_avec_l_organisation_de_la_personne(banc):
    await _un_test_libre()
    for statut in ("echec", "ok"):
        await stockage.ajouter_un_resultat(ORG_CLIENT, AGENT, "libre", {"le": "2026-11-03T10:00:00+00:00", "version": 2, "statut": statut, "reussis": 1, "total": 1, "essais": []})
    r = await registre.executer("executions_lister", {"workflow_id": AGENT}, mcp())
    assert r["ok"] and [e["statut"] for e in r["executions"]] == ["ok", "echec"] and r["en_echec"] == []
    # un agent d'une autre organisation est introuvable
    autre = await registre.executer("executions_lister", {"workflow_id": AGENT}, mcp(2, ORG_AUTRE))
    assert autre["ok"] is False
    inconnu = await registre.executer("chat_etat", {"fil_id": 999999}, mcp())
    assert inconnu["ok"] is False
