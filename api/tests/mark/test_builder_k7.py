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


# --- Réglages du Labo > Builder IA : les vraies données ------------------------------------------------------------------------------

from datetime import UTC, datetime, timedelta  # noqa: E402

from api.services.builder import depense, options, stock  # noqa: E402
from api.services.builder.actions.registre import PORTE_MCP, REGISTRE, Contexte, executer  # noqa: E402
from api.services.builder.bibliotheque import service as bibliotheque  # noqa: E402
from api.services.builder.cerveau.reglages import ReglagesCerveau  # noqa: E402


async def le_labo(db_session, monkeypatch, nom):
    org, user, jeton, agent = await decor(db_session, nom)
    monkeypatch.setenv("MARK_BIBLIOTHEQUE_ORGANISATION_ID", str(org))
    return org, user, jeton, agent


def donner_avec_plafond(monkeypatch, cerveau, plafond_mois):
    monkeypatch.setattr(
        "api.routes.builder._cerveau_de", AsyncMock(return_value=(cerveau, ReglagesCerveau(modele="m", plafond_mois=plafond_mois)))
    )


async def test_la_vue_des_cerveaux_lit_les_vraies_donnees(db_session, sans_preparation_des_organisations, monkeypatch):
    org, _user, jeton, _agent = await le_labo(db_session, monkeypatch, "k7g")
    await bibliotheque.creer("methode-builder", "methode", "Méthode du builder", {"texte": "La méthode."}, "test")
    async with client_http() as c:
        r = await c.get(f"{B}/cerveaux", headers=entetes(jeton, org))
        assert r.status_code == 200, r.text
        vue = r.json()
        assert vue["builder"]["prompt"]["slug"] == "methode" and vue["builder"]["prompt"]["version"] == 1
        assert vue["builder"]["prompt"]["statut"] == "candidat" and vue["builder"]["prompt"]["titre"] == "Méthode du builder"
        # L'appelant et le juge : élément absent de la bibliothèque, le texte du code sert de secours (titre vide).
        assert vue["appelant"]["prompt"]["titre"] is None and vue["juge"]["prompt"]["slug"] == "grille-juge"
        recu = {x["cle"]: x["present"] for x in vue["builder"]["recoit"]}
        assert recu["conventions"] is False and recu["preferences"] is False and recu["recettes_a_la_demande"] is True
        # Les portes comptent les actions du registre de chaque porte.
        assert vue["portes"]["ecran"] == {"ouverte": True, "actions": len([a for a in REGISTRE.values() if a.moteur])}
        assert vue["portes"]["claude_code"]["actions"] == len([a for a in REGISTRE.values() if a.mcp])
        assert vue["builder_actif"] is True and vue["plafond_du_mois"] == 0 and vue["depense_du_mois"] == 0
        assert vue["limites_du_juge"]["passes_max"] == 3 and vue["limites_du_juge"]["accord_min"] == 0.8
        # Réservé à l'équipe : un compte d'une autre organisation n'y lit rien.
        autre_org, _u, autre_jeton, _a = await decor(db_session, "k7h")
        assert (await c.get(f"{B}/cerveaux", headers=entetes(autre_jeton, autre_org))).status_code in (403, 404)


