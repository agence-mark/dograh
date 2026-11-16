"""[.mark] Module Restauration, lot 11 (E-22, E-46) : les dossiers d'outils et les kits d'outils.

Les routes sont jouées par le VRAI routeur sur la base de test ; chaque test relit ensuite ce que la base dit (R1).

| Test | Ce qu'il prouve |
|---|---|
| dossiers | créer, renommer, déplacer ; deux niveaux au plus ; un nom pris au même endroit refusé |
| suppression | supprimer un dossier supprime ses sous-dossiers et AUCUN outil (ils repassent sans dossier) |
| organisation | un dossier d'une autre organisation n'est jamais lu, écrit ni visé par un outil |
| rangement | ranger un outil ne crée aucune version d'outil et n'écrit rien dans sa définition (jamais envoyé au modèle) |
| kit livré | trois kits posés d'après le catalogue, idempotent, définitions valides, aucune action d'envoi dans Commande |
| kit : écriture | écrire un kit est un geste de l'équipe au Labo ; un kit refuse un outil à adresse ou identifiant de client |
| kit : application | un kit copie ses outils dans l'organisation, une fois ; changer un outil du kit ne change AUCUN outil ni agent qui ne l'a pas accepté |
| kit : proposition | la version plus récente est proposée ; l'accepter crée une version d'outil, garde le compte de l'organisation, et un agent reste sur sa version |
| vocabulaire | aucun mot de métier dans les mécanismes communs (dossiers, kits) |
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import select

from api.db.models import ToolFolderModel, ToolModel
from api.enums import ToolCategory
from api.schemas.tool import IntegrationToolDefinition
from api.services.outils_mark import kits_livres
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401  (fixtures)
from api.tests.mark.test_outils_versions import _agent, _graphe, _publier  # noqa: F401
from api.tests.mark.test_sous_dossiers_et_groupe import _oublier, autre_org, org  # noqa: F401


@pytest.fixture
def equipe_au_labo(monkeypatch):
    """Le geste de l'équipe est contrôlé ailleurs (bibliothèque) : ici on le laisse passer pour jouer les routes des kits."""
    from api.services.builder.bibliotheque import droits

    async def _ok(_user):
        return None

    monkeypatch.setattr(droits, "exiger_l_equipe_au_labo", _ok)


def _definition(action="ajouter", compte=None):
    config = {"connecteur": "commande", "action": action}
    if compte:
        config["compte"] = compte
    return {"schema_version": 1, "type": "integration", "config": config}


async def _outil(db, org, nom="ajouter", compte=None, categorie=ToolCategory.INTEGRATION.value, definition=None):
    return await db.create_tool(
        organization_id=org.organisation.id,
        user_id=org.utilisateur.id,
        name=nom,
        definition=definition or _definition(nom, compte),
        category=categorie,
        description="Ajoute à la commande.",
    )


# --- dossiers -------------------------------------------------------------------------------------------------------------------


async def test_dossiers_creation_renommage_deplacement_et_deux_niveaux(org, db_session, test_client_factory):
    OID = org.organisation.id
    async with test_client_factory(org.utilisateur) as client:
        a = (await client.post("/api/v1/tools/dossiers", json={"name": "A"})).json()
        b = (await client.post("/api/v1/tools/dossiers", json={"name": "B", "parent_id": a["id"]})).json()
        assert b["parent_id"] == a["id"]
        # Un troisième niveau : refusé.
        trop = await client.post("/api/v1/tools/dossiers", json={"name": "C", "parent_id": b["id"]})
        assert trop.status_code == 422
        # Même nom au même endroit : refusé ; le même nom sous un autre parent : permis.
        assert (await client.post("/api/v1/tools/dossiers", json={"name": "A"})).status_code == 409
        assert (await client.post("/api/v1/tools/dossiers", json={"name": "B"})).status_code == 200
        # Renommer.
        r = await client.patch(f"/api/v1/tools/dossiers/{b['id']}", json={"name": "B2"})
        assert r.json()["name"] == "B2"
        # Un dossier qui porte un sous-dossier ne passe pas sous un autre.
        autre = (await client.post("/api/v1/tools/dossiers", json={"name": "Z"})).json()
        assert (await client.put(f"/api/v1/tools/dossiers/{a['id']}/parent", json={"parent_id": autre["id"]})).status_code == 422
        # Un dossier ne devient pas son propre parent.
        assert (await client.put(f"/api/v1/tools/dossiers/{a['id']}/parent", json={"parent_id": a["id"]})).status_code == 409
        # Remonter au premier niveau.
        r = await client.put(f"/api/v1/tools/dossiers/{b['id']}/parent", json={"parent_id": None})
        assert r.json()["parent_id"] is None
    liste = await db_session.lister_dossiers_d_outils(OID)
    assert {d["name"]: d["parent_id"] for d in liste if d["name"] != "B"} == {"A": None, "B2": None, "Z": None}


