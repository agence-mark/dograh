"""[.mark] Builder partie 2, U2 quinquies (lot H2, E58, E33) : exporter un agent du Labo vers un client, le ramener au Labo.

Vraie application, vraie base de test, vrais rôles. Aucun appel à un tiers (le stockage de fichiers n'est jamais touché).

| Test | Ce qu'il prouve |
|---|---|
| groupe exporté | le groupe entier arrive en brouillon chez le client, l'original est inchangé, les passations suivent les copies |
| rien de la source | aucun identifiant, aucune clé, aucun secret de la source dans la copie (agents, outils, documents, tests, réglages) |
| clé jamais copiée | aucune clé chez la cible ; reliée à la clé du client du même nom, ou vide |
| idempotence | rejoué : la même copie, aucune ligne de plus ; deux appels simultanés : une seule copie |
| ramener | copie en brouillon au Labo, dossier « Copies de clients », outil sans équivalent laissé vide |
| sens | exporter depuis un client, ramener depuis le Labo : refusés |
| cloisonnement | clé d'API, compte sans rôle, organisation source ou cible que le rôle n'ouvre pas, agent d'une autre organisation : refusés |
| choix | un choix hors relevé, une action non permise, un « relier » sans cible : refusés, rien d'écrit |
| défaire | une copie qui échoue en route ne laisse aucun agent actif ni outil actif ni journal ; rejouée ensuite, elle réussit |
| tests | les tests suivent sur demande (sans l'identifiant de la source), les résultats jamais |
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from api.services.builder.constantes import cle_resultats
from api.services.builder.tests_agent import stockage as stockage_tests
from api.services.equipe_mark import espaces
from api.services.groupe import groupe
from api.tests.mark.equipe_commun import (  # noqa: F401
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,
)

E = "/api/v1/export-agent"

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")

SECRET = "SECRET-DU-LABO-1234"


@pytest.fixture(autouse=True)
def _cache_du_labo_propre():
    espaces.reinitialiser_cache()
    yield
    espaces.reinitialiser_cache()


async def _monde(db, suffixe):
    labo = await creer_organisation(db, f"exp-labo-{suffixe}")
    client = await creer_organisation(db, f"exp-client-{suffixe}")
    espaces.reinitialiser_cache()
    await espaces.definir_labo(labo, True)
    admin, jeton = await creer_compte(
        db, f"exp-admin-{suffixe}@example.com", role="Administrateur", organisations=[labo, client]
    )
    return labo, client, admin, jeton


async def _groupe_du_labo(db, labo, admin, *, avec_tests=False):
    """Un principal et un spécialisé, un outil HTTP à clé, un document prêt, un déclencheur, des secrets partout où il peut y en avoir."""
    principal, _ = await groupe.creer_principal(nom="Accueil", organization_id=labo, user_id=admin.id, dossier_parent_id=None)
    specialise = await groupe.creer_specialise(principal_id=principal, nom="Devis", organization_id=labo, user_id=admin.id)
    cle = await db.create_credential(labo, admin.id, "Clé CRM", "api_key", {"header_name": "X-API-Key", "api_key": SECRET})
    outil = await db.create_tool(
        organization_id=labo, user_id=admin.id, name="Prendre un rendez-vous", category="http_api",
        definition={
            "schema_version": 1, "type": "http_api",
            "config": {
                "url": "https://example.org/rdv", "method": "POST", "credential_uuid": cle.credential_uuid,
                "headers": {"Authorization": f"Bearer {SECRET}", "X-Autre": "ok"},
            },
        },
    )
    document = await db.create_document(
        organization_id=labo, created_by=admin.id, filename="tarifs.pdf", file_size_bytes=10, file_hash="h" * 64, mime_type="application/pdf"
    )
    await db.update_document_status(document.id, "completed", total_chunks=0)
    agent = await groupe.lire_agent(principal, labo)
    definition = agent.definition
    premier = definition["nodes"][0]
    premier.setdefault("data", {})["tool_uuids"] = [*(premier["data"].get("tool_uuids") or []), outil.tool_uuid]
    premier["data"]["document_uuids"] = [document.document_uuid]
    definition["nodes"].append({"id": "99", "type": "trigger", "position": {"x": 0, "y": 0}, "data": {"name": "Déclencheur", "trigger_path": "TRIGGER-DU-LABO"}})
    reglages = dict(agent.reglages)
    reglages["organization_id"] = labo
    reglages["model_overrides"] = {"llm": {"api_key": SECRET, "max_tokens": 300}}
    await db.update_workflow(
        workflow_id=principal, name=None, workflow_definition=definition, template_context_variables=None,
        workflow_configurations=reglages, organization_id=labo,
    )
    if avec_tests:
        for agent_id in (principal, specialise):
            await stockage_tests.ecrire(
                labo, agent_id, {"slug": f"t-{agent_id}", "nom": "Un test", "origine": "manuel", "organisation_id": labo}
            )
            await db.upsert_configuration(labo, cle_resultats(agent_id, f"t-{agent_id}"), {"executions": [{"note": 9}]})
    return {"principal": principal, "specialise": specialise, "cle": cle, "outil": outil, "document": document}


def _corps(client, **plus):
    return {"sens": "exporter", "cible_organization_id": client, **plus}


async def _tout_ce_que_la_cible_a_recu(db, organisation, agents):
    """Tout ce qui est écrit chez la cible, sérialisé : agents (brouillon, version publiée, réglages), outils, documents, clés, tests."""
    morceaux = []
    for agent_id in agents:
        agent = await groupe.lire_agent(agent_id, organisation)
        morceaux.append(json.dumps([agent.definition, agent.reglages, agent.variables], default=str))
        workflow = await db.get_workflow(agent_id, organization_id=organisation)
        morceaux.append(json.dumps([workflow.released_definition.workflow_json, workflow.released_definition.workflow_configurations], default=str))
        morceaux.append(json.dumps(await stockage_tests.lister(organisation, agent_id), default=str))
    for outil in await db.get_tools_for_organization(organisation):
        morceaux.append(json.dumps([outil.name, outil.definition], default=str))
    for document in await db.get_documents_for_organization(organisation):
        morceaux.append(json.dumps([document.filename, document.custom_metadata, document.docling_metadata], default=str))
    return "\n".join(morceaux)


async def test_un_groupe_est_exporte_en_brouillon_et_l_original_ne_bouge_pas(db_session):
    labo, client, admin, jeton = await _monde(db_session, "gr")
    src = await _groupe_du_labo(db_session, labo, admin)
    avant = await groupe.lire_agent(src["principal"], labo)
    async with client_http() as c:
        reponse = await c.post(f"{E}/{src['principal']}/copier", json=_corps(client), headers=entetes(jeton, labo))
    assert reponse.status_code == 200, reponse.text
    compte = reponse.json()
    assert compte["deja_copie"] is False and len(compte["agents"]) == 2
    nouveaux = [a["id"] for a in compte["agents"]]
    principal_neuf, specialise_neuf = compte["agent_id"], [i for i in nouveaux if i != compte["agent_id"]][0]

    # Brouillon : la version publiée est le squelette de création, la vraie définition est un brouillon.
    assert await db_session.get_draft_version(principal_neuf) is not None
    assert await db_session.workflow_a_ete_publie(principal_neuf) is False
    copie = await groupe.lire_agent(principal_neuf, client)
    assert copie.a_un_brouillon and groupe.specialises_de(copie.reglages) == [specialise_neuf]
    assert (await groupe.lire_agent(specialise_neuf, client)).reglages[groupe.CLE_AGENT_PRINCIPAL] == principal_neuf

    # Les passations suivent les copies.
    passations = [o for o in await db_session.get_tools_for_organization(client) if o.category == "transfer_agent"]
    assert [o.definition["config"]["workflow_id"] for o in passations] == [specialise_neuf]
    # Le déclencheur est neuf, l'original est intact.
    declencheurs = [n["data"]["trigger_path"] for n in copie.definition["nodes"] if n.get("type") == "trigger"]
    assert declencheurs and declencheurs != ["TRIGGER-DU-LABO"]
    apres = await groupe.lire_agent(src["principal"], labo)
    assert apres.definition == avant.definition and apres.reglages == avant.reglages
    assert (await db_session.get_workflow(src["principal"], organization_id=labo)).status == "active"


async def test_rien_de_la_source_ne_reste_dans_la_copie(db_session):
    labo, client, admin, jeton = await _monde(db_session, "ri")
    src = await _groupe_du_labo(db_session, labo, admin, avec_tests=True)
    async with client_http() as c:
        compte = (await c.post(f"{E}/{src['principal']}/copier", json=_corps(client), headers=entetes(jeton, labo))).json()
    nouveaux = [a["id"] for a in compte["agents"]]
    brut = await _tout_ce_que_la_cible_a_recu(db_session, client, nouveaux)
    interdits = [
        SECRET, "TRIGGER-DU-LABO", src["outil"].tool_uuid, src["document"].document_uuid, src["cle"].credential_uuid,
        f"\"organization_id\": {labo}", *[f"\"workflow_id\": {i}" for i in (src["principal"], src["specialise"])],
    ]
    for interdit in interdits:
        assert interdit not in brut, interdit
    assert compte["secrets_retires"] >= 2
    # Les valeurs qui ne sont pas des secrets voyagent (max_tokens n'est pas un secret).
    assert "max_tokens" in brut and "X-Autre" in brut
    # Le document est copié (identifiant neuf), l'outil à clé l'est aussi, sans sa clé ni son secret.
    assert [d.filename for d in await db_session.get_documents_for_organization(client)] == ["tarifs.pdf"]
    assert [o.name for o in await db_session.get_tools_for_organization(client) if o.category == "http_api"] == ["Prendre un rendez-vous"]


async def test_une_cle_n_est_jamais_copiee_elle_est_reliee_par_son_nom(db_session):
    labo, client, admin, jeton = await _monde(db_session, "cl")
    src = await _groupe_du_labo(db_session, labo, admin)
    async with client_http() as c:
        releve = (await c.get(f"{E}/{src['principal']}/releve", params={"sens": "exporter", "cible": client}, headers=entetes(jeton, labo))).json()
        ligne = next(e for e in releve["elements"] if e["type"] == "cle")
        assert ligne["choix"] == ["vide"] and ligne["defaut"] == "vide"  # le client n'a pas de clé : rien à relier

        cle_client = await db_session.create_credential(client, admin.id, "Clé CRM", "api_key", {"api_key": "AUTRE-VALEUR"})
        releve = (await c.get(f"{E}/{src['principal']}/releve", params={"sens": "exporter", "cible": client}, headers=entetes(jeton, labo))).json()
        ligne = next(e for e in releve["elements"] if e["type"] == "cle")
        assert ligne["defaut"] == "relier" and ligne["cible_par_defaut"] == cle_client.credential_uuid
        compte = (await c.post(f"{E}/{src['principal']}/copier", json=_corps(client), headers=entetes(jeton, labo))).json()
    assert len(await db_session.get_credentials_for_organization(client)) == 1  # aucune clé de plus chez le client
    outil = next(o for o in await db_session.get_tools_for_organization(client) if o.category == "http_api")
    assert outil.definition["config"]["credential_uuid"] == cle_client.credential_uuid
    assert compte["agent_id"]


async def test_rejouee_la_copie_n_est_pas_refaite(db_session):
    labo, client, admin, jeton = await _monde(db_session, "id")
    src = await _groupe_du_labo(db_session, labo, admin)
    async with client_http() as c:
        premiere = (await c.post(f"{E}/{src['principal']}/copier", json=_corps(client), headers=entetes(jeton, labo))).json()
        compte_avant = (len(await db_session.get_all_workflows(organization_id=client)), len(await db_session.get_tools_for_organization(client)))
        seconde = (await c.post(f"{E}/{src['principal']}/copier", json=_corps(client), headers=entetes(jeton, labo))).json()
        cibles = (await c.get(f"{E}/{src['principal']}/cibles", params={"sens": "exporter"}, headers=entetes(jeton, labo))).json()
    assert seconde["deja_copie"] is True and seconde["agent_id"] == premiere["agent_id"]
    assert compte_avant == (len(await db_session.get_all_workflows(organization_id=client)), len(await db_session.get_tools_for_organization(client)))
    ligne = next(x for x in cibles["cibles"] if x["id"] == client)
    assert ligne["deja_copie"]["agent_id"] == premiere["agent_id"]
    assert [x["id"] for x in cibles["cibles"]] == [client]  # le Labo n'est pas une cible de l'export
    # Une copie archivée n'est plus « déjà copiée » : on peut la refaire.
    for a in premiere["agents"]:
        await db_session.update_workflow_status(workflow_id=a["id"], status="archived", organization_id=client)
    async with client_http() as c:
        refaite = (await c.post(f"{E}/{src['principal']}/copier", json=_corps(client), headers=entetes(jeton, labo))).json()
    assert refaite["deja_copie"] is False and refaite["agent_id"] != premiere["agent_id"]


async def test_le_journal_est_lu_et_ecrit_sous_le_verrou_de_la_copie(db_session):
    """Deux copies identiques s'attendent : la seconde, entrée après la première, trouve la ligne du journal et ne refait rien.

    (Le banc de test partage une seule connexion : on prouve l'ordre, lecture du journal puis écriture, DANS le verrou.)"""
    from contextlib import asynccontextmanager

    from api.services.export_agent import registre

    labo, client, admin, jeton = await _monde(db_session, "si")
    src = await _groupe_du_labo(db_session, labo, admin)
    evenements: list[str] = []
    vrai_verrou, vraie_lecture, vraie_note = registre.verrou, registre.lire, registre.noter

    @asynccontextmanager
    async def verrou(*args):
        evenements.append("verrou:entre")
        async with vrai_verrou(*args):
            yield
        evenements.append("verrou:sort")

    async def lire(*args):
        evenements.append("journal:lit")
        return await vraie_lecture(*args)

    async def noter(*args):
        evenements.append("journal:ecrit")
        return await vraie_note(*args)

    with patch.object(registre, "verrou", verrou), patch.object(registre, "lire", lire), patch.object(registre, "noter", noter):
        async with client_http() as c:
            await c.post(f"{E}/{src['principal']}/copier", json=_corps(client), headers=entetes(jeton, labo))
    assert evenements == ["verrou:entre", "journal:lit", "journal:ecrit", "verrou:sort"]


async def test_ramener_au_labo_en_brouillon_dans_le_dossier_des_copies(db_session):
    labo, client, admin, jeton = await _monde(db_session, "ra")
    # Un agent du client avec un outil qui n'a pas d'équivalent au Labo, et un qui en a un.
    principal, _ = await groupe.creer_principal(nom="Standard", organization_id=client, user_id=admin.id, dossier_parent_id=None)
    seul = await db_session.create_tool(
        organization_id=client, user_id=admin.id, name="Outil du client", category="http_api",
        definition={"schema_version": 1, "type": "http_api", "config": {"url": "https://client.example/x", "method": "GET"}},
    )
    commun_client = await db_session.create_tool(
        organization_id=client, user_id=admin.id, name="Agenda", category="http_api",
        definition={"schema_version": 1, "type": "http_api", "config": {"url": "https://client.example/agenda", "method": "GET"}},
    )
    commun_labo = await db_session.create_tool(
        organization_id=labo, user_id=admin.id, name="Agenda", category="http_api",
        definition={"schema_version": 1, "type": "http_api", "config": {"url": "https://labo.example/agenda", "method": "GET"}},
    )
    agent = await groupe.lire_agent(principal, client)
    definition = agent.definition
    definition["nodes"][0].setdefault("data", {})["tool_uuids"] = [seul.tool_uuid, commun_client.tool_uuid]
    await db_session.update_workflow(workflow_id=principal, name=None, workflow_definition=definition, template_context_variables=None, workflow_configurations=None, organization_id=client)

    async with client_http() as c:
        h = entetes(jeton, client)
        releve = (await c.get(f"{E}/{principal}/releve", params={"sens": "ramener", "cible": labo}, headers=h)).json()
        par_nom = {e["nom"]: e for e in releve["elements"] if e["type"] == "outil"}
        assert par_nom["Outil du client"]["defaut"] == "vide"  # ce qui appartient au client reste chez lui
        assert par_nom["Agenda"]["defaut"] == "relier" and par_nom["Agenda"]["cible_par_defaut"] == commun_labo.tool_uuid
        reponse = await c.post(f"{E}/{principal}/copier", json={"sens": "ramener", "cible_organization_id": labo}, headers=h)
    assert reponse.status_code == 200, reponse.text
    compte = reponse.json()
    copie = await groupe.lire_agent(compte["agent_id"], labo)
    assert copie.a_un_brouillon and await db_session.workflow_a_ete_publie(copie.id) is False
    assert copie.nom.startswith("Standard (") and compte["dossier_id"]
    dossier = await db_session.get_folder(compte["dossier_id"], organization_id=labo)
    assert dossier.name == "Copies de clients"
    assert copie.definition["nodes"][0]["data"]["tool_uuids"] == [commun_labo.tool_uuid]
    # Rien du client n'est resté, l'original non plus n'a pas bougé.
    brut = await _tout_ce_que_la_cible_a_recu(db_session, labo, [copie.id])
    assert seul.tool_uuid not in brut and commun_client.tool_uuid not in brut and "client.example" not in brut
    assert (await groupe.lire_agent(principal, client)).definition == definition


async def test_le_sens_est_controle_cote_serveur(db_session):
    labo, client, admin, jeton = await _monde(db_session, "se")
    src = await _groupe_du_labo(db_session, labo, admin)
    autre_client = await creer_organisation(db_session, "exp-client-se2")
    agent_client, _ = await groupe.creer_principal(nom="Chez le client", organization_id=client, user_id=admin.id, dossier_parent_id=None)
    async with client_http() as c:
        # Ramener un agent du Labo, ou exporter vers le Labo : refusé.
        r1 = await c.post(f"{E}/{src['principal']}/copier", json={"sens": "ramener", "cible_organization_id": client}, headers=entetes(jeton, labo))
        r2 = await c.post(f"{E}/{src['principal']}/copier", json={"sens": "exporter", "cible_organization_id": labo}, headers=entetes(jeton, labo))
        # Exporter un agent d'un client, ou le copier d'un client à un autre : refusé.
        r3 = await c.post(f"{E}/{agent_client}/copier", json={"sens": "exporter", "cible_organization_id": autre_client}, headers=entetes(jeton, client))
        r4 = await c.post(f"{E}/{agent_client}/copier", json={"sens": "ramener", "cible_organization_id": autre_client}, headers=entetes(jeton, client))
        r5 = await c.post(f"{E}/{src['principal']}/copier", json=_corps(labo), headers=entetes(jeton, labo))
    assert [r.status_code for r in (r1, r2, r3, r4, r5)] == [422] * 5
    assert await db_session.get_all_workflows(organization_id=autre_client) == []
    # Un spécialisé ne se copie pas seul.
    async with client_http() as c:
        seul = await c.post(f"{E}/{src['specialise']}/copier", json=_corps(client), headers=entetes(jeton, labo))
    assert seul.status_code == 409


async def test_le_cloisonnement_refuse_cle_compte_sans_role_et_organisation_fermee(db_session):
    labo, client, admin, jeton = await _monde(db_session, "cn")
    src = await _groupe_du_labo(db_session, labo, admin)
    ferme = await creer_organisation(db_session, "exp-client-ferme")
    etranger = await creer_organisation(db_session, "exp-etranger")
    corps = _corps(client)

    # Une clé d'API (même celle du Labo) n'exporte ni ne ramène.
    _m, cle_brute = await db_session.create_api_key(labo, "portail", created_by=admin.id)
    async with client_http() as c:
        for chemin, methode in ((f"{E}/{src['principal']}/copier", "post"), (f"{E}/{src['principal']}/releve?sens=exporter&cible={client}", "get"), (f"{E}/{src['principal']}/cibles?sens=exporter", "get")):
            r = await getattr(c, methode)(chemin, headers={"X-API-Key": cle_brute}, **({"json": corps} if methode == "post" else {}))
            assert r.status_code == 403, (chemin, r.status_code)

    # Un compte sans rôle d'équipe.
    simple, jeton_simple = await creer_compte(db_session, "exp-simple@example.com", organisations=[labo])
    async with client_http() as c:
        assert (await c.post(f"{E}/{src['principal']}/copier", json=corps, headers=entetes(jeton_simple, labo))).status_code == 403

    # Un rôle sans la permission d'exporter.
    sans = await db_session.creer_role(nom="Sans-export-test", labo_ouvert=True, tous_les_clients=True, permissions=["agents.modifier"], organisations=[])
    membre, jeton_sans = await creer_compte(db_session, "exp-sans@example.com", organisations=[labo, client])
    await db_session.poser_membre(membre.id, sans)
    async with client_http() as c:
        assert (await c.post(f"{E}/{src['principal']}/copier", json=corps, headers=entetes(jeton_sans, labo))).status_code == 403

    # Un rôle qui n'ouvre que le client, pas le Labo : l'organisation source (l'adresse) lui est refusée.
    que_client = await db_session.creer_role(nom="Client-seul-test", labo_ouvert=False, tous_les_clients=False, permissions=["clients.exporter_ramener"], organisations=[client])
    seul, jeton_seul = await creer_compte(db_session, "exp-seul@example.com", organisations=[client])
    await db_session.poser_membre(seul.id, que_client)
    async with client_http() as c:
        assert (await c.post(f"{E}/{src['principal']}/copier", json=corps, headers=entetes(jeton_seul, labo))).status_code == 403

    # Un rôle qui ouvre le Labo et UN client : toute autre cible est un 404, et rien n'y est écrit.
    un_client = await db_session.creer_role(nom="Un-client-test", labo_ouvert=True, tous_les_clients=False, permissions=["clients.exporter_ramener"], organisations=[client])
    borne, jeton_borne = await creer_compte(db_session, "exp-borne@example.com", organisations=[labo, client, ferme])
    await db_session.poser_membre(borne.id, un_client)
    async with client_http() as c:
        h = entetes(jeton_borne, labo)
        assert (await c.post(f"{E}/{src['principal']}/copier", json=_corps(ferme), headers=h)).status_code == 404
        assert (await c.get(f"{E}/{src['principal']}/releve", params={"sens": "exporter", "cible": ferme}, headers=h)).status_code == 404
        assert (await c.post(f"{E}/{src['principal']}/copier", json=_corps(etranger), headers=h)).status_code == 404
        cibles = (await c.get(f"{E}/{src['principal']}/cibles", params={"sens": "exporter"}, headers=h)).json()
        assert [x["id"] for x in cibles["cibles"]] == [client]
    assert await db_session.get_all_workflows(organization_id=ferme) == []
    assert await db_session.get_all_workflows(organization_id=etranger) == []

    # Un agent d'une autre organisation que celle de l'adresse n'existe pas.
    async with client_http() as c:
        r = await c.post(f"{E}/{src['principal']}/copier", json={"sens": "ramener", "cible_organization_id": labo}, headers=entetes(jeton, client))
        assert r.status_code == 404
        r = await c.get(f"{E}/{src['principal']}/cibles", params={"sens": "exporter"}, headers=entetes(jeton, client))
        assert r.status_code == 404


async def test_les_choix_sont_revalides_contre_le_releve(db_session):
    labo, client, admin, jeton = await _monde(db_session, "ch")
    src = await _groupe_du_labo(db_session, labo, admin)
    async with client_http() as c:
        h = entetes(jeton, labo)
        cas = [
            {"type": "outil", "ref": "inconnu-du-releve", "action": "copier"},  # hors relevé
            {"type": "cle", "ref": src["cle"].credential_uuid, "action": "copier"},  # une clé ne se copie pas
            {"type": "outil", "ref": src["outil"].tool_uuid, "action": "relier"},  # relier sans équivalent
            {"type": "outil", "ref": src["outil"].tool_uuid, "action": "relier", "cible": "ailleurs"},
            {"type": "agent", "ref": str(src["principal"]), "action": "vide"},  # un agent se copie toujours
        ]
        for choix in cas:
            r = await c.post(f"{E}/{src['principal']}/copier", json=_corps(client, choix=[choix]), headers=h)
            assert r.status_code == 422, (choix, r.status_code)
        # Relier à un outil d'une AUTRE organisation que la cible est refusé aussi.
        autre = await creer_organisation(db_session, "exp-autre-ch")
        etranger = await db_session.create_tool(organization_id=autre, user_id=admin.id, name="Prendre un rendez-vous", category="http_api", definition={"schema_version": 1, "type": "http_api", "config": {}})
        r = await c.post(f"{E}/{src['principal']}/copier", json=_corps(client, choix=[{"type": "outil", "ref": src["outil"].tool_uuid, "action": "relier", "cible": etranger.tool_uuid}]), headers=h)
        assert r.status_code == 422
    assert await db_session.get_all_workflows(organization_id=client) == []
    assert await db_session.get_tools_for_organization(client) == []


async def test_un_outil_laisse_vide_et_un_document_laisse_vide_ne_sont_pas_copies(db_session):
    labo, client, admin, jeton = await _monde(db_session, "vi")
    src = await _groupe_du_labo(db_session, labo, admin)
    choix = [
        {"type": "outil", "ref": src["outil"].tool_uuid, "action": "vide"},
        {"type": "document", "ref": src["document"].document_uuid, "action": "vide"},
    ]
    async with client_http() as c:
        compte = (await c.post(f"{E}/{src['principal']}/copier", json=_corps(client, choix=choix), headers=entetes(jeton, labo))).json()
    assert await db_session.get_documents_for_organization(client) == []
    assert [o.category for o in await db_session.get_tools_for_organization(client)] == ["transfer_agent"]
    copie = await groupe.lire_agent(compte["agent_id"], client)
    donnees = copie.definition["nodes"][0]["data"]
    assert src["outil"].tool_uuid not in donnees.get("tool_uuids", []) and donnees.get("document_uuids") == []


async def test_une_copie_qui_echoue_est_defaite_puis_rejouable(db_session):
    labo, client, admin, jeton = await _monde(db_session, "de")
    src = await _groupe_du_labo(db_session, labo, admin)
    vraie = db_session.update_workflow
    appels = {"n": 0}

    async def casse_a_la_seconde_ecriture(*args, **kwargs):
        if kwargs.get("organization_id") == client and kwargs.get("workflow_definition") is not None:
            appels["n"] += 1
            if appels["n"] == 2:
                raise RuntimeError("panne simulee")
        return await vraie(*args, **kwargs)

    async with client_http() as c:
        with patch.object(type(db_session), "update_workflow", side_effect=casse_a_la_seconde_ecriture, autospec=False) as faux:
            faux.side_effect = casse_a_la_seconde_ecriture
            r = await c.post(f"{E}/{src['principal']}/copier", json=_corps(client), headers=entetes(jeton, labo))
    assert r.status_code == 500 and "panne" not in r.text  # jamais le texte interne
    assert [w for w in await db_session.get_all_workflows(organization_id=client) if w.status == "active"] == []
    assert await db_session.get_tools_for_organization(client) == []
    assert await db_session.get_documents_for_organization(client) == []
    async with client_http() as c:
        r = await c.post(f"{E}/{src['principal']}/copier", json=_corps(client), headers=entetes(jeton, labo))
    assert r.status_code == 200 and r.json()["deja_copie"] is False


async def test_les_tests_suivent_sur_demande_jamais_leurs_resultats(db_session):
    labo, client, admin, jeton = await _monde(db_session, "te")
    src = await _groupe_du_labo(db_session, labo, admin, avec_tests=True)
    async with client_http() as c:
        releve = (await c.get(f"{E}/{src['principal']}/releve", params={"sens": "exporter", "cible": client}, headers=entetes(jeton, labo))).json()
        assert releve["nb_tests"] == 2
        sans = await c.post(f"{E}/{src['principal']}/copier", json=_corps(client, avec_tests=False), headers=entetes(jeton, labo))
    assert sans.json()["tests_copies"] == 0
    assert await stockage_tests.lister(client, sans.json()["agent_id"]) == []
    for a in sans.json()["agents"]:
        await db_session.update_workflow_status(workflow_id=a["id"], status="archived", organization_id=client)
    async with client_http() as c:
        avec = (await c.post(f"{E}/{src['principal']}/copier", json=_corps(client), headers=entetes(jeton, labo))).json()
    assert avec["tests_copies"] == 2
    tests = await stockage_tests.lister(client, avec["agent_id"])
    assert len(tests) == 1 and "organisation_id" not in tests[0]
    lignes = await db_session.get_configurations_by_prefix(client, "MARK_TESTS_RESULTATS:")
    assert lignes == []


async def test_le_geste_est_journalise_sans_secret(db_session):
    labo, client, admin, jeton = await _monde(db_session, "jo")
    src = await _groupe_du_labo(db_session, labo, admin)
    async with client_http() as c:
        await c.post(f"{E}/{src['principal']}/copier", json=_corps(client), headers=entetes(jeton, labo))
    lignes, _ = await db_session.lister_journal(limit=50, offset=0, organization_id=client)
    exporte = [l for l in lignes if l["action"] == "agent.exporter"]
    assert len(exporte) == 1  # qui, quoi, où : le compte, l'action, l'organisation de la copie
    brut = json.dumps(lignes, default=str)
    assert SECRET not in brut and src["cle"].credential_uuid not in brut


async def test_dupliquer_avec_ses_tests_dans_la_meme_organisation(db_session):
    labo, _client, admin, jeton = await _monde(db_session, "du")
    src = await _groupe_du_labo(db_session, labo, admin, avec_tests=True)
    async with client_http() as c:
        r = await c.post(f"/api/v1/workflow/{src['principal']}/duplicate", params={"avec_tests": "true"}, headers=entetes(jeton, labo))
    assert r.status_code == 200, r.text
    avec = r.json()
    assert [t["slug"] for t in await stockage_tests.lister(labo, avec["id"])] == [f"t-{src['principal']}"]
    copie = await groupe.lire_agent(avec["id"], labo)
    (specialise_copie,) = groupe.specialises_de(copie.reglages)
    assert [t["slug"] for t in await stockage_tests.lister(labo, specialise_copie)] == [f"t-{src['specialise']}"]
    # Les résultats ne suivent jamais ; l'original garde ses tests.
    assert await db_session.get_configurations_by_prefix(labo, f"MARK_TESTS_RESULTATS:{avec['id']}:") == []
    assert len(await stockage_tests.lister(labo, src["principal"])) == 1


async def test_dupliquer_sans_les_tests_ne_les_recopie_pas(db_session):
    labo, _client, admin, jeton = await _monde(db_session, "du2")
    seul = (await db_session.create_workflow("Seul", groupe.graphe_minimal_du_specialise(), admin.id, labo)).id
    await stockage_tests.ecrire(labo, seul, {"slug": "t-seul", "nom": "Un test", "origine": "manuel"})
    async with client_http() as c:
        r = await c.post(f"/api/v1/workflow/{seul}/duplicate", headers=entetes(jeton, labo))
    assert r.status_code == 200, r.text
    assert await stockage_tests.lister(labo, r.json()["id"]) == []
    assert len(await stockage_tests.lister(labo, seul)) == 1
