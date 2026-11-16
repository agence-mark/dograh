"""[.mark] Module Restauration, lot 26, M30 : ce qui manquait aux routes du fork (la fiche servie par le réglage de l'agent, la connaissance par sujets).

| Test | Ce qu'il prouve |
|---|---|
| fiche servie | ``reglages_regler`` accepte ``etablissement_id`` (clé d'établissement, vide = aucune fiche), refuse une valeur mal formée, et ne touche à aucun autre réglage |
| connaissance | un sujet = un document texte « document entier » de l'organisation, écrit deux fois = le même document ; liste ; sans session 401 ; une autre organisation ne le voit pas ; texte vide, sujet mal formé, champ en trop : 422 |
| registre | les deux routes sont au registre (lecture : voir les conversations, écriture : modifier un agent, jamais par clé d'API) |
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from api.db import db_client
from api.services.builder import reglages_agent
from api.services.builder.reglages_agent import ErreurReglage
from api.services.equipe_mark import registre_routes as registre
from api.tests.mark.equipe_commun import (  # noqa: F401
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,
)

RACINE = "/api/v1/restauration/connaissance"


# --------------------------------------------------------------------------- la fiche servie


async def test_la_fiche_servie_se_pose_par_le_reglage_de_l_agent_sans_toucher_au_reste():
    ecrit = {}

    async def update_workflow(**options):
        ecrit.update(options["workflow_configurations"])

    with patch.object(reglages_agent, "_configurations", AsyncMock(return_value={"max_call_duration": 300})), \
         patch.object(db_client, "update_workflow", update_workflow), \
         patch("api.services.groupe.groupe.recopier_dans_les_specialises", AsyncMock()):
        assert "etablissement_id" in reglages_agent.cles_reglables()
        assert await reglages_agent.regler(1, 7, {"etablissement_id": "casa-italia-senlis"}) == {"ecrits": ["etablissement_id"]}
        assert ecrit == {"max_call_duration": 300, "etablissement_id": "casa-italia-senlis"}  # le reste est resté tel quel
        await reglages_agent.regler(1, 7, {"etablissement_id": ""})  # vide : l'agent ne sert plus de fiche
        assert ecrit["etablissement_id"] is None
        for mauvaise in ("Casa Italia", "a" * 41, "../x", 12, ["x"]):
            with pytest.raises(ErreurReglage, match="etablissement_id"):
                await reglages_agent.regler(1, 7, {"etablissement_id": mauvaise})
        with pytest.raises(ErreurReglage, match="Unknown or forbidden"):
            await reglages_agent.regler(1, 7, {"un_reglage_qui_n_existe_pas": 1})


# --------------------------------------------------------------------------- la connaissance par sujets


async def test_un_sujet_est_un_document_texte_de_l_organisation_idempotent_et_cloisonne(db_session, sans_preparation_des_organisations):  # noqa: F811
    a, b = await creer_organisation(db_session, f"a-{uuid.uuid4().hex[:6]}"), await creer_organisation(db_session, f"b-{uuid.uuid4().hex[:6]}")
    _, jeton_a = await creer_compte(db_session, f"co-{uuid.uuid4().hex[:8]}@example.com", role="Administrateur", organisations=[a])
    _, jeton_b = await creer_compte(db_session, f"co-{uuid.uuid4().hex[:8]}@example.com", role="Administrateur", organisations=[b])
    async with client_http() as c:
        assert (await c.get(RACINE)).status_code == 401
        assert (await c.put(f"{RACINE}/horaires", json={"texte": "x"})).status_code == 401
        ecrit = await c.put(f"{RACINE}/horaires", json={"texte": "Ouvert de onze heures à quatorze heures."}, headers=entetes(jeton_a))
        assert ecrit.status_code == 200 and ecrit.json()["cree"] is True and ecrit.json()["sujet"] == "horaires"
        uuid_ = ecrit.json()["document_uuid"]
        # écrit deux fois : le même document, le texte remplacé
        deux = await c.put(f"{RACINE}/horaires", json={"texte": "Ouvert tous les jours."}, headers=entetes(jeton_a))
        assert deux.json()["document_uuid"] == uuid_ and deux.json()["cree"] is False
        await c.put(f"{RACINE}/paiement", json={"texte": "Carte, espèces, titres-restaurant."}, headers=entetes(jeton_a))
        liste = (await c.get(RACINE, headers=entetes(jeton_a))).json()["sujets"]
        assert [s["sujet"] for s in liste] == ["horaires", "paiement"] and liste[0]["document_uuid"] == uuid_
        # le document est « document entier », complet, avec le dernier texte
        document = await db_client.get_document_by_uuid(uuid_, a)
        assert (document.retrieval_mode, document.processing_status, document.full_text, document.filename) == ("full_document", "completed", "Ouvert tous les jours.", "sujet-horaires.txt")
        # une autre organisation ne voit rien, et ne peut pas lire le document
        assert (await c.get(RACINE, headers=entetes(jeton_b))).json() == {"sujets": []}
        assert await db_client.get_document_by_uuid(uuid_, b) is None
        assert (await c.put(f"{RACINE}/horaires", json={"texte": "Chez B."}, headers=entetes(jeton_b))).json()["cree"] is True  # son propre sujet
        assert (await db_client.get_document_by_uuid(uuid_, a)).full_text == "Ouvert tous les jours."
        # les refus
        assert (await c.put(f"{RACINE}/horaires", json={"texte": "  "}, headers=entetes(jeton_a))).status_code == 422
        assert (await c.put(f"{RACINE}/Horaires Du Soir", json={"texte": "x"}, headers=entetes(jeton_a))).status_code == 422
        assert (await c.put(f"{RACINE}/horaires", json={"texte": "x", "en_trop": 1}, headers=entetes(jeton_a))).status_code == 422
        assert (await c.put(f"{RACINE}/horaires", json={"texte": "x" * 20_001}, headers=entetes(jeton_a))).status_code == 422


def test_les_routes_de_la_connaissance_sont_au_registre_avec_la_bonne_permission():
    lue = registre.decision_de("GET", "/restauration/connaissance")
    ecrite = registre.decision_de("PUT", "/restauration/connaissance/{sujet}")
    assert lue[0].cle == "conversations.voir" and lue[0].pour_cle is None
    assert ecrite[0].cle == "agents.modifier" and ecrite[0].pour_cle is None