async def test_l_interrupteur_et_les_portes_sont_eteints_par_defaut_puis_coupent(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await le_labo(db_session, monkeypatch, "k7i")
    ctx_mcp = Contexte(user=user, workflow_id=agent.id, porte=PORTE_MCP)
    ctx_ecran = Contexte(user=user, workflow_id=agent.id)
    # Par défaut : rien n'est coupé.
    assert (await options.lire(org)) == options.Options()
    assert (await executer("fiche_lire", {}, ctx_mcp)).get("code") != "porte_coupee"
    async with client_http() as c:
        # Porte de Claude Code coupée : l'écran continue, le MCP est refusé.
        assert (await c.put(f"{B}/options", json={"porte_claude_code_coupee": True}, headers=entetes(jeton, org))).status_code == 200
        assert (await executer("fiche_lire", {}, ctx_mcp))["code"] == "porte_coupee"
        assert (await executer("fiche_lire", {}, ctx_ecran)).get("code") != "porte_coupee"
        # Porte de l'écran coupée : les actions de l'écran sont refusées et le chat ne s'ouvre plus (409, avant tout cerveau).
        await c.put(f"{B}/options", json={"porte_ecran_coupee": True}, headers=entetes(jeton, org))
        assert (await executer("fiche_lire", {}, ctx_ecran))["code"] == "porte_coupee"
        r = await c.post(f"{B}/fils", json={"message": "x", "workflow_id": agent.id}, headers=entetes(jeton, org))
        assert r.status_code == 409 and "door" in r.json()["detail"]
        # L'interrupteur du builder coupe les deux portes d'un coup, et la vue le dit.
        await c.put(f"{B}/options", json={"builder_coupe": True}, headers=entetes(jeton, org))
        assert (await executer("fiche_lire", {}, ctx_mcp))["code"] == "porte_coupee"
        vue = (await c.get(f"{B}/cerveaux", headers=entetes(jeton, org))).json()
        assert vue["builder_actif"] is False and vue["portes"]["ecran"]["ouverte"] is False and vue["portes"]["claude_code"]["ouverte"] is False
        # Rallumé : tout repart.
        await c.put(f"{B}/options", json={}, headers=entetes(jeton, org))
    assert (await executer("fiche_lire", {}, ctx_mcp)).get("code") != "porte_coupee"


async def test_le_plafond_du_mois_refuse_de_demarrer_une_fois_atteint(db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await le_labo(db_session, monkeypatch, "k7j")
    fil = await db_client.creer_fil(org, user.id, agent.id, "Ce mois-ci", None)
    await db_client.modifier_fil(org, fil.id, cout=3.5)
    assert round(await depense.du_mois(org), 2) == 3.5
    assert await db_client.somme_des_couts_depuis(datetime.now(UTC) + timedelta(days=1)) == 0  # rien avant la période : ne compte pas
    async with client_http() as c:
        # Sans plafond (0 = aucun) : le chat démarre.
        donner_avec_plafond(monkeypatch, CerveauFactice(tour(texte("ok"))), 0.0)
        r = await c.post(f"{B}/fils", json={"message": "un", "workflow_id": agent.id}, headers=entetes(jeton, org))
        assert r.status_code == 200, r.text
        await service_fil.attendre(r.json()["id"])
        # Plafond à 3 $ avec 3,5 $ déjà dépensés : refusé, en une phrase.
        donner_avec_plafond(monkeypatch, CerveauFactice(tour(texte("non"))), 3.0)
        r = await c.post(f"{B}/fils", json={"message": "deux", "workflow_id": agent.id}, headers=entetes(jeton, org))
        assert r.status_code == 402 and "monthly ceiling" in r.json()["detail"]
        # Le plafond posé par la route du cerveau est lu par la vue.
        await stock.ecrire(org, "MARK_BUILDER_CERVEAU", ReglagesCerveau(modele="m", plafond_mois=3.0).model_dump(mode="json"))
        vue = (await c.get(f"{B}/cerveaux", headers=entetes(jeton, org))).json()
        assert vue["plafond_du_mois"] == 3.0 and vue["depense_du_mois"] >= 3.5
        # Plafond relevé : le chat repart.
        donner_avec_plafond(monkeypatch, CerveauFactice(tour(texte("oui"))), 100.0)
        r = await c.post(f"{B}/fils", json={"message": "trois", "workflow_id": agent.id}, headers=entetes(jeton, org))
        assert r.status_code == 200
        await service_fil.attendre(r.json()["id"])


async def test_se16_continuer_quand_meme_est_explicite_ponctuel_reserve_a_l_equipe_et_journalise(db_session, sans_preparation_des_organisations, monkeypatch):
    """SE-16 (E-5) : plafond atteint = 402 ; avec « continuer quand même » le travail part, UNE fois, avec une ligne au journal ;
    la fois suivante le plafond redemande ; une organisation qui n'est pas de l'équipe .mark est refusée (403)."""
    org, user, jeton, agent = await le_labo(db_session, monkeypatch, "k7s16")
    fil = await db_client.creer_fil(org, user.id, agent.id, "Ce mois-ci", None)
    await db_client.modifier_fil(org, fil.id, cout=3.5)
    async with client_http() as c:
        donner_avec_plafond(monkeypatch, CerveauFactice(tour(texte("non"))), 3.0)
        refus = await c.post(f"{B}/fils", json={"message": "deux", "workflow_id": agent.id}, headers=entetes(jeton, org))
        assert refus.status_code == 402
        lignes, _ = await db_client.lister_journal(limit=50, offset=0, organization_id=org)
        assert not [l for l in lignes if l["action"] == "builder.plafond_mois_depasse"]  # un refus n'écrit rien
        donner_avec_plafond(monkeypatch, CerveauFactice(tour(texte("ok"))), 3.0)
        accord = await c.post(f"{B}/fils", json={"message": "deux", "workflow_id": agent.id, "depasser_le_plafond": True}, headers=entetes(jeton, org))
        assert accord.status_code == 200, accord.text
        await service_fil.attendre(accord.json()["id"])
        lignes, _ = await db_client.lister_journal(limit=50, offset=0, organization_id=org)
        depassements = [l for l in lignes if l["action"] == "builder.plafond_mois_depasse"]
        assert len(depassements) == 1 and depassements[0]["detail"]["fil"] == accord.json()["id"] and depassements[0]["detail"]["plafond_mois"] == 3.0
        assert "deux" not in str(depassements[0])  # jamais le message de la personne
        # Ponctuel : rien n'est retenu, la demande suivante sans le drapeau est de nouveau refusée.
        donner_avec_plafond(monkeypatch, CerveauFactice(tour(texte("non"))), 3.0)
        encore = await c.post(f"{B}/fils", json={"message": "trois", "workflow_id": agent.id}, headers=entetes(jeton, org))
        assert encore.status_code == 402
        # Pas de plafond atteint : le drapeau ne journalise rien de plus.
        donner_avec_plafond(monkeypatch, CerveauFactice(tour(texte("ok"))), 100.0)
        libre = await c.post(f"{B}/fils", json={"message": "quatre", "workflow_id": agent.id, "depasser_le_plafond": True}, headers=entetes(jeton, org))
        assert libre.status_code == 200
        await service_fil.attendre(libre.json()["id"])
        lignes, _ = await db_client.lister_journal(limit=50, offset=0, organization_id=org)
        assert len([l for l in lignes if l["action"] == "builder.plafond_mois_depasse"]) == 1
        # Une organisation qui n'est pas de l'équipe ne dépasse pas le plafond de .mark.
        autre_org, _u, autre_jeton, autre_agent = await decor(db_session, "k7s16b")
        donner_avec_plafond(monkeypatch, CerveauFactice(tour(texte("non"))), 3.0)
        interdit = await c.post(
            f"{B}/fils", json={"message": "x", "workflow_id": autre_agent.id, "depasser_le_plafond": True}, headers=entetes(autre_jeton, autre_org)
        )
        assert interdit.status_code == 403