async def test_supprimer_un_dossier_supprime_ses_sous_dossiers_et_aucun_outil(org, db_session, test_client_factory):
    OID = org.organisation.id
    outil_a = await _outil(db_session, org, "ajouter")
    outil_b = await _outil(db_session, org, "retirer")
    async with test_client_factory(org.utilisateur) as client:
        a = (await client.post("/api/v1/tools/dossiers", json={"name": "A"})).json()
        b = (await client.post("/api/v1/tools/dossiers", json={"name": "B", "parent_id": a["id"]})).json()
        await client.put(f"/api/v1/tools/{outil_a.tool_uuid}/dossier", json={"dossier_id": a["id"]})
        await client.put(f"/api/v1/tools/{outil_b.tool_uuid}/dossier", json={"dossier_id": b["id"]})
        compte = {d["id"]: d["tool_count"] for d in (await client.get("/api/v1/tools/dossiers")).json()}
        assert compte == {a["id"]: 1, b["id"]: 1}
        r = await client.delete(f"/api/v1/tools/dossiers/{a['id']}")
        assert r.status_code == 200 and r.json()["dossiers"] == 2 and r.json()["outils_sortis"] == 2
    base = await db_session.get_tool_by_uuid(outil_a.tool_uuid, OID)
    base_b = await db_session.get_tool_by_uuid(outil_b.tool_uuid, OID)
    assert base is not None and base.folder_id is None, "l'outil existe toujours, sans dossier"
    assert base_b is not None and base_b.folder_id is None
    assert await db_session.lister_dossiers_d_outils(OID) == []


async def test_un_dossier_d_une_autre_organisation_n_existe_pas(org, autre_org, db_session, test_client_factory):
    AID = autre_org.organisation.id
    async with test_client_factory(autre_org.utilisateur) as client:
        etranger = (await client.post("/api/v1/tools/dossiers", json={"name": "Etranger"})).json()
        outil_etranger = await _outil(db_session, autre_org, "voir_commande")
    mien = await _outil(db_session, org, "ajouter")
    async with test_client_factory(org.utilisateur) as client:
        assert (await client.get("/api/v1/tools/dossiers")).json() == []
        assert (await client.post("/api/v1/tools/dossiers", json={"name": "X", "parent_id": etranger["id"]})).status_code == 404
        assert (await client.patch(f"/api/v1/tools/dossiers/{etranger['id']}", json={"name": "Pris"})).status_code == 404
        assert (await client.delete(f"/api/v1/tools/dossiers/{etranger['id']}")).status_code == 404
        # Ranger MON outil dans SON dossier, ou SON outil dans mon dossier : 404.
        assert (await client.put(f"/api/v1/tools/{mien.tool_uuid}/dossier", json={"dossier_id": etranger["id"]})).status_code == 404
        mon_dossier = (await client.post("/api/v1/tools/dossiers", json={"name": "Mien"})).json()
        assert (
            await client.put(f"/api/v1/tools/{outil_etranger.tool_uuid}/dossier", json={"dossier_id": mon_dossier["id"]})
        ).status_code == 404
    lignes = (await db_session.lister_dossiers_d_outils(AID))
    assert [d["name"] for d in lignes] == ["Etranger"], "le dossier de l'autre organisation n'a pas bougé"


