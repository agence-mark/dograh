"""[.mark] Builder partie 3, N1 (SA-N1a) : le mode du chat et la carte d'autorisation, de bout en bout (vraie application, vraie base de
test, cerveau simulé : rien n'est dépensé, aucun fournisseur appelé).

| Test | Ce qu'il prouve |
|---|---|
| carte puis « une fois » | le geste pose une carte et le travail s'arrête ; rien n'est fait avant le clic ; le clic relance, le geste passe une fois |
| refuser | la raison est lue par le builder ; rien n'est fait |
| pour ce chat, retirer | l'autorisation se voit dans la conversation, se retire, et ne vaut que pour ce chat |
| mode | réglé par chat, lu par la vue ; un nouveau chat est en « demander » ; liste fermée ; « Tout permettre » est journalisé |
| cloisonnement | la conversation d'une autre organisation est un 404 ; une réponse donnée deux fois est un 409 |
| le rôle borne | un compte sans « agents.publier » ne fait pas publier le builder, même en « Tout permettre » |
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from api.db import db_client
from api.services import mark_evenements as evenements
from api.services.builder import fil as service_fil
from api.services.builder.actions import registre
from api.services.builder.cerveau.factice import CerveauFactice, appel, texte, tour
from api.tests.mark.test_builder_c2 import B, base_en_serie, decor, donner_le_cerveau, fil_de  # noqa: F401
from api.tests.mark.equipe_commun import (  # noqa: F401
    client_http,
    creer_compte,
    entetes,
    sans_preparation_des_organisations,
)


@pytest.fixture(autouse=True)
def transport_en_memoire():
    ancien = evenements.utiliser_transport(evenements.TransportMemoire())
    yield
    evenements.utiliser_transport(ancien)


@pytest.fixture
def publications(monkeypatch):
    """``agent_publier`` remplacé par un espion : la porte des modes est la vraie, la publication ne joue pas."""
    vus: list[dict] = []

    async def espion(contexte, parametres):
        vus.append(parametres.model_dump())
        return {"ok": True, "version": 2}

    monkeypatch.setitem(registre.REGISTRE, "agent_publier", dataclasses.replace(registre.REGISTRE["agent_publier"], fonction=espion))
    return vus


async def _evenements(fil_id: int) -> list[dict]:
    return [e for _i, e in await service_fil.lire_apres(fil_id, 0)]


async def _lancer(user, fil, cerveau, monkeypatch, message="Publie l'agent"):
    from api.services.builder.cerveau.reglages import ReglagesCerveau

    await service_fil.lancer(user, fil, message, cerveau, ReglagesCerveau(modele="m"))
    await service_fil.attendre(fil.id)


async def test_la_carte_arrete_le_travail_et_autoriser_une_fois_relance_le_geste(db_session, sans_preparation_des_organisations, monkeypatch, publications):
    org, user, jeton, agent = await decor(db_session, "n1a")
    fil = await fil_de(org, user, agent)
    cerveau = CerveauFactice(
        tour(appel("agent_publier", {"workflow_id": agent.id}, "p1")),
        tour(texte("Ce tour ne doit jamais être joué avant le clic.")),
    )
    donner_le_cerveau(monkeypatch, cerveau)
    await _lancer(user, fil, cerveau, monkeypatch)
    vus = await _evenements(fil.id)
    carte = next(e["carte"] for e in vus if e["type"] == "carte")
    assert carte["type"] == "autorisation" and carte["action"] == "agent_publier" and carte["famille"] == "publication"
    assert vus[-1] == {"type": "fin", "raison": "attente"} and len(cerveau.requetes) == 1 and publications == []
    assert (await db_client.lire_fil(org, fil.id)).etat == "terminee"

    cerveau2 = CerveauFactice(tour(appel("agent_publier", {"workflow_id": agent.id}, "p2")), tour(texte("Publié.")))
    donner_le_cerveau(monkeypatch, cerveau2)
    async with client_http() as c:
        r = await c.post(f"{B}/fils/{fil.id}/autorisations/{carte['id']}", json={"decision": "une_fois"}, headers=entetes(jeton, org))
        assert r.status_code == 200, r.text
        await service_fil.attendre(fil.id)
        assert (await c.post(f"{B}/fils/{fil.id}/autorisations/{carte['id']}", json={"decision": "refuser"}, headers=entetes(jeton, org))).status_code == 409
        assert (await c.post(f"{B}/fils/{fil.id}/autorisations/zz", json={"decision": "une_fois"}, headers=entetes(jeton, org))).status_code == 404
        assert (await c.post(f"{B}/fils/{fil.id}/autorisations/{carte['id']}", json={"decision": "toujours"}, headers=entetes(jeton, org))).status_code == 422
    assert len(publications) == 1  # une seule fois, après le clic
    assert "Allowed once" in json.dumps(cerveau2.requetes[0]["messages"])
    relu = await db_client.lire_fil(org, fil.id)
    assert relu.historique["autorisations"][carte["id"]]["statut"] == "une_fois" and relu.historique["autorisations"][carte["id"]]["utilisee"]
    assert any(e["type"] == "autorisation_reponse" and e["statut"] == "une_fois" for e in await _evenements(fil.id))


async def test_refuser_transmet_la_raison_au_builder_et_ne_fait_rien(db_session, sans_preparation_des_organisations, monkeypatch, publications):
    org, user, jeton, agent = await decor(db_session, "n1b")
    fil = await fil_de(org, user, agent)
    await db_client.modifier_fil(
        org, fil.id, etat="terminee",
        historique={"messages": [], "autorisations": {"a1": {"nom": "agent_publier", "famille": "publication", "objet": f"agent:{agent.id}", "empreinte": "e", "statut": "attente", "utilisee": False}}},
    )
    cerveau = CerveauFactice(tour(texte("Compris, je ne publie pas.")))
    donner_le_cerveau(monkeypatch, cerveau)
    async with client_http() as c:
        r = await c.post(f"{B}/fils/{fil.id}/autorisations/a1", json={"decision": "refuser", "raison": "Pas avant lundi"}, headers=entetes(jeton, org))
        assert r.status_code == 200 and r.json()["statut"] == "refusee"
        await service_fil.attendre(fil.id)
    contenu = json.dumps(cerveau.requetes[0]["messages"], ensure_ascii=False)
    assert "Refused" in contenu and "Pas avant lundi" in contenu and publications == []


async def test_pour_ce_chat_se_voit_se_retire_et_ne_vaut_que_pour_ce_chat(db_session, sans_preparation_des_organisations, monkeypatch, publications):
    org, user, jeton, agent = await decor(db_session, "n1c")
    fil = await fil_de(org, user, agent)
    autre = await fil_de(org, user, agent, "autre chat")
    demande = {"nom": "agent_publier", "famille": "publication", "objet": f"agent:{agent.id}", "empreinte": "e", "statut": "attente", "utilisee": False}
    await db_client.modifier_fil(org, fil.id, etat="terminee", historique={"messages": [], "autorisations": {"a1": demande}})
    cerveau = CerveauFactice(tour(appel("agent_publier", {"workflow_id": agent.id}, "p1")), tour(texte("Fait.")))
    donner_le_cerveau(monkeypatch, cerveau)
    async with client_http() as c:
        assert (await c.post(f"{B}/fils/{fil.id}/autorisations/a1", json={"decision": "pour_ce_chat"}, headers=entetes(jeton, org))).status_code == 200
        await service_fil.attendre(fil.id)
        vue = (await c.get(f"{B}/fils/{fil.id}", headers=entetes(jeton, org))).json()
        assert vue["autorisations_du_chat"] == [{"id": "a1", "nom": "agent_publier", "famille": "publication", "objet": f"agent:{agent.id}"}]
        assert len(publications) == 1
        # l'autre chat n'a rien reçu
        assert (await c.get(f"{B}/fils/{autre.id}", headers=entetes(jeton, org))).json()["autorisations_du_chat"] == []
        assert (await c.delete(f"{B}/fils/{fil.id}/autorisations/a1", headers=entetes(jeton, org))).status_code == 200
        assert (await c.get(f"{B}/fils/{fil.id}", headers=entetes(jeton, org))).json()["autorisations_du_chat"] == []
        assert (await c.delete(f"{B}/fils/{fil.id}/autorisations/a1", headers=entetes(jeton, org))).status_code == 409


async def test_le_mode_se_regle_par_chat_en_liste_fermee_et_tout_permettre_est_journalise(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "n1d")
    fil = await fil_de(org, user, agent)
    nouveau = await fil_de(org, user, agent, "nouveau")
    journal = []

    async def journaliser(u, quoi, organisation, detail=None):
        journal.append((quoi, organisation, detail))

    monkeypatch.setattr("api.services.equipe_mark.acces.journaliser", journaliser)
    async with client_http() as c:
        assert (await c.get(f"{B}/fils/{fil.id}", headers=entetes(jeton, org))).json()["mode"] == "demander"
        for mode in ("plan", "agent", "tout", "demander"):
            r = await c.put(f"{B}/fils/{fil.id}/mode", json={"mode": mode}, headers=entetes(jeton, org))
            assert r.status_code == 200 and r.json()["mode"] == mode
        assert (await c.put(f"{B}/fils/{fil.id}/mode", json={"mode": "admin"}, headers=entetes(jeton, org))).status_code == 422
        await c.put(f"{B}/fils/{fil.id}/mode", json={"mode": "tout"}, headers=entetes(jeton, org))
        assert (await c.get(f"{B}/fils/{fil.id}", headers=entetes(jeton, org))).json()["mode"] == "tout"
        assert (await c.get(f"{B}/fils/{nouveau.id}", headers=entetes(jeton, org))).json()["mode"] == "demander"
    assert [q for q, *_ in journal if q == "builder.mode"] == ["builder.mode", "builder.mode", "builder.mode"]  # agent, tout, tout
    assert all(d["fil"] == fil.id for q, _o, d in journal if q == "builder.mode")


async def test_la_conversation_d_une_autre_organisation_est_un_404(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent = await decor(db_session, "n1e")
    autre_org, autre_user, autre_jeton, autre_agent = await decor(db_session, "n1f")
    fil = await fil_de(org, user, agent)
    async with client_http() as c:
        assert (await c.put(f"{B}/fils/{fil.id}/mode", json={"mode": "tout"}, headers=entetes(autre_jeton, autre_org))).status_code == 404
        assert (await c.post(f"{B}/fils/{fil.id}/autorisations/a1", json={"decision": "une_fois"}, headers=entetes(autre_jeton, autre_org))).status_code == 404
        assert (await c.delete(f"{B}/fils/{fil.id}/autorisations/a1", headers=entetes(autre_jeton, autre_org))).status_code == 404


async def test_un_compte_sans_publier_ne_fait_pas_publier_le_builder_meme_en_tout_permettre(db_session, sans_preparation_des_organisations, monkeypatch, publications):
    org, admin, _jeton, agent = await decor(db_session, "n1g")
    membre, _ = await creer_compte(db_session, "n1g-membre@example.test", role="Membre", organisations=[org])
    fil = await fil_de(org, membre, agent)
    await db_client.modifier_fil(org, fil.id, historique={"messages": [], "mode": "tout"})
    fil = await db_client.lire_fil(org, fil.id)
    cerveau = CerveauFactice(tour(appel("agent_publier", {"workflow_id": agent.id}, "p1")), tour(texte("Je ne peux pas.")))
    membre.selected_organization_id = org
    await _lancer(membre, fil, cerveau, monkeypatch)
    resultat = next(e for e in await _evenements(fil.id) if e["type"] == "resultat")
    assert resultat["resultat"]["code"] == "droits" and publications == []
