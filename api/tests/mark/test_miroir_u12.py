"""[.mark] Partie 2, U12 (lot I1, sous-lot 2, serveur) : le miroir des conversations Claude Code, le direct, les routes des sources.

Vraie application, vraie base de test, clé MCP réelle de la personne (``X-API-Key``). Aucun fournisseur, aucune dépense.

| Test | Ce qu'il prouve |
|---|---|
| filtre : mêmes cas qu'à Node | les cas d'essai partagés (``scripts/claude-code/tests/vecteurs-filtre.json``) tiennent côté serveur |
| interrupteur éteint par défaut | la route répond « inactif » et ne range rien |
| le miroir range sans secret | message, action, réponse, fin dans une conversation « claude_code » ; aucun secret ni valeur de .env dans le flux |
| lecture seule | écrire, reprendre, arrêter, modifier : 409 |
| cloisonnement | une autre organisation ne voit ni ne lit la conversation ; l'agent d'une autre organisation est ignoré |
| bornes | nom d'action, session, nombre d'événements, absence de clé, limite de débit |
| direct | une écriture par le MCP publie une modification que l'écran lit (objet, source, auteur), filtrée par objet |
| sources (routes) | lire, changer une brique ; le chat de l'écran est fermé sur Claude Code ; une clé ne règle pas les sources |
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.routes import builder_fils, builder_i1
from api.services import sources_cerveaux
from api.services.builder.actions import registre
from api.services.builder.actions.registre import PORTE_MCP, Contexte
from api.services.miroir.filtre import filtrer
from api.tests.mark.builder_commun import graphe_depart
from api.tests.mark.equipe_commun import (  # noqa: F401
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,
)

B = "/api/v1/builder"
# Les préfixes de clé y sont coupés par « {{J}} » (retiré ici) : aucun motif de clé en clair dans le dépôt (protection des pushs).
VECTEURS = json.loads((Path(__file__).parents[3] / "scripts" / "claude-code" / "tests" / "vecteurs-filtre.json").read_text(encoding="utf-8").replace("{{J}}", ""))
SECRET = "sk-ant-api03-ZZZZZZZZZZZZZZZZ"


@pytest.fixture(autouse=True)
def valeurs_de_production(monkeypatch):
    monkeypatch.setattr(sources_cerveaux, "DEFAUT", "claude_code")
    monkeypatch.setattr(builder_i1.rate_limiter, "acquire_token", AsyncMock(return_value=True))
    monkeypatch.setattr(builder_i1, "DUREE_MAX_FLUX_S", 0.0)  # un flux de test finit après avoir rejoué la table
    monkeypatch.setattr(builder_fils, "DUREE_MAX_CLAUDE_CODE_S", 0.0)


async def decor(db, nom):
    org = await creer_organisation(db, f"org-i1-{nom}")
    user, jeton = await creer_compte(db, f"evan.i1{nom}@example.test", role="Administrateur", organisations=[org])
    agent = await db.create_workflow(f"Agent {nom}", graphe_depart(), user.id, org)
    _modele, cle = await db.create_api_key(org, "mcp", created_by=user.id)
    return org, user, jeton, agent, cle


def lire_sse(reponse) -> list[tuple[int, dict]]:
    sorties = []
    for bloc in reponse.text.split("\n\n"):
        if bloc.startswith("id:"):
            ligne_id, ligne_data = bloc.split("\n", 1)
            sorties.append((int(ligne_id[3:]), json.loads(ligne_data[len("data: ") :])))
    return sorties


async def allumer(c, jeton, org):
    r = await c.put(f"{B}/miroir/reglage", json={"actif": True}, headers=entetes(jeton, org))
    assert r.status_code == 200 and r.json() == {"actif": True}


def charge(agent=None, session="session-abc123", **plus):
    return {
        "session": session,
        "workflow_id": agent.id if agent else None,
        "evenements": [
            {"type": "message", "texte": f"Corrige le prompt, ma clé est {SECRET}"},
            {"type": "action", "nom": "brouillon_operation", "resume": "workflow_id=1, api_key=abcd1234efgh5678", "ok": True},
            {"type": "texte", "texte": "Voici le fichier :\nAPP_NAME=mark\nDEBUG=true\nPORT=3000\nREGION=euwest\nFait."},
            {"type": "fin"},
        ],
        **plus,
    }


# --- le filtre du serveur : les mêmes cas qu'à Node -----------------------------------------------------------------------------


@pytest.mark.parametrize("cas", VECTEURS, ids=[v["nom"] for v in VECTEURS])
def test_le_filtre_du_serveur_tient_les_cas_partages(cas):
    entree = cas["entree"]
    if "repeter" in cas:
        cle = next(k for k in cas["repeter"] if k != "fois")
        entree = entree.replace(cle, cas["repeter"][cle] * cas["repeter"]["fois"])
    sortie, _ = filtrer(entree)
    for absent in cas["absents"]:
        assert absent not in sortie, absent
    for present in cas["presents"]:
        assert present in sortie, present


# --- le miroir ------------------------------------------------------------------------------------------------------------------


async def test_l_interrupteur_est_eteint_par_defaut_et_rien_n_est_range(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent, cle = await decor(db_session, "a")
    async with client_http() as c:
        assert (await c.get(f"{B}/miroir/reglage", headers=entetes(jeton, org))).json() == {"actif": False}
        r = await c.post(f"{B}/miroir", json=charge(agent), headers={"X-API-Key": cle})
        assert r.status_code == 200 and r.json()["actif"] is False and r.json()["recus"] == 0
        assert (await c.get(f"{B}/fils", headers=entetes(jeton, org))).json() == []


async def test_le_miroir_range_la_conversation_avec_son_agent_sans_aucun_secret(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent, cle = await decor(db_session, "b")
    async with client_http() as c:
        await allumer(c, jeton, org)
        r = await c.post(f"{B}/miroir", json=charge(agent), headers={"X-API-Key": cle})
        assert r.status_code == 200, r.text
        assert r.json()["actif"] is True and r.json()["recus"] == 4 and r.json()["filtres"] == 3
        liste = (await c.get(f"{B}/fils", headers=entetes(jeton, org))).json()
        assert len(liste) == 1
        fil = liste[0]
        assert fil["genre"] == "claude_code" and fil["auteur"] == "Evan" and fil["workflow_id"] == agent.id
        assert fil["etat"] == "terminee" and fil["titre"].startswith("Corrige le prompt")
        brut = await c.get(f"{B}/fils/{fil['id']}/evenements", headers=entetes(jeton, org))
        flux = lire_sse(brut)
        assert [e["type"] for _, e in flux] == ["message", "action", "resultat", "texte", "fin"]
        assert flux[1][1]["nom"] == "brouillon_operation" and flux[1][1]["id"] == flux[2][1]["id"]  # l'action et son résultat, une carte
        for fragment in ("ZZZZZZZZ", "abcd1234efgh5678", "euwest", "3000", "sk-ant"):
            assert fragment not in brut.text, fragment
        assert "fichier d'environnement retiré" in brut.text  # le bloc de type .env est retiré en entier
        # la même session continue la même conversation
        suite = {"session": "session-abc123", "evenements": [{"type": "message", "texte": "Et maintenant les tests"}]}
        assert (await c.post(f"{B}/miroir", json=suite, headers={"X-API-Key": cle})).json()["fil_id"] == fil["id"]
        assert len((await c.get(f"{B}/fils", headers=entetes(jeton, org))).json()) == 1
        assert (await c.get(f"{B}/fils/{fil['id']}", headers=entetes(jeton, org))).json()["etat"] == "en_cours"


async def test_une_conversation_claude_code_est_en_lecture_seule(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent, cle = await decor(db_session, "c")
    async with client_http() as c:
        await allumer(c, jeton, org)
        fil_id = (await c.post(f"{B}/miroir", json=charge(agent), headers={"X-API-Key": cle})).json()["fil_id"]
        for chemin, corps in (("messages", {"message": "x"}), ("reprendre", None), ("arreter", None), ("modifier-dernier", {"message": "x"})):
            r = await c.post(f"{B}/fils/{fil_id}/{chemin}", json=corps, headers=entetes(jeton, org))
            assert r.status_code == 409 and "Claude Code" in r.text, chemin


async def test_cloisonnement_une_autre_organisation_ne_voit_rien_et_l_agent_d_un_autre_est_ignore(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent, cle = await decor(db_session, "d")
    autre_org, _autre, autre_jeton, _autre_agent, autre_cle = await decor(db_session, "e")
    async with client_http() as c:
        await allumer(c, jeton, org)
        await allumer(c, autre_jeton, autre_org)
        fil_id = (await c.post(f"{B}/miroir", json=charge(agent), headers={"X-API-Key": cle})).json()["fil_id"]
        assert (await c.get(f"{B}/fils/{fil_id}", headers=entetes(autre_jeton, autre_org))).status_code == 404
        assert (await c.get(f"{B}/fils/{fil_id}/evenements", headers=entetes(autre_jeton, autre_org))).status_code == 404
        assert (await c.get(f"{B}/fils", headers=entetes(autre_jeton, autre_org))).json() == []
        # la clé de l'autre organisation désigne l'agent du premier : il est ignoré (la conversation reste sans agent), jamais rattaché
        r = await c.post(f"{B}/miroir", json=charge(agent, session="session-autre1"), headers={"X-API-Key": autre_cle})
        assert r.status_code == 200
        vue = (await c.get(f"{B}/fils/{r.json()['fil_id']}", headers=entetes(autre_jeton, autre_org))).json()
        assert vue["workflow_id"] is None
        # et le corps ne désigne jamais l'organisation : la clé du premier ne range que chez le premier
        assert len((await c.get(f"{B}/fils", headers=entetes(jeton, org))).json()) == 1


async def test_les_bornes_de_la_route(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent, cle = await decor(db_session, "f")
    async with client_http() as c:
        await allumer(c, jeton, org)
        entete = {"X-API-Key": cle}
        assert (await c.post(f"{B}/miroir", json=charge(agent))).status_code == 401  # pas de clé
        assert (await c.post(f"{B}/miroir", json=charge(agent), headers={"X-API-Key": "dgr_fausse_cle_0123456789"})).status_code == 401
        mauvais_nom = {"session": "session-abc123", "evenements": [{"type": "action", "nom": "mon action; rm -rf", "resume": "x"}]}
        assert (await c.post(f"{B}/miroir", json=mauvais_nom, headers=entete)).status_code == 422
        trop = {"session": "session-abc123", "evenements": [{"type": "texte", "texte": "x"}] * 21}
        assert (await c.post(f"{B}/miroir", json=trop, headers=entete)).status_code == 422
        courte = {"session": "ab", "evenements": [{"type": "texte", "texte": "x"}]}
        assert (await c.post(f"{B}/miroir", json=courte, headers=entete)).status_code == 422
        vide = {"session": "session-abc123", "evenements": []}
        assert (await c.post(f"{B}/miroir", json=vide, headers=entete)).status_code == 422
        monkeypatch.setattr(builder_i1.rate_limiter, "acquire_token", AsyncMock(return_value=False))
        assert (await c.post(f"{B}/miroir", json=charge(agent), headers=entete)).status_code == 429


# --- le direct --------------------------------------------------------------------------------------------------------------------


async def test_une_ecriture_par_le_mcp_publie_une_modification_que_l_ecran_lit(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent, cle = await decor(db_session, "g")
    moi = SimpleNamespace(id=user.id, email=user.email, selected_organization_id=org, provider_id="p")
    async with client_http() as c:
        ecrit = await registre.executer("contexte_ecrire", {"workflow_id": agent.id, "notes": "Une note"}, Contexte(user=moi, porte=PORTE_MCP))
        assert ecrit.get("ok") is not False, ecrit
        flux = lire_sse(await c.get(f"{B}/live?depuis=0", headers=entetes(jeton, org)))
        assert [(e["objet"], e["action"], e["source"], e["auteur"]) for _, e in flux] == [(f"agent:{agent.id}", "contexte_ecrire", "claude_code", "Evan")]
        # filtre par objet, et reprise depuis le dernier identifiant reçu
        assert lire_sse(await c.get(f"{B}/live?depuis=0&objet=agent:999999", headers=entetes(jeton, org))) == []
        assert lire_sse(await c.get(f"{B}/live?depuis={flux[-1][0]}", headers=entetes(jeton, org))) == []
        assert lire_sse(await c.get(f"{B}/live", headers={**entetes(jeton, org), "Last-Event-ID": "0"})) != []
        # par l'écran, la même action publie avec la source « ecran »
        await registre.executer("contexte_ecrire", {"workflow_id": agent.id, "notes": "Autre"}, Contexte(user=moi))
        derniere = lire_sse(await c.get(f"{B}/live?depuis={flux[-1][0]}", headers=entetes(jeton, org)))
        assert [e["source"] for _, e in derniere] == ["ecran"]
        assert (await c.get(f"{B}/live?objet=Agent%201", headers=entetes(jeton, org))).status_code == 422


async def test_une_ecriture_refusee_ne_publie_rien(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent, cle = await decor(db_session, "h")
    moi = SimpleNamespace(id=user.id, email=user.email, selected_organization_id=org, provider_id="p")
    async with client_http() as c:
        refus = await registre.executer("contexte_ecrire", {"workflow_id": 987654, "notes": "x"}, Contexte(user=moi, porte=PORTE_MCP))
        assert refus["ok"] is False
        assert lire_sse(await c.get(f"{B}/live?depuis=0", headers=entetes(jeton, org))) == []


# --- les sources ------------------------------------------------------------------------------------------------------------------


async def test_les_sources_se_lisent_et_se_changent_brique_par_brique(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent, cle = await decor(db_session, "i")
    async with client_http() as c:
        vue = (await c.get(f"{B}/sources", headers=entetes(jeton, org))).json()["sources"]
        assert vue == {b: "claude_code" for b in ("builder", "appelant", "juge_tests", "juge_appels", "analyse")}
        r = await c.put(f"{B}/sources/juge_appels", json={"source": "cle_api"}, headers=entetes(jeton, org))
        assert r.status_code == 200 and r.json()["sources"]["juge_appels"] == "cle_api" and r.json()["sources"]["appelant"] == "claude_code"
        assert (await c.put(f"{B}/sources/inconnue", json={"source": "cle_api"}, headers=entetes(jeton, org))).status_code == 404
        assert (await c.put(f"{B}/sources/appelant", json={"source": "autre"}, headers=entetes(jeton, org))).status_code == 422
        # une clé d'API (accès de machine) ne règle pas l'atelier
        assert (await c.put(f"{B}/sources/appelant", json={"source": "cle_api"}, headers={"X-API-Key": cle})).status_code == 403
        assert (await c.get(f"{B}/sources", headers={"X-API-Key": cle})).status_code == 200


async def test_le_chat_de_l_ecran_est_ferme_sur_claude_code_et_ne_cree_aucune_conversation(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent, cle = await decor(db_session, "j")
    async with client_http() as c:
        r = await c.post(f"{B}/fils", json={"message": "Construis", "workflow_id": agent.id}, headers=entetes(jeton, org))
        assert r.status_code == 409 and "Claude Code" in r.text
        assert (await c.get(f"{B}/fils", headers=entetes(jeton, org))).json() == []


async def test_le_resume_de_session_se_lit_avec_la_cle_de_la_personne(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent, cle = await decor(db_session, "k")
    async with client_http() as c:
        r = await c.get(f"{B}/resume", headers={"X-API-Key": cle})
        assert r.status_code == 200, r.text
        corps = r.json()
        assert set(corps) >= {"a_ameliorer", "tests_en_echec", "appels_a_juger", "chats_du_builder"}
        assert (await c.get(f"{B}/resume?depuis=hier", headers={"X-API-Key": cle})).status_code == 422
        assert (await c.get(f"{B}/resume")).status_code == 401


async def test_deux_comptes_de_la_meme_organisation_ne_partagent_jamais_une_conversation(db_session, sans_preparation_des_organisations):
    """Revue serveur, mineur 5 : la conversation d'une session se retrouve par l'organisation ET le compte. Le même identifiant
    de session envoyé par la clé d'un autre compte ouvre SA conversation, jamais celle du premier."""
    org, user, jeton, agent, cle = await decor(db_session, "f")
    pierre, jeton_pierre = await creer_compte(db_session, "pierre.i1f@example.test", role="Administrateur", organisations=[org])
    _modele, cle_pierre = await db_session.create_api_key(org, "mcp-pierre", created_by=pierre.id)
    async with client_http() as c:
        await allumer(c, jeton, org)
        await allumer(c, jeton_pierre, org)
        fil_evan = (await c.post(f"{B}/miroir", json=charge(agent), headers={"X-API-Key": cle})).json()["fil_id"]
        r = await c.post(f"{B}/miroir", json=charge(agent), headers={"X-API-Key": cle_pierre})
    assert r.status_code == 200, r.text
    assert r.json()["fil_id"] != fil_evan
    assert (await db_session.fil_de_la_session(org, "session-abc123", user.id)).id == fil_evan
    assert (await db_session.fil_de_la_session(org, "session-abc123", pierre.id)).id == r.json()["fil_id"]