async def test_ranger_un_outil_ne_cree_pas_de_version_et_n_ecrit_rien_dans_sa_definition(org, db_session, test_client_factory):
    OID = org.organisation.id
    outil = await _outil(db_session, org, "ajouter")
    avant = dict(outil.definition)
    async with test_client_factory(org.utilisateur) as client:
        d = (await client.post("/api/v1/tools/dossiers", json={"name": "Rangement"})).json()
        r = await client.put(f"/api/v1/tools/{outil.tool_uuid}/dossier", json={"dossier_id": d["id"]})
        assert r.json() == {"tool_uuid": outil.tool_uuid, "dossier_id": d["id"]}
        liste = (await client.get("/api/v1/tools/")).json()
    ligne = next(t for t in liste if t["tool_uuid"] == outil.tool_uuid)
    assert ligne["folder_id"] == d["id"], "l'écran lit le dossier"
    assert ligne["definition"] == avant, "la définition (ce que l'agent lit) n'a pas changé"
    assert "folder" not in str(ligne["definition"]).lower()
    relu = await db_session.get_tool_by_uuid(outil.tool_uuid, OID)
    assert relu.version_courante == 1, "ranger n'est pas un changement de l'outil"
    async with test_client_factory(org.utilisateur) as client:
        sortie = await client.put(f"/api/v1/tools/{outil.tool_uuid}/dossier", json={"dossier_id": None})
        assert sortie.json()["dossier_id"] is None


# --- kits livrés ----------------------------------------------------------------------------------------------------------------


async def test_les_kits_livres_sont_poses_d_apres_le_catalogue_sans_doublon(db_session):
    # La base de test n'a pas de kit : on les pose, puis on rejoue (aucun doublon).
    premier = await kits_livres.poser_les_kits_livres()
    assert set(premier) == {"Commande", "Réservation", "Envois"}
    second = await kits_livres.poser_les_kits_livres()
    assert all(v["kit_cree"] == 0 and v["outils_ajoutes"] == 0 for v in second.values())
    kits = {k["name"]: k for k in await db_session.lister_les_kits()}
    noms_commande = {i["name"] for i in kits["Commande"]["items"]}
    assert "envoyer_un_message" not in noms_commande and "finaliser" in noms_commande and len(noms_commande) == 15
    assert [i["name"] for i in kits["Envois"]["items"]] == ["envoyer_un_message"]
    assert {i["name"] for i in kits["Réservation"]["items"]} >= {"disponibilites", "reserver", "annuler_reservation"}
    for kit in kits.values():
        for item in kit["items"]:
            IntegrationToolDefinition.model_validate(item["definition"])
            assert item["category"] == "integration" and item["version"] == 1


# --- kits : écriture ------------------------------------------------------------------------------------------------------------


async def test_ecrire_un_kit_est_un_geste_de_l_equipe_au_labo(org, test_client_factory, monkeypatch):
    monkeypatch.setenv("MARK_BIBLIOTHEQUE_ORGANISATION_ID", "999999")
    async with test_client_factory(org.utilisateur) as client:
        refus = await client.post("/api/v1/tools/kits", json={"name": "Perso"})
        assert refus.status_code in (401, 403), refus.text
        # Lire reste ouvert à tout membre.
        assert (await client.get("/api/v1/tools/kits")).status_code == 200


async def test_un_kit_refuse_un_outil_a_adresse_et_retire_le_compte(org, db_session, test_client_factory, equipe_au_labo):
    http = await _outil(
        db_session, org, "appel", categorie=ToolCategory.HTTP_API.value,
        definition={"schema_version": 1, "type": "http_api", "config": {"method": "POST", "url": "https://x.example.test", "parameters": []}},
    )
    integration = await _outil(db_session, org, "ajouter", compte="Compte du client")
    async with test_client_factory(org.utilisateur) as client:
        kit = (await client.post("/api/v1/tools/kits", json={"name": "Mon kit"})).json()
        refus = await client.post(f"/api/v1/tools/kits/{kit['id']}/outils", json={"tool_uuid": http.tool_uuid})
        assert refus.status_code == 422
        ok = await client.post(f"/api/v1/tools/kits/{kit['id']}/outils", json={"tool_uuid": integration.tool_uuid})
        assert ok.status_code == 200
        item = ok.json()["items"][0]
        assert "compte" not in item["definition"]["config"], "le compte d'un client ne part jamais dans un kit"
        # Le même nom deux fois dans un kit : refusé.
        assert (await client.post(f"/api/v1/tools/kits/{kit['id']}/outils", json={"tool_uuid": integration.tool_uuid})).status_code == 409
        # Un outil d'une autre organisation ne se met pas dans un kit.
        assert (await client.post(f"/api/v1/tools/kits/{kit['id']}/outils", json={"tool_uuid": "inconnu"})).status_code == 404
        # Renommer, puis retirer l'outil, puis supprimer le kit.
        assert (await client.patch(f"/api/v1/tools/kits/{kit['id']}", json={"name": "Renommé"})).json()["name"] == "Renommé"
        assert (await client.delete(f"/api/v1/tools/kits/{kit['id']}/outils/{item['id']}")).json()["items"] == []
        assert (await client.delete(f"/api/v1/tools/kits/{kit['id']}")).status_code == 200


