"""[.mark] Builder partie 2, lot K7 : renommer et supprimer une conversation du Chat (menu ⋮).

| Test | Ce qu'il prouve |
|---|---|
| renommer | le titre change, se range propre, un titre vide est refusé, une autre organisation a un 404, le direct est publié |
| supprimer | la conversation, ses événements et ses sous-agents disparaissent ; un travail en cours est coupé d'abord |
| supprimer : garde-fous | une clé d'API ne supprime pas (403), une autre organisation a un 404, un sous-agent seul ne se supprime pas, le geste est journalisé sans le titre |
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from api.db import db_client
from api.services.builder import fil as service_fil
from api.services.builder.cerveau.factice import CerveauFactice, texte, tour
from api.tests.mark.equipe_commun import client_http, entetes, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_builder_fils import B, CerveauBloque, decor, donner_le_cerveau, ouvrir, transport_en_memoire  # noqa: F401


async def test_renommer_une_conversation(db_session, sans_preparation_des_organisations, monkeypatch):
    org, _user, jeton, agent = await decor(db_session, "k7a")
    autre_org, _autre, autre_jeton, _ = await decor(db_session, "k7b")
    donner_le_cerveau(monkeypatch, CerveauFactice(tour(texte("ok"))))
    async with client_http() as c:
        fil = await ouvrir(c, jeton, org, agent, "Premier titre")
        await service_fil.attendre(fil["id"])
        r = await c.put(f"{B}/fils/{fil['id']}/titre", json={"titre": "  Relecture   du   numéro  "}, headers=entetes(jeton, org))
        assert r.status_code == 200 and r.json()["titre"] == "Relecture du numéro"
        assert (await c.get(f"{B}/fils/{fil['id']}", headers=entetes(jeton, org))).json()["titre"] == "Relecture du numéro"
        assert (await c.put(f"{B}/fils/{fil['id']}/titre", json={"titre": "   "}, headers=entetes(jeton, org))).status_code == 422
        assert (await c.put(f"{B}/fils/{fil['id']}/titre", json={"titre": "Pirate"}, headers=entetes(autre_jeton, autre_org))).status_code == 404
        assert (await c.get(f"{B}/fils/{fil['id']}", headers=entetes(jeton, org))).json()["titre"] == "Relecture du numéro"
    direct = await db_client.modifications_apres(org, 0, "conversations")
    assert [m.action for m in direct] == ["fil_renomme"]


async def test_supprimer_efface_la_conversation_ses_evenements_et_ses_sous_agents(db_session, sans_preparation_des_organisations, monkeypatch):
    org, _user, jeton, agent = await decor(db_session, "k7c")
    donner_le_cerveau(monkeypatch, CerveauFactice(tour(texte("fait"))))
    async with client_http() as c:
        fil = await ouvrir(c, jeton, org, agent, "À effacer")
        await service_fil.attendre(fil["id"])
        enfant = await db_client.creer_fil(org, None, agent.id, "Sous-agent", parent_id=fil["id"], genre="sous_agent")
        assert await db_client.evenements_apres(fil["id"]) != []
        r = await c.delete(f"{B}/fils/{fil['id']}", headers=entetes(jeton, org))
        assert r.status_code == 204
        assert (await c.get(f"{B}/fils/{fil['id']}", headers=entetes(jeton, org))).status_code == 404
        assert (await c.get(f"{B}/fils", headers=entetes(jeton, org))).json() == []
        assert (await c.delete(f"{B}/fils/{fil['id']}", headers=entetes(jeton, org))).status_code == 404  # rejouable sans effet double
    assert await db_client.evenements_apres(fil["id"]) == []
    assert await db_client.lire_fil(org, enfant.id) is None
    assert [m.action for m in await db_client.modifications_apres(org, 0, "conversations")] == ["fil_supprime"]
    # Le journal dit qui, quoi, où : jamais le titre.
    lignes, _ = await db_client.lister_journal(limit=50, offset=0, organization_id=org)
    supprimes = [l for l in lignes if l["action"] == "builder.fil_supprime"]
    assert len(supprimes) == 1 and supprimes[0]["detail"]["fil_id"] == fil["id"] and "À effacer" not in str(supprimes[0])


async def test_supprimer_coupe_d_abord_le_travail_en_cours(db_session, sans_preparation_des_organisations, monkeypatch):
    org, _user, jeton, agent = await decor(db_session, "k7d")
    bloque = CerveauBloque()
    donner_le_cerveau(monkeypatch, bloque)
    async with client_http() as c:
        fil = await ouvrir(c, jeton, org, agent)
        await asyncio.wait_for(bloque.commence.wait(), 3)
        assert service_fil.en_cours(fil["id"])
        tache = service_fil._TACHES[fil["id"]]
        assert (await c.delete(f"{B}/fils/{fil['id']}", headers=entetes(jeton, org))).status_code == 204
    assert tache.done()  # le travail est coupé, pas seulement oublié
    assert await db_client.lire_fil(org, fil["id"]) is None


async def test_supprimer_garde_fous(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor(db_session, "k7e")
    autre_org, _autre, autre_jeton, _ = await decor(db_session, "k7f")
    donner_le_cerveau(monkeypatch, CerveauFactice(tour(texte("ok"))))
    _, cle = await db_session.create_api_key(org, "portail", user.id)
    async with client_http() as c:
        fil = await ouvrir(c, jeton, org, agent)
        await service_fil.attendre(fil["id"])
        enfant = await db_client.creer_fil(org, user.id, agent.id, "Sous-agent", parent_id=fil["id"], genre="sous_agent")
        # Une clé d'API ne supprime pas.
        assert (await c.delete(f"{B}/fils/{fil['id']}", headers={"X-API-Key": cle})).status_code == 403
        # Une autre organisation ne voit rien, ne supprime rien.
        assert (await c.delete(f"{B}/fils/{fil['id']}", headers=entetes(autre_jeton, autre_org))).status_code == 404
        # Un sous-agent part avec son parent, jamais seul.
        assert (await c.delete(f"{B}/fils/{enfant.id}", headers=entetes(jeton, org))).status_code == 409
        assert (await c.put(f"{B}/fils/{enfant.id}/titre", json={"titre": "x"}, headers=entetes(jeton, org))).status_code == 409
    assert await db_client.lire_fil(org, fil["id"]) is not None
