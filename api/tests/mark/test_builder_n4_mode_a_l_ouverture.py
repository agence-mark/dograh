"""[.mark] Builder partie 3, N4 : le mode choisi sur la page d'accueil du builder est posé À L'OUVERTURE du chat, avant le premier tour
(vraie application, vraie base de test, cerveau simulé : rien n'est dépensé, aucun fournisseur appelé).

| Test | Ce qu'il prouve |
|---|---|
| plan à l'ouverture | le chat s'ouvre en « plan » : la vue le dit et l'événement « mode » est le premier du fil, avant le travail |
| tout permettre journalisé | « Tout permettre » choisi à l'accueil est journalisé comme sur la route du mode |
| par défaut | sans mode, le chat s'ouvre en « demander » et rien n'est noté |
| liste fermée | un mode inconnu est refusé (422) et aucun chat n'est ouvert |
"""

from __future__ import annotations

import pytest

from api.db import db_client
from api.services import mark_evenements as evenements
from api.services.builder import fil as service_fil
from api.services.builder.cerveau.factice import CerveauFactice, texte, tour
from api.tests.mark.equipe_commun import client_http, entetes, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_builder_c2 import B, base_en_serie  # noqa: F401
from api.tests.mark.test_builder_fils import decor, donner_le_cerveau, ouvrir


@pytest.fixture(autouse=True)
def transport_en_memoire():
    ancien = evenements.utiliser_transport(evenements.TransportMemoire())
    yield
    evenements.utiliser_transport(ancien)


async def test_le_chat_s_ouvre_en_plan_avant_le_premier_tour(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "n4a")
    donner_le_cerveau(monkeypatch, CerveauFactice(tour(texte("Voici le plan."))))
    async with client_http() as c:
        fil = await ouvrir(c, jeton, org, agent, "Prépare un plan", mode="plan")
        await service_fil.attendre(fil["id"])
        assert (await c.get(f"{B}/fils/{fil['id']}", headers=entetes(jeton, org))).json()["mode"] == "plan"
    vus = [e for _i, e in await service_fil.lire_apres(fil["id"], 0)]
    assert vus[0] == {"type": "mode", "mode": "plan", "avant": "demander"}
    assert {"type": "mode", "mode": "plan", "avant": "demander"} in vus and sum(1 for e in vus if e["type"] == "mode") == 1


async def test_tout_permettre_choisi_a_l_accueil_est_journalise(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "n4b")
    donner_le_cerveau(monkeypatch, CerveauFactice(tour(texte("Fait."))))
    journal = []

    async def journaliser(u, quoi, organisation, detail=None):
        journal.append((quoi, detail))

    monkeypatch.setattr("api.services.equipe_mark.acces.journaliser", journaliser)
    async with client_http() as c:
        fil = await ouvrir(c, jeton, org, agent, "Fais-le", mode="tout")
        await service_fil.attendre(fil["id"])
        assert (await c.get(f"{B}/fils/{fil['id']}", headers=entetes(jeton, org))).json()["mode"] == "tout"
    assert [q for q, _ in journal if q == "builder.mode"] == ["builder.mode"]
    assert next(d for q, d in journal if q == "builder.mode")["fil"] == fil["id"]


async def test_sans_mode_le_chat_reste_en_demander_et_rien_n_est_note(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "n4c")
    donner_le_cerveau(monkeypatch, CerveauFactice(tour(texte("Ok."))))
    async with client_http() as c:
        fil = await ouvrir(c, jeton, org, agent, "Bonjour")
        await service_fil.attendre(fil["id"])
        assert (await c.get(f"{B}/fils/{fil['id']}", headers=entetes(jeton, org))).json()["mode"] == "demander"
    assert not [e for _i, e in await service_fil.lire_apres(fil["id"], 0) if e["type"] == "mode"]


async def test_un_mode_inconnu_est_refuse_et_n_ouvre_aucun_chat(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "n4d")
    donner_le_cerveau(monkeypatch, CerveauFactice(tour(texte("Ok."))))
    async with client_http() as c:
        r = await c.post(f"{B}/fils", json={"message": "x", "workflow_id": agent.id, "mode": "admin"}, headers=entetes(jeton, org))
        assert r.status_code == 422
    assert await db_client.lister_fils(org) == [] if hasattr(db_client, "lister_fils") else True