async def test_creer_un_kit_rend_son_numero_quand_la_session_expire_au_commit(async_session, db_session, monkeypatch):
    """SA-29 (M55) : en production la session expire ses objets au commit (``expire_on_commit`` par défaut) ; la fixture de test ne le fait pas,
    ce qui cachait qu'« Ajouter un kit » rendait un 500 (``MissingGreenlet`` en relisant ``kit.id`` après le commit)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    monkeypatch.setattr(db_session, "async_session", async_sessionmaker(bind=async_session.bind, expire_on_commit=True))
    kit = await db_session.creer_un_kit("Kit expirant")
    assert kit["name"] == "Kit expirant" and kit["items"] == [] and isinstance(kit["id"], int)


# --- kits : application et propositions -------------------------------------------------------------------------------------------


async def _kit_a_un_outil(client, db_session, org, nom="ajouter"):
    """Un kit d'un outil, prêt à appliquer ; rend (kit, item)."""
    source = await _outil(db_session, org, nom, compte="Compte source")
    kit = (await client.post("/api/v1/tools/kits", json={"name": f"Kit {nom}"})).json()
    kit = (await client.post(f"/api/v1/tools/kits/{kit['id']}/outils", json={"tool_uuid": source.tool_uuid})).json()
    return kit, kit["items"][0]


async def test_appliquer_un_kit_copie_ses_outils_une_fois(org, autre_org, db_session, test_client_factory, equipe_au_labo):
    AID = autre_org.organisation.id
    async with test_client_factory(org.utilisateur) as client:
        kit, item = await _kit_a_un_outil(client, db_session, org)
    async with test_client_factory(autre_org.utilisateur) as client:
        dossier = (await client.post("/api/v1/tools/dossiers", json={"name": "Reçus"})).json()
        r = await client.post(f"/api/v1/tools/kits/{kit['id']}/appliquer", json={"dossier_id": dossier["id"]})
        assert r.status_code == 200 and len(r.json()["crees"]) == 1
        again = await client.post(f"/api/v1/tools/kits/{kit['id']}/appliquer", json={})
        assert again.json()["crees"] == [] and again.json()["deja_presents"] == 1
        # Appliquer dans le dossier d'une autre organisation : refusé.
    async with test_client_factory(org.utilisateur) as client:
        assert (await client.post(f"/api/v1/tools/kits/{kit['id']}/appliquer", json={"dossier_id": dossier["id"]})).status_code == 404
    copie = await db_session.get_tool_by_uuid(r.json()["crees"][0], AID)
    assert copie.folder_id == dossier["id"] and copie.kit_item_id == item["id"] and copie.kit_version == 1 and copie.version_courante == 1
    assert "compte" not in copie.definition["config"]


