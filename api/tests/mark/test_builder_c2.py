"""[.mark] Builder partie 2, U5 (lot C2) : la revue champ par champ, les versions restaurables, le rapport de fin, l'accord de dépense,
les tests lus par le builder, la correction depuis un appel, les sous-agents, la visionneuse de fichiers.

Vraie application, vraie base de test, cerveau simulé (rien n'est dépensé, aucun fournisseur appelé).

| Test | Ce qu'il prouve |
|---|---|
| revue : un changement par champ | une opération qui touche 2 champs donne 2 changements, avec l'avant et l'après |
| revue : accepter un seul | seul ce changement entre dans le brouillon, l'autre reste en attente, un instantané est rangé |
| revue : refuser | le refus n'écrit rien dans l'agent |
| versions restaurables | chaque acceptation a son instantané ; restaurer remet le graphe d'avant (et se restaure à son tour) |
| rapport de fin | la carte sort dans le flux avec le nombre de tests réussis |
| dépense | le chat ne rejoue pas sans accord ; l'accord est consommé une fois ; la route d'accord relance le builder |
| tests lus | lister rend les 3 dernières exécutions, lire rend le test, supprimer propose sans effacer |
| garde du code | le builder ne change pas les critères d'un test existant, une personne le peut |
| correction | « retour d'outil » refusé hors recette façon PolyAI ; le bilan liste ce qu'un changement a cassé |
| sous-agents | écriture refusée, file au-delà de N, arrêt du parent, plafond, relecture, interrupteur, accord de dépense |
| visionneuse | le texte d'un fichier se lit par pages ; un fichier d'une autre organisation est un 404 |
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from api.db import db_client
from api.services import mark_evenements as evenements
from api.services.builder import brouillon, fil as service_fil, revue
from api.services.builder.actions.registre import Contexte, executer
from api.services.builder.cerveau.factice import CerveauFactice, appel, texte, tour
from api.services.builder.cerveau.reglages import ReglagesCerveau
from api.tests.mark.builder_commun import graphe_depart
from api.tests.mark.equipe_commun import (  # noqa: F401
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,
)

B = "/api/v1/builder"


@pytest.fixture(autouse=True)
def transport_en_memoire():
    ancien = evenements.utiliser_transport(evenements.TransportMemoire())
    yield
    evenements.utiliser_transport(ancien)


class _SessionEnSerie:
    """Les tests partagent UNE session de base (savepoint) : plusieurs tâches de fond ne peuvent pas y écrire en même temps. Cette
    enveloppe les range à la queue, une tâche à la fois (réentrante pour la même tâche). En production, chaque appel a sa session."""

    def __init__(self, fabrique):
        self._fabrique = fabrique
        self._verrou = asyncio.Lock()
        self._proprietaire = None
        self._profondeur = 0

    def __call__(self):
        outer = self
        contexte = self._fabrique()

        class _Ctx:
            async def __aenter__(_):
                tache = asyncio.current_task()
                if outer._proprietaire is not tache:
                    await outer._verrou.acquire()
                    outer._proprietaire = tache
                outer._profondeur += 1
                return await contexte.__aenter__()

            async def __aexit__(_, *exc):
                try:
                    return await contexte.__aexit__(*exc)
                finally:
                    outer._profondeur -= 1
                    if outer._profondeur == 0:
                        outer._proprietaire = None
                        outer._verrou.release()

        return _Ctx()


@pytest.fixture(autouse=True)
def base_en_serie(db_session):
    db_session.async_session = _SessionEnSerie(db_session.async_session)  # restauré par la fixture db_session
    yield


def donner_le_cerveau(monkeypatch, cerveau, **reglages):
    monkeypatch.setattr("api.routes.builder._cerveau_de", AsyncMock(return_value=(cerveau, ReglagesCerveau(modele="m", **reglages))))


async def decor(db, nom="a"):
    org = await creer_organisation(db, f"org-c2-{nom}")
    user, jeton = await creer_compte(db, f"c2{nom}@example.test", role="Administrateur", organisations=[org])
    agent = await db.create_workflow(f"Agent {nom}", graphe_depart(), user.id, org)
    return org, user, jeton, agent


def lire_sse(reponse) -> list[dict]:
    sorties = []
    for bloc in reponse.text.split("\n\n"):
        if bloc.startswith("id:"):
            sorties.append(json.loads(bloc.split("\n", 1)[1][len("data: ") :]))
    return sorties


async def poser_des_changements(org, agent, operations):
    workflow = await db_client.get_workflow(agent.id, organization_id=org)
    _graphe, version = await brouillon.source_courante(workflow)
    await brouillon.ecrire_en_attente(org, agent.id, {"operations": operations, "base_version": version})
    return workflow


async def fil_de(org, user, agent, titre="t"):
    return await db_client.creer_fil(org, user.id, agent.id if agent else None, titre)


def prompts(graphe):
    return {n["id"]: n["data"].get("prompt") for n in graphe["nodes"]}


# --- la revue champ par champ ------------------------------------------------------------------------------------------


async def test_une_operation_a_deux_champs_donne_deux_changements(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent = await decor(db_session, "r1")
    workflow = await poser_des_changements(org, agent, [{"op": "modifier_noeud", "id": "1", "nom": "Accueil", "prompt": "nouveau"}])
    vu = await revue.lister(org, workflow)
    assert vu["total"] == 2
    assert [(c["champ"], c["avant"], c["apres"]) for c in vu["changements"]] == [("nom", "Départ", "Accueil"), ("prompt", "p1", "nouveau")]


async def test_accepter_un_seul_changement_range_un_instantane(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent = await decor(db_session, "r2")
    await poser_des_changements(org, agent, [{"op": "modifier_noeud", "id": "1", "nom": "Accueil", "prompt": "nouveau"}])
    fil = await fil_de(org, user, agent)
    async with client_http() as c:
        r = await c.post(f"{B}/fils/{fil.id}/changements/accepter", json={"rangs": [1]}, headers=entetes(jeton, org))
        assert r.status_code == 200, r.text
        assert r.json()["acceptes"] == 1 and r.json()["restants"] == 1
        workflow = await db_client.get_workflow(agent.id, organization_id=org)
        graphe, _ = await brouillon.source_courante(workflow)
        assert prompts(graphe)["1"] == "nouveau" and graphe["nodes"][0]["data"]["name"] == "Départ"  # seul le prompt est entré
        en_attente = await revue.lister(org, workflow)
        assert [c["champ"] for c in en_attente["changements"]] == ["nom"]
        versions = (await c.get(f"{B}/agents/{agent.id}/versions", headers=entetes(jeton, org))).json()
        assert len(versions) == 1 and versions[0]["cause"] == "acceptation"
        assert (await c.get(f"{B}/fils/{fil.id}", headers=entetes(jeton, org))).json()["changements"] == 1


async def test_refuser_n_ecrit_rien_dans_l_agent(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent = await decor(db_session, "r3")
    workflow = await poser_des_changements(org, agent, [{"op": "modifier_prompt", "id": "1", "prompt": "refusé"}])
    avant, version = await brouillon.source_courante(workflow)
    fil = await fil_de(org, user, agent)
    async with client_http() as c:
        r = await c.post(f"{B}/fils/{fil.id}/changements/refuser", json={"rangs": []}, headers=entetes(jeton, org))
        assert r.status_code == 200 and r.json()["restants"] == 0
        assert (await c.post(f"{B}/fils/{fil.id}/changements/refuser", json={"rangs": []}, headers=entetes(jeton, org))).status_code == 409
    apres, version_apres = await brouillon.source_courante(await db_client.get_workflow(agent.id, organization_id=org))
    assert prompts(apres) == prompts(avant) and version_apres == version


async def test_chaque_acceptation_se_restaure(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent = await decor(db_session, "r4")
    await poser_des_changements(org, agent, [{"op": "modifier_prompt", "id": "1", "prompt": "v2"}])
    fil = await fil_de(org, user, agent)
    async with client_http() as c:
        assert (await c.post(f"{B}/fils/{fil.id}/changements/accepter", json={"rangs": []}, headers=entetes(jeton, org))).status_code == 200
        r = await c.post(f"{B}/agents/{agent.id}/versions/1/restaurer", headers=entetes(jeton, org))
        assert r.status_code == 200, r.text
        graphe, _ = await brouillon.source_courante(await db_client.get_workflow(agent.id, organization_id=org))
        assert prompts(graphe)["1"] == "p1"  # le graphe d'avant est revenu
        versions = (await c.get(f"{B}/agents/{agent.id}/versions", headers=entetes(jeton, org))).json()
        assert [v["cause"] for v in versions] == ["restauration de 1", "acceptation"]  # la restauration se restaure à son tour
        assert (await c.post(f"{B}/agents/{agent.id}/versions/99/restaurer", headers=entetes(jeton, org))).status_code == 404


async def test_les_changements_d_une_autre_organisation_sont_un_404(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent = await decor(db_session, "r5")
    org2, user2, jeton2, agent2 = await decor(db_session, "r5b")
    fil = await fil_de(org, user, agent)
    async with client_http() as c:
        assert (await c.get(f"{B}/fils/{fil.id}/changements", headers=entetes(jeton2, org2))).status_code == 404
        assert (await c.get(f"{B}/agents/{agent.id}/versions", headers=entetes(jeton2, org2))).status_code == 404


# --- le rapport de fin, la dépense --------------------------------------------------------------------------------------


async def test_le_rapport_de_fin_sort_en_carte(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "p1")
    rapport = {
        "resume": "L'agent prend les rendez-vous.",
        "tests": [{"nom": "t1", "ok": True}, {"nom": "t2", "ok": False, "pourquoi": "Dit le nom d'un outil."}],
        "phrases_a_essayer": ["Je voudrais un rendez-vous."],
        "points_ouverts": ["Numéro de transfert."],
    }
    donner_le_cerveau(monkeypatch, CerveauFactice(tour(appel("rapport_de_fin", rapport)), tour(texte("Voilà"))))
    async with client_http() as c:
        fil = (await c.post(f"{B}/fils", json={"message": "Termine", "workflow_id": agent.id}, headers=entetes(jeton, org))).json()
        await service_fil.attendre(fil["id"])
        flux = lire_sse(await c.get(f"{B}/fils/{fil['id']}/evenements", headers=entetes(jeton, org)))
    carte = next(e["carte"] for e in flux if e["type"] == "carte")
    assert carte["type"] == "rapport" and carte["reussis"] == 1 and carte["tests"][1]["pourquoi"].startswith("Dit")


async def test_le_chat_ne_rejoue_pas_sans_accord(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent = await decor(db_session, "d1")
    conv = {"depenses": {}}
    ctx = Contexte(user=user, workflow_id=agent.id, conversation=conv)
    refus = await executer("tests_rejouer", {}, ctx)
    assert refus["ok"] is False and refus["code"] == "accord_requis"
    annonce = await executer("depense_annoncer", {"motif": "Rejouer la suite 3 fois", "montant_estime": 0.4}, ctx)
    assert annonce["carte"]["statut"] == "attente" and annonce["id"] == "d1"
    # annoncée mais pas accordée : toujours refusé
    assert (await executer("tests_rejouer", {}, ctx))["code"] == "accord_requis"
    conv["depenses"]["d1"]["statut"] = "accordee"
    await executer("tests_rejouer", {}, ctx)
    assert conv["depenses"]["d1"]["utilisee"] is True  # l'accord est consommé : une seule dépense par accord
    assert (await executer("tests_rejouer", {}, ctx))["code"] == "accord_requis"
    # la personne qui agit depuis l'écran (sans conversation) n'est pas freinée
    assert (await executer("tests_rejouer", {}, Contexte(user=user, workflow_id=agent.id))).get("code") != "accord_requis"


async def test_la_route_d_accord_relance_le_builder(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "d2")
    fil = await fil_de(org, user, agent)
    await db_client.modifier_fil(
        org, fil.id, etat="terminee",
        historique={"messages": [], "depenses": {"d1": {"motif": "Rejouer", "montant_estime": 0.5, "statut": "attente", "utilisee": False}}},
    )
    cerveau = CerveauFactice(tour(texte("Je rejoue")))
    donner_le_cerveau(monkeypatch, cerveau)
    async with client_http() as c:
        r = await c.post(f"{B}/fils/{fil.id}/depenses/d1", json={"accord": True}, headers=entetes(jeton, org))
        assert r.status_code == 200 and r.json()["statut"] == "accordee"
        await service_fil.attendre(fil.id)
        assert (await c.post(f"{B}/fils/{fil.id}/depenses/d1", json={"accord": False}, headers=entetes(jeton, org))).status_code == 409
        assert (await c.post(f"{B}/fils/{fil.id}/depenses/zz", json={"accord": True}, headers=entetes(jeton, org))).status_code == 404
    relu = await db_client.lire_fil(org, fil.id)
    assert relu.historique["depenses"]["d1"]["statut"] == "accordee"
    assert "Agreed" in json.dumps(cerveau.requetes[0]["messages"])


# --- les tests lus, la garde du code -------------------------------------------------------------------------------------


async def un_test(user, agent, nom="Prise de RDV"):
    ctx = Contexte(user=user, workflow_id=agent.id)
    r = await executer("tests_creer", {"nom": nom, "replique": "Un rendez-vous.", "criteres": [{"type": "texte_present", "texte": "rendez-vous"}]}, ctx)
    assert r["ok"], r
    return r["test"]["slug"]


async def test_lister_lire_et_proposer_de_supprimer(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent = await decor(db_session, "t1")
    slug = await un_test(user, agent)
    ctx = Contexte(user=user, workflow_id=agent.id, conversation={})
    liste = await executer("tests_lister", {}, ctx)
    assert liste["total"] == 1 and liste["tests"][0]["slug"] == slug and liste["tests"][0]["executions"] == []
    lu = await executer("tests_lire", {"test": slug}, ctx)
    assert lu["test"]["criteres"][0]["type"] == "texte_present"
    assert (await executer("tests_lire", {"test": "inconnu"}, ctx))["ok"] is False
    proposition = await executer("tests_supprimer", {"test": slug}, ctx)
    assert proposition["propose"] is True and proposition["carte"]["type"] == "proposition_test"
    assert (await executer("tests_lister", {}, ctx))["total"] == 1  # rien n'a été effacé


async def test_le_builder_ne_change_pas_les_criteres_d_un_test(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent = await decor(db_session, "t2")
    slug = await un_test(user, agent)
    nouveaux = [{"type": "texte_absent", "texte": "x"}]
    builder = await executer("tests_modifier", {"test": slug, "criteres": nouveaux}, Contexte(user=user, workflow_id=agent.id, conversation={}))
    assert builder["ok"] is False and builder["code"] == "garde_du_code" and builder["carte"]["type"] == "proposition_test"
    mcp = await executer("tests_modifier", {"test": slug, "criteres": nouveaux}, Contexte(user=user, workflow_id=agent.id, porte="mcp"))
    assert mcp["code"] == "garde_du_code"
    # le nom, lui, peut changer ; et la personne (écran, sans conversation) change aussi les critères
    assert (await executer("tests_modifier", {"test": slug, "nom": "Autre nom"}, Contexte(user=user, workflow_id=agent.id, conversation={})))["ok"]
    personne = await executer("tests_modifier", {"test": slug, "criteres": nouveaux}, Contexte(user=user, workflow_id=agent.id))
    assert personne["ok"] is True


# --- corriger depuis un appel --------------------------------------------------------------------------------------------


async def test_la_descente_dans_le_retour_d_outil_est_reservee_a_la_recette_polyai(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent = await decor(db_session, "c1")
    ctx = Contexte(user=user, workflow_id=agent.id, conversation={})
    plan = {"cause": "Oublie le nom", "replique": "Bonjour.", "objet": "retour_outil", "cible": "chercher", "avant": "a", "apres": "b"}
    assert (await executer("correction_proposer", plan, ctx))["code"] == "recette"
    assert (await executer("correction_proposer", {**plan, "recette": "facon-tala"}, ctx))["ok"] is False
    bon = await executer("correction_proposer", {**plan, "recette": "facon-polyai"}, ctx)
    assert bon["ok"] and bon["carte"]["statut"] == "a_approuver"  # rien n'est écrit : la personne approuve d'abord
    assert (await executer("correction_proposer", {**plan, "objet": "etape", "apres": "a"}, ctx))["ok"] is False  # ne change rien


async def test_le_bilan_liste_ce_que_le_changement_a_casse(db_session, sans_preparation_des_organisations):
    from api.services.builder.tests_agent import stockage

    org, user, jeton, agent = await decor(db_session, "c2")
    casse, repare = await un_test(user, agent, "Casse"), await un_test(user, agent, "Repare")
    for slug, avant, apres in ((casse, "ok", "echec"), (repare, "echec", "ok")):
        await stockage.ajouter_un_resultat(org, agent.id, slug, {"le": "1", "statut": avant, "reussis": 1, "total": 1})
        await stockage.ajouter_un_resultat(org, agent.id, slug, {"le": "2", "statut": apres, "reussis": 1, "total": 1})
    bilan = await executer("correction_bilan", {}, Contexte(user=user, workflow_id=agent.id))
    assert [c["test"] for c in bilan["casses"]] == [casse] and [r["test"] for r in bilan["repares"]] == [repare]


async def test_le_builder_liste_toutes_ses_modifications_avant_et_apres(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent = await decor(db_session, "c3")
    fil = await fil_de(org, user, agent)
    for prompt in ("v2", "v3"):
        workflow = await poser_des_changements(org, agent, [{"op": "modifier_prompt", "id": "1", "prompt": prompt}])
        await revue.accepter(org, workflow, None, fil.id)
    ctx = Contexte(user=user, workflow_id=agent.id, conversation={"fil_id": fil.id})
    rendu = await executer("modifications_lister", {}, ctx)
    assert rendu["total"] == 2
    assert [(m["operations"][0]["avant"], m["operations"][0]["apres"]) for m in rendu["modifications"]] == [("p1", "v2"), ("v2", "v3")]


# --- les sous-agents -----------------------------------------------------------------------------------------------------


class CerveauDeSousAgents:
    """Le parent délègue ; un sous-agent obéit à sa tâche : « ECRIRE » tente une écriture, « BLOQUER » attend sans fin,
    « DEPENSER » coûte puis attend. Le reste rend un résultat."""

    def __init__(self, delegation=None, attente=0.0):
        self.delegation = delegation
        self.attente = attente
        self.en_meme_temps = 0
        self.maximum = 0
        self.vus: list[str] = []

    async def tour(self, *, systeme, messages, outils):
        premier = next(m["content"] for m in messages if m["role"] == "user")
        a_un_resultat = any(m["role"] == "outil" for m in messages)
        if "[Delegated task" not in premier:
            if a_un_resultat:
                yield texte("Rassemblé")
            else:
                yield appel("deleguer", self.delegation, "deleg")
        else:
            self.vus.append(premier)
            self.en_meme_temps += 1
            self.maximum = max(self.maximum, self.en_meme_temps)
            try:
                if "ECRIRE" in premier and not a_un_resultat:
                    assert "brouillon_operation" not in [o["name"] for o in outils]  # l'outil n'est même pas montré
                    yield appel("brouillon_operation", {"operations": [{"op": "modifier_prompt", "id": "1", "prompt": "x"}]}, "w")
                elif "DEPENSER" in premier and not a_un_resultat:
                    yield appel("tests_lister", {}, "l")
                    yield {"type": "usage", "entree": 1_000_000, "sortie": 0}
                elif "BLOQUER" in premier:
                    await asyncio.Event().wait()
                else:
                    if self.attente:
                        await asyncio.sleep(self.attente)
                    yield texte("Résultat de " + premier[premier.index("[Delegated task"):].splitlines()[1])
                if "DEPENSER" in premier and a_un_resultat:
                    await asyncio.Event().wait()
            finally:
                self.en_meme_temps -= 1


def deleguer(usage, *consignes, **plus):
    return {"usage": usage, "taches": [{"titre": f"T{i}", "consigne": c} for i, c in enumerate(consignes)], **plus}


async def lancer_un_chat(c, jeton, org, agent, message="Délègue"):
    return (await c.post(f"{B}/fils", json={"message": message, "workflow_id": agent.id}, headers=entetes(jeton, org))).json()


async def enfants(c, jeton, org, fil_id):
    return (await c.get(f"{B}/fils/{fil_id}/sous-agents", headers=entetes(jeton, org))).json()


async def test_un_sous_agent_n_ecrit_jamais(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "s1")
    cerveau = CerveauDeSousAgents(deleguer("analyser", "lis ECRIRE"))
    donner_le_cerveau(monkeypatch, cerveau)
    async with client_http() as c:
        fil = await lancer_un_chat(c, jeton, org, agent)
        await service_fil.attendre(fil["id"])
        vus = await enfants(c, jeton, org, fil["id"])
        assert len(vus["sous_agents"]) == 1 and vus["sous_agents"][0]["usage"] == "analyser"
        flux = lire_sse(await c.get(f"{B}/fils/{vus['sous_agents'][0]['id']}/evenements", headers=entetes(jeton, org)))
    refus = next(e for e in flux if e["type"] == "resultat")
    assert refus["ok"] is False and "never writes" in refus["resultat"]["erreur"]
    flux_parent = lire_sse(await _flux(org, jeton, fil["id"]))
    assert {e["type"] for e in flux_parent} >= {"delegation", "delegation_fin"}
    # le brouillon de l'agent n'a pas bougé
    assert (await brouillon.lire_en_attente(org, agent.id))["operations"] == []


async def _flux(org, jeton, fil_id):
    async with client_http() as c:
        return await c.get(f"{B}/fils/{fil_id}/evenements", headers=entetes(jeton, org))


async def test_au_plus_n_en_meme_temps_et_le_dernier_attend_en_file(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "s2")
    cerveau = CerveauDeSousAgents(deleguer("analyser", "a", "b", "c", "d"), attente=0.15)
    donner_le_cerveau(monkeypatch, cerveau)
    async with client_http() as c:
        assert (await c.put(f"{B}/sous-agents/reglages", json={"en_meme_temps": 3}, headers=entetes(jeton, org))).status_code == 200
        fil = await lancer_un_chat(c, jeton, org, agent)
        await service_fil.attendre(fil["id"])
        vus = await enfants(c, jeton, org, fil["id"])
    assert len(vus["sous_agents"]) == 4 and all(s["etat"] == "terminee" for s in vus["sous_agents"])
    assert cerveau.maximum == 3  # N + 1 : le quatrième a attendu qu'une place se libère
    assert {s["resume"] for s in vus["sous_agents"]} == {"Résultat de a", "Résultat de b", "Résultat de c", "Résultat de d"}


async def test_arreter_le_parent_arrete_ses_sous_agents(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "s3")
    cerveau = CerveauDeSousAgents(deleguer("analyser", "BLOQUER 1", "BLOQUER 2"))
    donner_le_cerveau(monkeypatch, cerveau)
    async with client_http() as c:
        fil = await lancer_un_chat(c, jeton, org, agent)
        for _ in range(100):
            await asyncio.sleep(0.05)
            if cerveau.en_meme_temps == 2:
                break
        assert cerveau.en_meme_temps == 2
        assert (await c.post(f"{B}/fils/{fil['id']}/arreter", headers=entetes(jeton, org))).status_code == 200
        vus = await enfants(c, jeton, org, fil["id"])
    assert [s["etat"] for s in vus["sous_agents"]] == ["arretee", "arretee"] and not any(s["en_cours"] for s in vus["sous_agents"])
    assert (await db_client.lire_fil(org, fil["id"])).etat == "arretee"


async def test_le_plafond_de_la_delegation_arrete_le_groupe(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "s4")
    cerveau = CerveauDeSousAgents(deleguer("analyser", "DEPENSER 1", "DEPENSER 2"))
    donner_le_cerveau(monkeypatch, cerveau, prix_entree_par_million=10.0, plafond_depense=100.0)
    async with client_http() as c:
        await c.put(f"{B}/sous-agents/reglages", json={"plafond_delegation": 0.5}, headers=entetes(jeton, org))
        fil = await lancer_un_chat(c, jeton, org, agent)
        await service_fil.attendre(fil["id"])
        vus = await enfants(c, jeton, org, fil["id"])
        flux = lire_sse(await c.get(f"{B}/fils/{fil['id']}/evenements", headers=entetes(jeton, org)))
    assert all(s["etat"] == "arretee" for s in vus["sous_agents"])
    assert any(e.get("code") == "plafond_delegation" for e in flux)  # dit dans le fil
    parent = await db_client.lire_fil(org, fil["id"])
    assert parent.cout >= 10.0  # la dépense des enfants est comptée dans le plafond de la conversation


async def test_la_conversation_d_un_sous_agent_se_relit_et_ne_recoit_pas_de_message(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "s5")
    donner_le_cerveau(monkeypatch, CerveauDeSousAgents(deleguer("analyser", "lis")))
    async with client_http() as c:
        fil = await lancer_un_chat(c, jeton, org, agent)
        await service_fil.attendre(fil["id"])
        enfant = (await enfants(c, jeton, org, fil["id"]))["sous_agents"][0]
        flux = lire_sse(await c.get(f"{B}/fils/{enfant['id']}/evenements", headers=entetes(jeton, org)))
        assert any(e["type"] == "texte" and "Résultat de lis" in e["texte"] for e in flux)  # rejoué depuis la table
        vue = (await c.get(f"{B}/fils/{enfant['id']}", headers=entetes(jeton, org))).json()
        assert vue["genre"] == "sous_agent" and vue["parent_id"] == fil["id"]
        for chemin in ("messages", "modifier-dernier"):
            r = await c.post(f"{B}/fils/{enfant['id']}/{chemin}", json={"message": "salut"}, headers=entetes(jeton, org))
            assert r.status_code == 409
        assert (await c.post(f"{B}/fils/{enfant['id']}/reprendre", headers=entetes(jeton, org))).status_code == 409
        listes = (await c.get(f"{B}/fils", headers=entetes(jeton, org))).json()
    assert [f["id"] for f in listes] == [fil["id"]]  # les sous-agents n'encombrent pas l'historique


async def test_l_interrupteur_eteint_le_builder_fait_tout_lui_meme(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "s6")
    cerveau = CerveauDeSousAgents(deleguer("analyser", "lis"))
    donner_le_cerveau(monkeypatch, cerveau)
    async with client_http() as c:
        fil = await db_client.creer_fil(org, user.id, agent.id, "chat")
        r = await c.put(f"{B}/fils/{fil.id}/sous-agents/interrupteur", json={"actif": False}, headers=entetes(jeton, org))
        assert r.status_code == 200 and r.json()["actif"] is False
        await c.post(f"{B}/fils/{fil.id}/messages", json={"message": "Délègue"}, headers=entetes(jeton, org))
        await service_fil.attendre(fil.id)
        assert (await enfants(c, jeton, org, fil.id))["sous_agents"] == []
    refus = next(m for m in (await db_client.lire_fil(org, fil.id)).historique["messages"] if m["role"] == "outil")
    assert "Sub-agents are off" in refus["content"] and cerveau.vus == []


async def test_tester_exige_l_accord_de_la_personne(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "s7")
    cerveau = CerveauDeSousAgents(deleguer("tester", "joue"))
    donner_le_cerveau(monkeypatch, cerveau)
    async with client_http() as c:
        fil = await lancer_un_chat(c, jeton, org, agent)
        await service_fil.attendre(fil["id"])
    refus = next(m for m in (await db_client.lire_fil(org, fil["id"])).historique["messages"] if m["role"] == "outil")
    assert "agreement" in refus["content"] and cerveau.vus == []  # rien n'a tourné sans accord


# --- la visionneuse -------------------------------------------------------------------------------------------------------


async def un_fichier(db, org, user, nom, texte_complet):
    return await db.create_document(
        organization_id=org, created_by=user.id, filename=nom, file_size_bytes=len(texte_complet), file_hash=f"h-{nom}-{org}",
        mime_type="text/plain", retrieval_mode="full_document", custom_metadata={}, docling_metadata={}, source_url=None,
    )


async def test_le_texte_d_un_fichier_se_lit_par_pages_et_reste_dans_son_organisation(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent = await decor(db_session, "f1")
    org2, user2, jeton2, agent2 = await decor(db_session, "f1b")
    document = await un_fichier(db_session, org, user, "notes.pdf", "page un\fpage deux")
    await db_session.update_document_full_text(document.id, "page un\fpage deux")
    async with client_http() as c:
        r = await c.get(f"{B}/fichiers/{document.document_uuid}/texte?page=2", headers=entetes(jeton, org))
        assert r.status_code == 200, r.text
        assert r.json() == {"nom": "notes.pdf", "type_mime": "text/plain", "genre": "pages", "page": 2, "pages": 2, "texte": "page deux"}
        assert (await c.get(f"{B}/fichiers/{document.document_uuid}/texte?page=3", headers=entetes(jeton, org))).status_code == 404
        assert (await c.get(f"{B}/fichiers/{document.document_uuid}/texte", headers=entetes(jeton2, org2))).status_code == 404
