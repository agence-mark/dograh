"""[.mark] Revue serveur, passage 1, corrections R2 (Hub « Relation clients ») : M9 et mineur 8.

| Test | Ce qu'il prouve |
|---|---|
| M9 : dernier message en une requête | la liste des fils lit les derniers messages en UNE requête, quel que soit le nombre de fils ; une note interne n'est le dernier message que pour le Hub |
| M9 : avis bornés | ``/relation/avis`` lit les bases cinq à la fois au plus ; une base qui dépasse le délai donne « aucun avis » sans bloquer la page |
| mineur 8 : journal | réponse, note, témoignage, état d'un fil : chaque geste d'écriture du Hub est écrit au journal, sans le texte |
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import event

from api.db import db_client
from api.routes import relation
from api.services.relation import hub
from api.tests.mark.equipe_commun import (  # noqa: F401
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,
)

R = "/api/v1/relation"

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")


async def test_m9_les_derniers_messages_se_lisent_en_une_requete(db_session, async_session):
    org = await creer_organisation(db_session, "r2-hub-m9")
    fils = []
    for i in range(6):
        fil = await db_session.creer_fil_relation(
            org, sorte="question", sujet=f"Fil {i}", auteur="Paul", texte=f"premier {i}"
        )
        fils.append(fil["id"] if isinstance(fil, dict) else fil.id)
    await db_session.ajouter_message_relation(org, fils[0], cote="mark", auteur="Evan", texte="réponse 0")
    await db_session.ajouter_message_relation(org, fils[0], cote="interne", auteur="Evan", texte="note interne 0")

    requetes: list[str] = []

    def compter(_conn, _curseur, statement, *_a):
        if statement.lstrip().upper().startswith("SELECT") and "mark_relation_messages" in statement:
            requetes.append(statement)

    lien = async_session.sync_session.get_bind()
    event.listen(lien, "before_cursor_execute", compter)
    try:
        pour_le_portail = await db_session.lister_fils_relation([org])
        pour_le_hub = await db_session.lister_fils_relation([org], avec_internes=True)
    finally:
        event.remove(lien, "before_cursor_execute", compter)

    assert len(requetes) == 2  # une par appel, pas une par fil (6 fils)
    portail = {f["id"]: f["dernier"] for f in pour_le_portail}
    hub_vu = {f["id"]: f["dernier"] for f in pour_le_hub}
    assert portail[fils[0]]["texte"] == "réponse 0"  # la note interne ne sort pas du Hub
    assert hub_vu[fils[0]]["texte"] == "note interne 0"
    assert portail[fils[3]]["texte"] == "premier 3"
    assert len(portail) == 6 and all(v is not None for v in portail.values())


async def test_m9_les_avis_se_lisent_cinq_a_la_fois_avec_un_delai(db_session, monkeypatch):
    orgs = [await creer_organisation(db_session, f"r2-hub-avis-{i}") for i in range(9)]
    _admin, jeton = await creer_compte(db_session, "r2-hub-avis@example.com", role="Administrateur", organisations=orgs)
    lente = orgs[0]
    en_cours = {"n": 0, "max": 0}

    async def stats(organisation):
        if organisation == lente:
            await asyncio.sleep(5)  # dépasse le délai
        en_cours["n"] += 1
        en_cours["max"] = max(en_cours["max"], en_cours["n"])
        await asyncio.sleep(0.05)
        en_cours["n"] -= 1
        return {"note": 4.0, "avis": 3}

    monkeypatch.setattr(hub, "stats_avis", stats)
    monkeypatch.setattr(relation, "DELAI_LECTURE_BASE_S", 0.3)
    async with client_http() as c:
        r = await c.get(f"{R}/avis", headers=entetes(jeton))
    assert r.status_code == 200, r.text
    par_client = {x["organization_id"]: x for x in r.json()}
    assert en_cours["max"] <= relation.LECTURES_EN_PARALLELE
    assert par_client[lente]["avis"] == 0 and par_client[lente]["note"] is None  # délai dépassé : aucun avis, la page s'ouvre
    # Un Administrateur voit tous les clients de la base de test partagée : on compte seulement les siens.
    assert sum(1 for o in orgs[1:] if par_client[o]["avis"] == 3) == 8


async def test_mineur_8_chaque_geste_d_ecriture_du_hub_est_au_journal(db_session):
    org = await creer_organisation(db_session, "r2-hub-journal")
    _admin, jeton = await creer_compte(db_session, "r2-hub-journal@example.com", role="Administrateur", organisations=[org])
    fil = await db_session.creer_fil_relation(org, sorte="question", sujet="S", auteur="Paul", texte="T")
    fil_id = fil["id"] if isinstance(fil, dict) else fil.id
    h = entetes(jeton)
    async with client_http() as c:
        assert (await c.post(f"{R}/clients/{org}/fils/{fil_id}/messages", json={"cote": "mark", "texte": "TEXTE-A-NE-PAS-JOURNALISER"}, headers=h)).status_code == 201
        assert (await c.patch(f"{R}/clients/{org}/fils/{fil_id}", json={"etat": "clos"}, headers=h)).status_code == 204
        note = (await c.post(f"{R}/clients/{org}/notes", json={"texte": "une note"}, headers=h)).json()
        assert (await c.delete(f"{R}/clients/{org}/notes/{note['id']}", headers=h)).status_code == 204
        t = (await c.post(f"{R}/clients/{org}/temoignages", json={"texte": "bien", "auteur": "P"}, headers=h)).json()
        assert (await c.patch(f"{R}/clients/{org}/temoignages/{t['id']}", json={"accord": True}, headers=h)).status_code == 204
        assert (await c.delete(f"{R}/clients/{org}/temoignages/{t['id']}", headers=h)).status_code == 204
    lignes, _total = await db_client.lister_journal(limit=50, offset=0, organization_id=org)
    actions = sorted(ligne["action"] for ligne in lignes if ligne["action"].startswith("relation."))
    assert actions == sorted(
        [
            "relation.message",
            "relation.fil_modifie",
            "relation.note_ajoutee",
            "relation.note_supprimee",
            "relation.temoignage_ajoute",
            "relation.temoignage_accord",
            "relation.temoignage_supprime",
        ]
    )
    assert "TEXTE-A-NE-PAS-JOURNALISER" not in str(lignes)