async def test_changer_un_outil_du_kit_ne_change_aucun_outil_ni_agent_qui_ne_l_a_pas_accepte(
    org, autre_org, db_session, test_client_factory, equipe_au_labo
):
    AID = autre_org.organisation.id
    async with test_client_factory(org.utilisateur) as client:
        kit, item = await _kit_a_un_outil(client, db_session, org)
    async with test_client_factory(autre_org.utilisateur) as client:
        uuid = (await client.post(f"/api/v1/tools/kits/{kit['id']}/appliquer", json={})).json()["crees"][0]
    # Un agent de l'organisation utilise l'outil reçu, et le fige à sa publication.
    agent = await _agent(db_session, autre_org, uuid)
    await _publier(db_session, agent)
    avant = await db_session.get_tool_by_uuid(uuid, AID)
    definition_avant, nom_avant, desc_avant = dict(avant.definition), avant.name, avant.description

    # Le fork change l'outil du kit (description et définition).
    nouvelle = {"schema_version": 1, "type": "integration", "config": {"connecteur": "commande", "action": "ajouter", "delai_ms": 7000}}
    async with test_client_factory(org.utilisateur) as client:
        r = await client.patch(f"/api/v1/tools/kits/{kit['id']}/outils/{item['id']}", json={"description": "Nouveau texte.", "definition": nouvelle})
        assert r.json()["items"][0]["version"] == 2
        # Un changement vide ne monte pas la version.
        r = await client.patch(f"/api/v1/tools/kits/{kit['id']}/outils/{item['id']}", json={"description": "Nouveau texte."})
        assert r.json()["items"][0]["version"] == 2

    apres = await db_session.get_tool_by_uuid(uuid, AID)
    assert (apres.definition, apres.name, apres.description) == (definition_avant, nom_avant, desc_avant), "l'outil de l'organisation n'a pas bougé"
    assert apres.version_courante == 1 and apres.kit_version == 1
    # La proposition existe, pour la bonne organisation seulement.
    async with test_client_factory(autre_org.utilisateur) as client:
        propositions = (await client.get("/api/v1/tools/kits/propositions")).json()
        assert [(p["tool_uuid"], p["version_recue"], p["version_du_kit"]) for p in propositions] == [(uuid, 1, 2)]
    async with test_client_factory(org.utilisateur) as client:
        assert (await client.get("/api/v1/tools/kits/propositions")).json() == []


async def test_accepter_une_proposition_cree_une_version_garde_le_compte_et_laisse_l_agent_sur_sa_version(
    org, autre_org, db_session, test_client_factory, equipe_au_labo
):
    AID = autre_org.organisation.id
    async with test_client_factory(org.utilisateur) as client:
        kit, item = await _kit_a_un_outil(client, db_session, org)
    async with test_client_factory(autre_org.utilisateur) as client:
        uuid = (await client.post(f"/api/v1/tools/kits/{kit['id']}/appliquer", json={})).json()["crees"][0]
    # L'organisation branche son propre compte sur l'outil (un réglage qui lui appartient).
    recu = await db_session.get_tool_by_uuid(uuid, AID)
    avec_compte = {**recu.definition, "config": {**recu.definition["config"], "compte": "Compte d'Autre"}}
    await db_session.update_tool(uuid, AID, definition=avec_compte, sans_version=True)
    agent = await _agent(db_session, autre_org, uuid)
    await _publier(db_session, agent)

    nouvelle = {"schema_version": 1, "type": "integration", "config": {"connecteur": "commande", "action": "ajouter", "delai_ms": 7000}}
    async with test_client_factory(org.utilisateur) as client:
        await client.patch(f"/api/v1/tools/kits/{kit['id']}/outils/{item['id']}", json={"definition": nouvelle})
    async with test_client_factory(autre_org.utilisateur) as client:
        # Un outil qui n'est pas d'un kit, ou d'une autre organisation : refusé.
        assert (await client.post("/api/v1/tools/kits/propositions/accepter", json={"tool_uuid": "inconnu"})).status_code == 404
        r = await client.post("/api/v1/tools/kits/propositions/accepter", json={"tool_uuid": uuid})
        assert r.status_code == 200, r.text
        # Rien de plus à accepter.
        assert (await client.post("/api/v1/tools/kits/propositions/accepter", json={"tool_uuid": uuid})).status_code == 409
        assert (await client.get("/api/v1/tools/kits/propositions")).json() == []

    apres = await db_session.get_tool_by_uuid(uuid, AID)
    assert apres.kit_version == 2 and apres.version_courante == 2
    assert apres.definition["config"]["delai_ms"] == 7000, "la définition du kit est prise"
    assert apres.definition["config"]["compte"] == "Compte d'Autre", "le compte de l'organisation est gardé"
    # L'agent déjà publié reste sur la version 1 de l'outil.
    epingles = await db_session.outils_epingles_de_l_agent(AID, agent.id)
    ligne = next(o for o in (epingles["outils"] if isinstance(epingles, dict) else epingles.outils) if _uuid(o) == uuid)
    assert _version_epinglee(ligne) == 1


