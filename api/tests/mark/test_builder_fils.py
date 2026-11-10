"""[.mark] Builder partie 2, U5 (lot C1) : le chat en tables, en tâche de fond, rejouable ; le module d'événements ; arrêter,
reprendre, redémarrer ; la carte plan et la carte question ; les démarrages de l'accueil.

Vraie application, vraie base de test, cerveau factice (rien n'est dépensé, aucun fournisseur appelé).

| Test | Ce qu'il prouve |
|---|---|
| module : rejeu et suite | les événements après ``depuis`` sont rejoués, puis les nouveaux arrivent par le réveil, et le flux s'arrête à la fin |
| module : Redis tombé | publier ne lève jamais ; sans réveil, la table est relue (aucun événement perdu) |
| conversation en tables | ouvrir un chat écrit la ligne, le travail tourne en fond, les événements sont en table dans l'ordre |
| rechargement | relire le flux depuis 0 redonne les mêmes événements ; depuis le dernier id, rien |
| plusieurs par agent | deux conversations du même agent coexistent, la liste les rend, avec leur coût |
| cloisonnement | la conversation, l'agent et le flux d'une autre organisation sont des 404 |
| arrêter | coupe l'appel au cerveau, état « arretee », événement de fin ; le travail déjà écrit reste |
| reprendre | relance depuis le disque, l'appel orphelin est réparé, la conversation finit |
| redémarrage | une conversation « en_cours » sans tâche passe à « arretee » au démarrage, « Reprendre » la relance |
| modifier et relancer | le dernier message est retiré de l'historique du cerveau, l'écran est averti |
| plan et question | les cartes sortent dans le flux, le plan est gardé, une seule étape en cours |
| démarrages | un démarrage ajouté apparaît, un rejeté disparaît, ``{agent}`` est remplacé, l'agent manquant est refusé, le compteur monte |
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from api.db import db_client
from api.services import mark_evenements as evenements
from api.services.builder import demarrages, fil as service_fil
from api.services.builder.bibliotheque import service as bibliotheque
from api.services.builder.bibliotheque.modele import Statut
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


@pytest.fixture(autouse=True)
def sans_journal_differe_de_l_equipe(monkeypatch):
    """Clôture SA-2 : le journal de l'équipe s'écrit après la réponse, pendant que le travail de fond du chat tourne déjà. Sur la session
    unique des tests, deux écritures à la fois se heurtent (« Session is already flushing ») : sur le serveur, chacune a sa session.
    Ce fichier prouve le chat, pas le journal (``test_journal_sans_fausses_ecritures`` le prouve) : on ne le rejoue pas ici."""

    async def rien(scope, statut):
        scope.pop("mark_journal_differe", None)
        return False

    monkeypatch.setattr("api.services.equipe_mark.journal_apres_succes.ecrire_le_journal_differe", rien)


class CerveauBloque:
    """Rend un morceau de texte puis attend sans fin : le travail est « en cours » jusqu'à l'arrêt."""

    def __init__(self):
        self.commence = asyncio.Event()

    async def tour(self, *, systeme, messages, outils):
        yield texte("Je commence")
        self.commence.set()
        await asyncio.Event().wait()


def donner_le_cerveau(monkeypatch, cerveau):
    monkeypatch.setattr("api.routes.builder._cerveau_de", AsyncMock(return_value=(cerveau, ReglagesCerveau(modele="m"))))


async def decor(db, nom="a"):
    org = await creer_organisation(db, f"org-c1-{nom}")
    user, jeton = await creer_compte(db, f"c1{nom}@example.test", role="Administrateur", organisations=[org])
    agent = await db.create_workflow(f"Agent {nom}", graphe_depart(), user.id, org)
    return org, user, jeton, agent


def lire_sse(reponse) -> list[tuple[int, dict]]:
    sorties = []
    for bloc in reponse.text.split("\n\n"):
        if not bloc.startswith("id:"):
            continue
        ligne_id, ligne_data = bloc.split("\n", 1)
        sorties.append((int(ligne_id[3:]), json.loads(ligne_data[len("data: ") :])))
    return sorties


async def ouvrir(client, jeton, org, agent, message="Construis", **plus):
    r = await client.post(f"{B}/fils", json={"message": message, "workflow_id": agent.id if agent else None, **plus}, headers=entetes(jeton, org))
    assert r.status_code == 200, r.text
    return r.json()


# --- le module d'événements --------------------------------------------------------------------------------------------


async def test_le_module_rejoue_puis_suit_puis_s_arrete():
    table: list[tuple[int, dict]] = [(1, {"n": 1}), (2, {"n": 2})]
    fini = False

    async def lire_apres(apres):
        return [e for e in table if e[0] > apres]

    async def est_fini():
        return fini

    recus = []

    async def lecteur():
        async for element in evenements.suivre("c", lire_apres, est_fini, depuis=1, attente_max=5):
            recus.append(element)

    tache = asyncio.create_task(lecteur())
    await asyncio.sleep(0.05)
    assert recus == [(2, {"n": 2})]  # rejoué à partir de « depuis », pas avant
    table.append((3, {"n": 3}))
    await evenements.publier("c")
    await asyncio.sleep(0.05)
    assert recus[-1] == (3, {"n": 3})  # la suite arrive par le réveil
    fini = True
    await evenements.publier("c")
    await asyncio.wait_for(tache, 3)  # relu jusqu'au bout, puis le flux s'arrête
    assert [i for i, _ in recus] == [2, 3]


async def test_le_flux_sse_met_en_forme_et_bat_le_coeur():
    async def source():
        yield 7, {"type": "texte", "texte": "é"}
        yield None

    sortie = [m async for m in evenements.flux_sse(source())]
    assert sortie[0] == 'id: 7\ndata: {"type": "texte", "texte": "é"}\n\n' and sortie[1].startswith(":")


async def test_redis_tombe_ne_perd_aucun_evenement(monkeypatch):
    class RedisMort:
        async def publish(self, *a):
            raise ConnectionError("down")

        def pubsub(self):
            raise ConnectionError("down")

    async def client_mort():
        return RedisMort()

    monkeypatch.setattr(evenements, "_client_redis", client_mort)
    evenements.utiliser_transport(evenements.TransportRedis())
    await evenements.publier("c")  # ne lève pas
    table = [(1, {"n": 1})]
    fini = False

    async def lire_apres(apres):
        return [e for e in table if e[0] > apres]

    async def est_fini():
        return fini

    recus = []

    async def lecteur():
        async for element in evenements.suivre("c", lire_apres, est_fini, attente_max=5):
            recus.append(element)

    tache = asyncio.create_task(lecteur())
    await asyncio.sleep(0.1)
    table.append((2, {"n": 2}))  # aucun réveil : la table est relue à intervalle court
    await asyncio.sleep(1.4)
    fini = True
    await asyncio.wait_for(tache, 4)
    assert [i for i, _ in recus] == [1, 2]


# --- la conversation en tables -----------------------------------------------------------------------------------------


async def test_un_chat_s_ouvre_tourne_en_fond_et_se_rejoue(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session)
    donner_le_cerveau(monkeypatch, CerveauFactice(tour(texte("Bonjour"))))
    async with client_http() as c:
        fil = await ouvrir(c, jeton, org, agent, "Construis un agent")
        assert fil["etat"] in ("en_cours", "terminee") and fil["titre"] == "Construis un agent"
        await service_fil.attendre(fil["id"])
        vu = (await c.get(f"{B}/fils/{fil['id']}", headers=entetes(jeton, org))).json()
        assert vu["etat"] == "terminee" and vu["jetons"] == 150 and vu["cout"] >= 0 and 0 <= vu["jauge"] <= 1
        flux = lire_sse(await c.get(f"{B}/fils/{fil['id']}/evenements", headers=entetes(jeton, org)))
        genres = [e["type"] for _, e in flux]
        assert genres[0] == "message" and "texte" in genres and genres[-1] == "fin"
        assert [i for i, _ in flux] == sorted(i for i, _ in flux)
        # Le rechargement de l'écran : même flux depuis 0, et rien depuis le dernier reçu.
        assert lire_sse(await c.get(f"{B}/fils/{fil['id']}/evenements", headers=entetes(jeton, org))) == flux
        derniere = flux[-1][0]
        assert lire_sse(await c.get(f"{B}/fils/{fil['id']}/evenements?depuis={derniere}", headers=entetes(jeton, org))) == []
        reprise = lire_sse(await c.get(f"{B}/fils/{fil['id']}/evenements", headers={**entetes(jeton, org), "Last-Event-ID": str(flux[0][0])}))
        assert [i for i, _ in reprise] == [i for i, _ in flux[1:]]  # Last-Event-ID à la reconnexion


async def test_plusieurs_conversations_par_agent_et_cloisonnement(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "b")
    autre_org, _autre, autre_jeton, autre_agent = await decor(db_session, "c")
    donner_le_cerveau(monkeypatch, CerveauFactice(tour(texte("un")), tour(texte("deux"))))
    async with client_http() as c:
        un = await ouvrir(c, jeton, org, agent, "Première")
        await service_fil.attendre(un["id"])
        deux = await ouvrir(c, jeton, org, agent, "Seconde")
        await service_fil.attendre(deux["id"])
        liste = (await c.get(f"{B}/fils?workflow_id={agent.id}", headers=entetes(jeton, org))).json()
        assert {f["id"] for f in liste} == {un["id"], deux["id"]} and all(f["jetons"] > 0 for f in liste)
        # Une autre organisation ne voit rien et ne touche rien.
        assert (await c.get(f"{B}/fils", headers=entetes(autre_jeton, autre_org))).json() == []
        for chemin, methode in ((f"fils/{un['id']}", "get"), (f"fils/{un['id']}/evenements", "get"), (f"fils/{un['id']}/arreter", "post")):
            r = await getattr(c, methode)(f"{B}/{chemin}", headers=entetes(autre_jeton, autre_org))
            assert r.status_code == 404, chemin
        r = await c.post(f"{B}/fils", json={"message": "x", "workflow_id": agent.id}, headers=entetes(autre_jeton, autre_org))
        assert r.status_code == 404  # l'agent d'une autre organisation


async def test_arreter_coupe_le_cerveau_puis_reprendre_relance_depuis_le_disque(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "d")
    bloque = CerveauBloque()
    donner_le_cerveau(monkeypatch, bloque)
    async with client_http() as c:
        fil = await ouvrir(c, jeton, org, agent)
        await asyncio.wait_for(bloque.commence.wait(), 3)
        assert (await c.get(f"{B}/fils/{fil['id']}", headers=entetes(jeton, org))).json()["etat"] == "en_cours"
        r = await c.post(f"{B}/fils/{fil['id']}/messages", json={"message": "encore"}, headers=entetes(jeton, org))
        assert r.status_code == 409  # un seul travail à la fois
        arret = (await c.post(f"{B}/fils/{fil['id']}/arreter", headers=entetes(jeton, org))).json()
        assert arret["etat"] == "arretee" and not arret["en_cours"]
        flux = lire_sse(await c.get(f"{B}/fils/{fil['id']}/evenements", headers=entetes(jeton, org)))
        assert flux[-1][1] == {"type": "fin", "raison": "arret"}
        # Reprendre : le cerveau relit l'historique, finit, la conversation est terminée.
        suite = CerveauFactice(tour(texte("Je reprends")))
        donner_le_cerveau(monkeypatch, suite)
        assert (await c.post(f"{B}/fils/{fil['id']}/reprendre", headers=entetes(jeton, org))).status_code == 200
        await service_fil.attendre(fil["id"])
        assert (await c.get(f"{B}/fils/{fil['id']}", headers=entetes(jeton, org))).json()["etat"] == "terminee"
        assert "relis l'état actuel" in suite.requetes[0]["messages"][-1]["content"]
        # Reprendre une conversation terminée est refusé.
        assert (await c.post(f"{B}/fils/{fil['id']}/reprendre", headers=entetes(jeton, org))).status_code == 409


async def test_un_appel_sans_resultat_est_repare_avant_de_reprendre():
    conv = {
        "messages": [
            {"role": "user", "content": "x"},
            {"role": "assistant", "content": "", "appels": [{"id": "a1", "nom": "fiche_lire", "arguments": {}}, {"id": "a2", "nom": "contexte_lire", "arguments": {}}]},
            {"role": "outil", "appel_id": "a1", "nom": "fiche_lire", "content": "{}"},
        ]
    }
    service_fil.reparer(conv)
    assert [m.get("appel_id") for m in conv["messages"] if m["role"] == "outil"] == ["a1", "a2"]
    service_fil.reparer(conv)
    assert len([m for m in conv["messages"] if m["role"] == "outil"]) == 2  # rejouable


async def test_au_redemarrage_une_conversation_en_cours_devient_arretee_et_se_reprend(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "e")
    fil = await service_fil.creer(user, agent.id, "Coupée par le redémarrage")
    await db_client.modifier_fil(org, fil.id, etat="en_cours")  # une tâche morte avec l'ancien processus
    assert await service_fil.au_demarrage() >= 1
    donner_le_cerveau(monkeypatch, CerveauFactice(tour(texte("Repris"))))
    async with client_http() as c:
        vu = (await c.get(f"{B}/fils/{fil.id}", headers=entetes(jeton, org))).json()
        assert vu["etat"] == "arretee"
        flux = lire_sse(await c.get(f"{B}/fils/{fil.id}/evenements", headers=entetes(jeton, org)))
        assert flux[-1][1] == {"type": "fin", "raison": "redemarrage"}
        assert (await c.post(f"{B}/fils/{fil.id}/reprendre", headers=entetes(jeton, org))).status_code == 200
        await service_fil.attendre(fil.id)
        assert (await c.get(f"{B}/fils/{fil.id}", headers=entetes(jeton, org))).json()["etat"] == "terminee"


async def test_modifier_et_relancer_retire_le_dernier_message(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "f")
    donner_le_cerveau(monkeypatch, CerveauFactice(tour(texte("réponse 1"))))
    async with client_http() as c:
        fil = await ouvrir(c, jeton, org, agent, "Mauvaise demande")
        await service_fil.attendre(fil["id"])
        second = CerveauFactice(tour(texte("réponse 2")))
        donner_le_cerveau(monkeypatch, second)
        r = await c.post(f"{B}/fils/{fil['id']}/modifier-dernier", json={"message": "Bonne demande"}, headers=entetes(jeton, org))
        assert r.status_code == 200
        await service_fil.attendre(fil["id"])
        envoye = [m["content"] for m in second.requetes[0]["messages"] if m["role"] == "user"]
        assert len(envoye) == 1 and "Bonne demande" in envoye[0] and "Mauvaise" not in envoye[0]
        genres = [e["type"] for _, e in lire_sse(await c.get(f"{B}/fils/{fil['id']}/evenements", headers=entetes(jeton, org)))]
        assert "retrait" in genres


async def test_un_chat_sans_agent_se_rattache_a_l_agent_qu_il_cree(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "g")
    from api.services.builder.actions import registre

    async def creer(contexte, parametres):
        return {"ok": True, "workflow_id": agent.id}

    import dataclasses

    monkeypatch.setitem(registre.REGISTRE, "create_workflow", dataclasses.replace(registre.REGISTRE["create_workflow"], fonction=creer))
    cerveau = CerveauFactice(tour(appel("create_workflow", {"code": "x"})), tour(texte("Fait")))
    donner_le_cerveau(monkeypatch, cerveau)
    async with client_http() as c:
        # RV (mineur 4) : créer un agent est un objet de l'organisation, une carte est demandée hors de « Tout permettre » ;
        # ce test vérifie le rattachement, le chat s'ouvre donc en « Tout permettre » (N4 : mode posé à l'ouverture).
        fil = await ouvrir(c, jeton, org, None, "Crée un agent", mode="tout")
        assert fil["workflow_id"] is None
        await service_fil.attendre(fil["id"])
        vu = (await c.get(f"{B}/fils/{fil['id']}", headers=entetes(jeton, org))).json()
        assert vu["workflow_id"] == agent.id and vu["etat"] == "terminee"
        assert "Cette conversation n'a pas encore d'agent" in json.dumps(cerveau.requetes[0]["messages"], ensure_ascii=False)


# --- la carte plan et la carte question --------------------------------------------------------------------------------


async def test_le_plan_et_la_question_sortent_en_cartes(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "h")
    plan = {"etapes": [{"libelle": "Lire l'audit", "etat": "fait"}, {"libelle": "Concevoir", "etat": "en_cours"}, {"libelle": "Tester"}]}
    cerveau = CerveauFactice(
        tour(appel("plan_mettre_a_jour", plan, "p1"), appel("question_poser", {"question": "Quel ton ?", "reponse_proposee": "Chaleureux", "choix": ["Sobre"]}, "q1")),
        tour(texte("J'attends")),
    )
    donner_le_cerveau(monkeypatch, cerveau)
    async with client_http() as c:
        fil = await ouvrir(c, jeton, org, agent)
        await service_fil.attendre(fil["id"])
        flux = [e for _, e in lire_sse(await c.get(f"{B}/fils/{fil['id']}/evenements", headers=entetes(jeton, org)))]
    cartes = {e["carte"]["type"]: e["carte"] for e in flux if e["type"] == "carte"}
    assert [e["etat"] for e in cartes["plan"]["etapes"]] == ["fait", "en_cours", "a_venir"]
    assert cartes["question"]["reponse_proposee"] == "Chaleureux" and cartes["question"]["choix"] == ["Sobre"]
    # Chaque action et son résultat sont des événements distincts (la ligne compacte « Lit… ✓ » du fil).
    assert [e["nom"] for e in flux if e["type"] == "action"] == ["plan_mettre_a_jour", "question_poser"]
    assert [e["nom"] for e in flux if e["type"] == "resultat"] == ["plan_mettre_a_jour", "question_poser"]


async def test_deux_etapes_en_cours_sont_refusees():
    from api.services.builder.actions.registre import Contexte, executer
    from types import SimpleNamespace

    ctx = Contexte(user=SimpleNamespace(id=1, selected_organization_id=1), workflow_id=None, conversation={})
    refus = await executer("plan_mettre_a_jour", {"etapes": [{"libelle": "a", "etat": "en_cours"}, {"libelle": "b", "etat": "en_cours"}]}, ctx)
    assert refus.get("ok") is False
    bon = await executer("plan_mettre_a_jour", {"etapes": [{"libelle": "a", "etat": "fait"}, {"libelle": "b", "etat": "en_cours"}]}, ctx)
    assert bon["faites"] == 1 and ctx.conversation["plan"][1]["etat"] == "en_cours"


# --- les démarrages ----------------------------------------------------------------------------------------------------


def contenu(**plus):
    return {"phrase": "une phrase", "demande": "Améliore {agent} maintenant", "besoin": "agent", "icone": "test", **plus}


async def test_les_demarrages_sont_des_donnees_de_la_bibliotheque(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "i")
    monkeypatch.setenv("MARK_BIBLIOTHEQUE_ORGANISATION_ID", str(org))
    for n in range(5):
        await bibliotheque.creer("demarrages-builder", f"d{n}", f"Démarrage {n}", contenu(), "test")
    donner_le_cerveau(monkeypatch, CerveauFactice(tour(texte("ok")), tour(texte("ok"))))
    async with client_http() as c:
        cartes = (await c.get(f"{B}/demarrages", headers=entetes(jeton, org))).json()
        assert len(cartes) == 4  # les 4 plus utilisés
        # Un démarrage ajouté apparaît ; un démarrage rejeté disparaît.
        await bibliotheque.creer("demarrages-builder", "tout-neuf", "Tout neuf", contenu(besoin="rien"), "test")
        # Utilisé en premier : il passe devant les autres.
        r = await c.post(f"{B}/fils", json={"message": "Tout neuf", "demarrage": "tout-neuf"}, headers=entetes(jeton, org))
        assert r.status_code == 200, r.text
        await service_fil.attendre(r.json()["id"])
        cartes = (await c.get(f"{B}/demarrages", headers=entetes(jeton, org))).json()
        assert cartes[0]["slug"] == "tout-neuf" and cartes[0]["utilisations"] == 1
        await bibliotheque.marquer("demarrages-builder", "tout-neuf", 1, Statut.REJETE, "test", raison="plus voulu")
        assert "tout-neuf" not in {x["slug"] for x in (await c.get(f"{B}/demarrages", headers=entetes(jeton, org))).json()}
        # Le besoin d'un agent est refusé tant qu'il manque ; {agent} est remplacé par le nom de l'agent.
        manque = await c.post(f"{B}/fils", json={"message": "x", "demarrage": "d1"}, headers=entetes(jeton, org))
        assert manque.status_code == 422
        r = await c.post(f"{B}/fils", json={"message": "Améliore {agent} maintenant", "demarrage": "d1", "workflow_id": agent.id}, headers=entetes(jeton, org))
        assert r.status_code == 200
        await service_fil.attendre(r.json()["id"])
        flux = [e for _, e in lire_sse(await c.get(f"{B}/fils/{r.json()['id']}/evenements", headers=entetes(jeton, org)))]
        assert flux[0]["texte"] == f"Améliore {agent.name} maintenant"
        assert (await c.post(f"{B}/fils", json={"message": "x", "demarrage": "inconnu"}, headers=entetes(jeton, org))).status_code == 404


async def test_le_contenu_d_un_demarrage_est_valide_a_l_ecriture(monde):
    with pytest.raises(bibliotheque.ErreurBibliotheque):
        await bibliotheque.creer("demarrages-builder", "x", "X", {"phrase": "p", "demande": "d", "besoin": "tout"}, "test")
    assert demarrages.remplir("Teste {agent}", "A") == "Teste A" and demarrages.remplir("Teste {agent}", None) == "Teste {agent}"