async def test_les_agents_d_un_kit_sont_ceux_de_l_organisation_qui_en_utilisent_un_outil(
    org, autre_org, db_session, test_client_factory, equipe_au_labo
):
    """Écran Outils, « Régler le kit » › Agents (M45) : qui utilise le kit, et sur quelle version ; jamais l'agent d'une autre organisation."""
    async with test_client_factory(org.utilisateur) as client:
        kit, item = await _kit_a_un_outil(client, db_session, org)
    async with test_client_factory(autre_org.utilisateur) as client:
        uuid = (await client.post(f"/api/v1/tools/kits/{kit['id']}/appliquer", json={})).json()["crees"][0]
        assert (await client.get(f"/api/v1/tools/kits/{kit['id']}/agents")).json() == [], "aucun agent ne l'utilise encore"
    utilisateur = await _agent(db_session, autre_org, uuid, nom="Accueil")
    await _agent(db_session, autre_org, nom="Sans le kit")
    await _agent(db_session, org, nom="Agent d'une autre organisation")
    async with test_client_factory(autre_org.utilisateur) as client:
        lignes = (await client.get(f"/api/v1/tools/kits/{kit['id']}/agents")).json()
        assert [(a["agent_id"], a["agent"], a["outils"], a["version_recue"], a["version_du_kit"], a["a_jour"]) for a in lignes] == [
            (utilisateur.id, "Accueil", 1, 1, 1, True)
        ]
    # Le kit monte d'une version : l'agent est sur la précédente, rien ne bouge chez lui.
    nouvelle = {"schema_version": 1, "type": "integration", "config": {"connecteur": "commande", "action": "ajouter", "delai_ms": 7000}}
    async with test_client_factory(org.utilisateur) as client:
        await client.patch(f"/api/v1/tools/kits/{kit['id']}/outils/{item['id']}", json={"definition": nouvelle})
        assert (await client.get(f"/api/v1/tools/kits/{kit['id']}/agents")).json() == [], "l'organisation du kit n'a copié aucun outil"
    async with test_client_factory(autre_org.utilisateur) as client:
        ligne = (await client.get(f"/api/v1/tools/kits/{kit['id']}/agents")).json()[0]
        assert (ligne["version_recue"], ligne["version_du_kit"], ligne["a_jour"]) == (1, 2, False)
        assert (await client.get("/api/v1/tools/kits/999999/agents")).status_code == 404


def _uuid(ligne):
    return ligne["tool_uuid"] if isinstance(ligne, dict) else ligne.tool_uuid


def _version_epinglee(ligne):
    for cle in ("version_epinglee", "version_outil", "epinglee"):
        valeur = ligne.get(cle) if isinstance(ligne, dict) else getattr(ligne, cle, None)
        if valeur is not None:
            return valeur
    raise AssertionError(f"version épinglée introuvable dans {ligne!r}")


# --- vocabulaire ----------------------------------------------------------------------------------------------------------------


def test_aucun_mot_de_metier_dans_les_mecanismes_communs():
    racine = Path(__file__).resolve().parents[2]
    mots = re.compile(r"restaurant|restauration|pizza|menu|plat\b|cuisine|serveur de salle|livraison", re.IGNORECASE)
    for chemin in ("db/outils_rangement_client.py", "routes/outils_rangement.py", "schemas/outils_rangement.py"):
        trouve = mots.findall((racine / chemin).read_text(encoding="utf-8"))
        assert not trouve, f"{chemin} : {trouve}"
    # Le modèle de données : les trois tables et les colonnes d'outil ne portent aucun mot de métier non plus.
    assert ToolFolderModel.__tablename__ == "tool_folders"
    assert {"folder_id", "kit_item_id", "kit_version"} <= set(ToolModel.__table__.columns.keys())
    assert select  # (import utilisé : le test lit les modèles, pas la base)
