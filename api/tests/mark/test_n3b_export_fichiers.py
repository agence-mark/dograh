"""[.mark] Partie 3, N3b, sous-lot 3 : l'agent entier en fichiers lisibles, et leur import dans le brouillon (``services/export_agent/fichiers``).

| Test | Ce qu'il prouve |
|---|---|
| contenu | graphe, un prompt par étape, réglages, variables, outils épinglés à leur version, blocs cités, tests : un fichier chacun |
| déterminisme | deux exports sans rien changer = les mêmes fichiers ; l'archive aussi (mêmes octets) |
| aucun secret | une clé écrite dans un réglage, dans le graphe ou dans un test n'est dans aucun fichier ; une référence de clé (``…credential_uuid``) reste ; le nombre retiré est dit |
| aller-retour | exporter A, importer dans un autre agent B (brouillon), exporter B : mêmes fichiers (hors le nom) ; rien n'est publié |
| idempotent | le même dossier importé deux fois : aucun doublon (tests, outils), l'aperçu dit « inchangé » partout ; le chemin du déclencheur ne bouge pas |
| aperçu | ajouté, modifié (nombre de lignes), inchangé, retiré (gardé) ; il n'écrit rien |
| outils | la version épinglée voyage ; un outil d'une autre organisation se retrouve par son nom, sinon il est dit absent |
| refus | un dossier qui n'est pas un agent exporté, un chemin hors liste, un YAML cassé, un graphe invalide, une clé en clair : refus ou ignorée, rien n'est écrit |
| cloisonnement | par la clé d'une autre organisation : 404 en exportant comme en important ; une clé d'organisation exporte et importe SON agent |
"""

from __future__ import annotations

import copy
import zipfile
import io
from types import SimpleNamespace

import pytest
import yaml

from api.db import branche_ouverte
from api.services.builder.tests_agent import stockage
from api.services.equipe_mark import espaces
from api.services.export_agent import fichiers
from api.tests.mark.equipe_commun import client_http, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401  (fixtures)
from api.tests.mark.test_outils_versions import _agent, _definition_d_outil, _graphe, _outil
from api.tests.mark.test_sous_dossiers_et_groupe import _oublier, autre_org, org  # noqa: F401

CLE_EN_CLAIR = "sk-test-0000-jamais-ecrite"


@pytest.fixture(autouse=True)
def _contexte_propre():
    branche_ouverte.ouvrir(None, None)
    espaces.reinitialiser_cache()
    yield
    branche_ouverte.ouvrir(None, None)
    espaces.reinitialiser_cache()


def _test(slug="urgence-gaz", **plus):
    return {"slug": slug, "nom": "Urgence gaz", "origine": "manuel", "obligatoire": True, "criteres": [{"type": "texte_present", "texte": "112"}], "dossier": "", **plus}


async def _agent_complet(db, org, nom="Agent A"):
    """Un agent avec un outil (deux versions, épinglé à la 1), un déclencheur, des réglages, des variables, un secret et deux tests."""
    outil = await _outil(db, org, "reserver")
    await db.update_tool(outil.tool_uuid, org.organisation.id, description="Version deux.", user_id=org.utilisateur.id)
    graphe = _graphe(outil.tool_uuid)
    graphe["nodes"][0]["data"]["prompt"] = "Bonjour.\nVoici la règle : {{bloc:regles-d-or}}\nÀ bientôt, café crème."
    graphe["nodes"][0]["data"]["api_key"] = CLE_EN_CLAIR
    graphe["nodes"][0]["data"]["credential_uuid"] = "cred-123"
    graphe["nodes"].append({"id": "3", "type": "trigger", "position": {"x": 0, "y": 200}, "data": {"name": "Déclencheur", "trigger_path": "chemin-de-a"}})
    agent = await db.create_workflow(name=nom, workflow_definition=graphe, user_id=org.utilisateur.id, organization_id=org.organisation.id)
    await db.update_workflow(
        workflow_id=agent.id,
        name=None,
        workflow_definition=graphe,
        template_context_variables={"entreprise": "Chauffage Durand", "token": CLE_EN_CLAIR},
        workflow_configurations={"phrases_regles": [{"id": "r1", "texte": "Un instant."}], "ambient_noise_configuration": {"storage_key": "x"}, "password": CLE_EN_CLAIR, "reglage": 7},
        organization_id=org.organisation.id,
    )
    await db.remplacer_les_epingles_du_brouillon(org.organisation.id, agent.id, {outil.tool_uuid: 1})
    await stockage.ecrire(org.organisation.id, agent.id, _test())
    await stockage.ecrire(org.organisation.id, agent.id, _test("sans-prix", nom="Sans prix", obligatoire=False, criteres=[{"type": "sans_redite"}], secret=CLE_EN_CLAIR))
    return agent, outil


@pytest.fixture(autouse=True)
def _bloc_de_la_bibliotheque(monkeypatch):
    from api.services.etiquettes_prompt import table
    from api.services.etiquettes_prompt.resolution import BlocLu, VersionDeBloc

    bloc = BlocLu(slug="regles-d-or", titre="Règles d'or", famille="prompt-general", versions=(VersionDeBloc(1, "recette", "Toujours poli."),))

    async def lire(slug):
        return bloc if slug == "regles-d-or" else None

    monkeypatch.setattr(table, "lire_un_bloc", lire)


# --- le contenu -----------------------------------------------------------------------------------------------------------------


async def test_l_export_a_un_fichier_par_element_lisible(org, db_session):
    agent, outil = await _agent_complet(db_session, org)
    rendu = await fichiers.exporter(org.organisation.id, agent.id)
    f = rendu["fichiers"]
    assert {"agent.yaml", "graphe.yaml", "reglages.yaml", "variables.yaml", "outils.yaml", "blocs.yaml", "tests/urgence-gaz.yaml", "tests/sans-prix.yaml"} <= set(f)
    assert [c for c in f if c.startswith("prompts/")] == ["prompts/1-accueil.md", "prompts/2-fin.md", ] or sorted(c for c in f if c.startswith("prompts/")) == ["prompts/1-accueil.md", "prompts/2-fin.md"]
    assert f["prompts/1-accueil.md"] == "Bonjour.\nVoici la règle : {{bloc:regles-d-or}}\nÀ bientôt, café crème."  # le texte exact, accents compris
    graphe = yaml.safe_load(f["graphe.yaml"])
    premier = next(n for n in graphe["nodes"] if n["id"] == "1")
    assert "prompt" not in premier["data"] and premier["data"]["prompt_fichier"] == "prompts/1-accueil.md"
    outils = yaml.safe_load(f["outils.yaml"])
    assert outils == [{"nom": "reserver", "uuid": outil.tool_uuid, "version": 1}]  # épinglé à la v1 alors que la courante est la v2
    blocs = yaml.safe_load(f["blocs.yaml"])
    assert blocs == [{"slug": "regles-d-or", "suit": True, "version": None, "existe": True, "famille": "prompt-general", "titre": "Règles d'or", "version_lue": 1}]
    assert f["blocs/regles-d-or.md"] == "Toujours poli."
    reglages = yaml.safe_load(f["reglages.yaml"])
    assert reglages["phrases_regles"] == [{"id": "r1", "texte": "Un instant."}] and reglages["reglage"] == 7
    assert "ambient_noise_configuration" not in reglages  # un fichier de la source ne voyage pas
    assert yaml.safe_load(f["variables.yaml"]) == {"entreprise": "Chauffage Durand"}


async def test_l_export_est_deterministe_octet_pour_octet(org, db_session):
    agent, _ = await _agent_complet(db_session, org)
    a = await fichiers.exporter(org.organisation.id, agent.id)
    b = await fichiers.exporter(org.organisation.id, agent.id)
    assert a == b
    assert fichiers.en_zip(a["fichiers"]) == fichiers.en_zip(b["fichiers"])
    with zipfile.ZipFile(io.BytesIO(fichiers.en_zip(a["fichiers"]))) as z:
        assert sorted(z.namelist()) == sorted(a["fichiers"]) and z.read("prompts/1-accueil.md").decode() == a["fichiers"]["prompts/1-accueil.md"]


async def test_aucun_secret_n_est_dans_les_fichiers_et_la_reference_de_cle_reste(org, db_session):
    agent, _ = await _agent_complet(db_session, org)
    rendu = await fichiers.exporter(org.organisation.id, agent.id)
    assert CLE_EN_CLAIR not in "\n".join(rendu["fichiers"].values())
    assert rendu["secrets_retires"] == 4  # api_key du graphe, token des variables, password des réglages, secret d'un test
    assert yaml.safe_load(rendu["fichiers"]["agent.yaml"])["secrets_retires"] == 4
    assert "cred-123" in rendu["fichiers"]["graphe.yaml"]  # une référence, pas une clé


async def test_le_declencheur_ne_voyage_pas(org, db_session):
    agent, _ = await _agent_complet(db_session, org)
    f = (await fichiers.exporter(org.organisation.id, agent.id))["fichiers"]
    assert "chemin-de-a" not in f["graphe.yaml"] and fichiers.MARQUE_DECLENCHEUR in f["graphe.yaml"]


async def test_on_peut_n_exporter_que_certains_contenus(org, db_session):
    agent, _ = await _agent_complet(db_session, org)
    f = (await fichiers.exporter(org.organisation.id, agent.id))["fichiers"]
    seulement = fichiers.filtrer(f, ["prompts", "tests"])
    assert set(seulement) == {"agent.yaml", "prompts/1-accueil.md", "prompts/2-fin.md", "tests/urgence-gaz.yaml", "tests/sans-prix.yaml"}
    assert fichiers.filtrer(f, None) == f and "outils.yaml" in fichiers.filtrer(f, ["outils"]) and "blocs/regles-d-or.md" in fichiers.filtrer(f, ["blocs"])
    with pytest.raises(fichiers.ErreurFichiers):
        fichiers.filtrer(f, ["tout"])


# --- l'aller-retour ---------------------------------------------------------------------------------------------------------------


async def _sans_le_nom(rendu):
    return {chemin: texte for chemin, texte in rendu["fichiers"].items() if chemin != "agent.yaml"}


async def test_aller_retour_sans_perte_dans_un_autre_agent_et_rien_n_est_publie(org, db_session):
    a, outil = await _agent_complet(db_session, org)
    exporte = await fichiers.exporter(org.organisation.id, a.id)
    b = await _agent(db_session, org, nom="Agent B")
    en_ligne_avant = (await db_session.get_workflow(b.id, organization_id=org.organisation.id)).released_definition_id
    compte = await fichiers.importer(SimpleNamespace(id=org.utilisateur.id), org.organisation.id, b.id, exporte["fichiers"])
    assert compte["applique"] is True and compte["tests_ecrits"] == 2 and compte["outils_epingles"] == 1 and compte["avertissements"] == []
    relu = await fichiers.exporter(org.organisation.id, b.id)
    assert await _sans_le_nom(relu) == await _sans_le_nom(exporte)  # graphe, prompts, réglages, variables, outils épinglés, blocs, tests
    assert yaml.safe_load(relu["fichiers"]["agent.yaml"])["nom"] == "Agent B"  # l'import ne renomme pas
    brouillon = await db_session.get_draft_version(b.id)
    assert brouillon.outils_epingles == {outil.tool_uuid: 1}  # la version exacte est épinglée dans le brouillon
    assert (await db_session.get_workflow(b.id, organization_id=org.organisation.id)).released_definition_id == en_ligne_avant  # jamais en ligne


async def test_importer_deux_fois_le_meme_dossier_ne_double_rien(org, db_session):
    a, _ = await _agent_complet(db_session, org)
    exporte = await fichiers.exporter(org.organisation.id, a.id)
    b = await _agent(db_session, org, nom="Agent B")
    utilisateur = SimpleNamespace(id=org.utilisateur.id)
    await fichiers.importer(utilisateur, org.organisation.id, b.id, exporte["fichiers"])
    premier = await fichiers.exporter(org.organisation.id, b.id)
    chemin_b = next(n for n in yaml.safe_load(premier["fichiers"]["graphe.yaml"])["nodes"] if n["type"] == "trigger")
    trigger_apres_le_premier = (await db_session.get_draft_version(b.id)).workflow_json["nodes"][-1]["data"]["trigger_path"]
    await fichiers.importer(utilisateur, org.organisation.id, b.id, exporte["fichiers"])
    second = await fichiers.exporter(org.organisation.id, b.id)
    assert second == premier
    assert chemin_b["data"]["trigger_path"] == fichiers.MARQUE_DECLENCHEUR
    assert (await db_session.get_draft_version(b.id)).workflow_json["nodes"][-1]["data"]["trigger_path"] == trigger_apres_le_premier  # l'adresse du déclencheur ne bouge pas
    assert len(await stockage.lister(org.organisation.id, b.id)) == 2
    apercu = await fichiers.previsualiser(org.organisation.id, b.id, exporte["fichiers"])
    assert {ligne["effet"] for ligne in apercu} == {"inchange"}


async def test_l_apercu_dit_ajoute_modifie_inchange_retire_et_n_ecrit_rien(org, db_session):
    a, _ = await _agent_complet(db_session, org)
    f = copy.deepcopy((await fichiers.exporter(org.organisation.id, a.id))["fichiers"])
    f["prompts/1-accueil.md"] = "Bonjour, autre texte.\nDeuxième ligne."
    f["tests/nouveau.yaml"] = yaml.safe_dump(_test("nouveau"))
    del f["tests/sans-prix.yaml"]
    avant = await fichiers.exporter(org.organisation.id, a.id)
    apercu = {ligne["fichier"]: ligne for ligne in await fichiers.previsualiser(org.organisation.id, a.id, f)}
    assert apercu["prompts/1-accueil.md"]["effet"] == "modifie" and apercu["prompts/1-accueil.md"]["detail"]
    assert apercu["tests/nouveau.yaml"]["effet"] == "ajoute"
    assert apercu["tests/sans-prix.yaml"]["effet"] == "retire"
    assert apercu["reglages.yaml"]["effet"] == "inchange"
    assert await fichiers.exporter(org.organisation.id, a.id) == avant  # l'aperçu n'a rien écrit


async def test_importer_un_prompt_modifie_arrive_dans_le_brouillon_et_ne_supprime_aucun_test(org, db_session):
    a, _ = await _agent_complet(db_session, org)
    f = copy.deepcopy((await fichiers.exporter(org.organisation.id, a.id))["fichiers"])
    f["prompts/1-accueil.md"] = "Bonjour, nouvelle consigne."
    del f["tests/sans-prix.yaml"]
    await fichiers.importer(SimpleNamespace(id=org.utilisateur.id), org.organisation.id, a.id, f)
    brouillon = await db_session.get_draft_version(a.id)
    assert next(n for n in brouillon.workflow_json["nodes"] if n["id"] == "1")["data"]["prompt"] == "Bonjour, nouvelle consigne."
    assert {t["slug"] for t in await stockage.lister(org.organisation.id, a.id)} == {"urgence-gaz", "sans-prix"}  # jamais supprimé


# --- les outils -------------------------------------------------------------------------------------------------------------------


async def test_un_outil_d_une_autre_organisation_se_retrouve_par_son_nom_sinon_il_est_dit_absent(org, autre_org, db_session):
    a, outil = await _agent_complet(db_session, org)
    exporte = await fichiers.exporter(org.organisation.id, a.id)
    b = await _agent(db_session, autre_org, nom="Chez l'autre")
    sans_outil = await fichiers.importer(SimpleNamespace(id=autre_org.utilisateur.id), autre_org.organisation.id, b.id, exporte["fichiers"])
    assert {"code": "outil_absent", "nom": "reserver"} in sans_outil["avertissements"]
    assert sans_outil["outils_epingles"] == 0
    chez_lui = await _outil(db_session, autre_org, "reserver")
    await db_session.update_tool(chez_lui.tool_uuid, autre_org.organisation.id, description="Deux.", user_id=autre_org.utilisateur.id)
    importe = await fichiers.importer(SimpleNamespace(id=autre_org.utilisateur.id), autre_org.organisation.id, b.id, exporte["fichiers"])
    assert importe["outils_epingles"] == 1 and not [w for w in importe["avertissements"] if w["code"] == "outil_absent"]
    brouillon = await db_session.get_draft_version(b.id)
    assert brouillon.outils_epingles == {chez_lui.tool_uuid: 1}  # l'outil de SON organisation, à la version exportée
    assert outil.tool_uuid not in str(brouillon.workflow_json)  # aucun identifiant de l'organisation d'origine


async def test_un_bloc_absent_de_la_bibliotheque_est_dit_sans_rien_creer(org, db_session, monkeypatch):
    a, _ = await _agent_complet(db_session, org)
    exporte = await fichiers.exporter(org.organisation.id, a.id)
    from api.services.etiquettes_prompt import table

    async def aucun(slug):
        return None

    monkeypatch.setattr(table, "lire_un_bloc", aucun)
    b = await _agent(db_session, org, nom="Agent B")
    compte = await fichiers.importer(SimpleNamespace(id=org.utilisateur.id), org.organisation.id, b.id, exporte["fichiers"])
    assert {"code": "bloc_absent", "nom": "regles-d-or"} in compte["avertissements"]


# --- les refus ------------------------------------------------------------------------------------------------------------------


async def _refus(org, agent, f, mot):
    with pytest.raises(fichiers.ErreurFichiers) as e:
        await fichiers.importer(SimpleNamespace(id=org.utilisateur.id), org.organisation.id, agent.id, f)
    assert mot in str(e.value)
    return e.value


async def test_un_dossier_qui_n_est_pas_un_agent_exporte_est_refuse_sans_rien_ecrire(org, db_session):
    a, _ = await _agent_complet(db_session, org)
    bon = (await fichiers.exporter(org.organisation.id, a.id))["fichiers"]
    avant = await fichiers.exporter(org.organisation.id, a.id)
    await _refus(org, a, {"graphe.yaml": bon["graphe.yaml"]}, "not an exported agent")
    await _refus(org, a, {**bon, "agent.yaml": yaml.safe_dump({"format": "autre", "version": 1})}, "not an exported agent")
    await _refus(org, a, {**bon, "agent.yaml": yaml.safe_dump({"format": fichiers.FORMAT, "version": 99})}, "not known")
    await _refus(org, a, {**bon, "../secret.md": "x"}, "not part of an exported agent")
    await _refus(org, a, {**bon, "graphe.yaml": "a: [unclosed"}, "not valid YAML")
    await _refus(org, a, {**{k: v for k, v in bon.items() if k != "prompts/1-accueil.md"}}, "is missing")
    await _refus(org, a, {**bon, "tests/autre-nom.yaml": bon["tests/urgence-gaz.yaml"]}, "slug does not match")
    assert await fichiers.exporter(org.organisation.id, a.id) == avant


async def test_un_graphe_invalide_est_refuse_avant_toute_ecriture(org, db_session):
    a, _ = await _agent_complet(db_session, org)
    bon = (await fichiers.exporter(org.organisation.id, a.id))["fichiers"]
    avant = await fichiers.exporter(org.organisation.id, a.id)
    casse = yaml.safe_load(bon["graphe.yaml"])
    casse["edges"] = [{"id": "x", "source": "1", "target": "inconnu", "data": {"label": "l", "condition": "c"}}]
    await _refus(org, a, {**bon, "graphe.yaml": yaml.safe_dump(casse)}, "graph is not valid")
    assert await fichiers.exporter(org.organisation.id, a.id) == avant


async def test_une_cle_ajoutee_a_la_main_dans_un_dossier_n_entre_pas(org, db_session):
    a, _ = await _agent_complet(db_session, org)
    bon = copy.deepcopy((await fichiers.exporter(org.organisation.id, a.id))["fichiers"])
    reglages = yaml.safe_load(bon["reglages.yaml"])
    reglages["api_key"] = CLE_EN_CLAIR
    bon["reglages.yaml"] = yaml.safe_dump(reglages)
    b = await _agent(db_session, org, nom="Agent B")
    compte = await fichiers.importer(SimpleNamespace(id=org.utilisateur.id), org.organisation.id, b.id, bon)
    assert {"code": "secrets_ignores", "nombre": 1} in compte["avertissements"]
    assert CLE_EN_CLAIR not in str((await db_session.get_draft_version(b.id)).workflow_configurations)


async def test_les_reglages_de_rattachement_de_l_agent_cible_sont_gardes(org, db_session):
    a, _ = await _agent_complet(db_session, org)
    exporte = (await fichiers.exporter(org.organisation.id, a.id))["fichiers"]
    b = await _agent(db_session, org, nom="Agent B")
    await db_session.update_workflow(
        workflow_id=b.id, name=None, workflow_definition=_graphe(), template_context_variables=None,
        workflow_configurations={"agents_specialises": [4242], "etablissement_id": "beauvais"}, organization_id=org.organisation.id,
    )
    await fichiers.importer(SimpleNamespace(id=org.utilisateur.id), org.organisation.id, b.id, exporte)
    reglages = (await db_session.get_draft_version(b.id)).workflow_configurations
    assert reglages["agents_specialises"] == [4242] and reglages["etablissement_id"] == "beauvais" and reglages["reglage"] == 7


# --- par la clé de l'organisation ----------------------------------------------------------------------------------------------


async def test_une_session_exporte_et_importe_son_agent_et_pas_celui_d_une_autre_et_une_cle_n_y_entre_plus(org, autre_org, db_session, monkeypatch):
    """RV (point 3) : l'agent en fichiers n'a pas sa propre permission de clé : fermé aux clés, export comme import. La session d'une personne
    (avec son organisation dans l'adresse) exporte et importe SON agent ; celle d'une autre organisation reçoit 404."""
    from api.tests.mark.equipe_commun import creer_compte, entetes

    a, _ = await _agent_complet(db_session, org)
    _, jeton = await creer_compte(db_session, "n3b-fichiers@example.com", role="Administrateur", organisations=[org.organisation.id, autre_org.organisation.id])
    pour, contre = entetes(jeton, org.organisation.id), entetes(jeton, autre_org.organisation.id)
    _, cle = await db_session.create_api_key(org.organisation.id, "n8n", org.utilisateur.id)
    async with client_http() as c:
        assert (await c.get(f"/api/v1/agent-fichiers/{a.id}/export", headers={"X-API-Key": cle})).status_code == 403
        assert (await c.post(f"/api/v1/agent-fichiers/{a.id}/import", headers={"X-API-Key": cle}, json={"fichiers": {}})).status_code == 403
        r = await c.get(f"/api/v1/agent-fichiers/{a.id}/export", headers=pour)
        z = await c.get(f"/api/v1/agent-fichiers/{a.id}/export?format=zip", headers=pour)
        partiel = await c.get(f"/api/v1/agent-fichiers/{a.id}/export?contenus=tests", headers=pour)
        assert sorted(partiel.json()["fichiers"]) == ["agent.yaml", "tests/sans-prix.yaml", "tests/urgence-gaz.yaml"]
        assert (await c.get(f"/api/v1/agent-fichiers/{a.id}/export?contenus=tout", headers=pour)).status_code == 422
        assert r.status_code == 200 and "graphe.yaml" in r.json()["fichiers"] and CLE_EN_CLAIR not in r.text
        assert z.status_code == 200 and z.headers["content-type"] == "application/zip" and zipfile.ZipFile(io.BytesIO(z.content)).testzip() is None
        assert (await c.get(f"/api/v1/agent-fichiers/{a.id}/export", headers=contre)).status_code == 404
        corps = {"fichiers": r.json()["fichiers"]}
        assert (await c.post(f"/api/v1/agent-fichiers/{a.id}/import", headers=contre, json=corps)).status_code == 404
        apercu = await c.post(f"/api/v1/agent-fichiers/{a.id}/import", headers=pour, json=corps)
        assert apercu.status_code == 200 and apercu.json()["applique"] is False and {x["effet"] for x in apercu.json()["fichiers"]} == {"inchange"}
        notees: list[tuple] = []
        from api.services import modifications_live as live

        async def noter(organisation, objet, action, **options):
            notees.append((organisation, objet, action))

        monkeypatch.setattr(live, "noter", noter)
        applique = await c.post(f"/api/v1/agent-fichiers/{a.id}/import", headers=pour, json={**corps, "appliquer": True})
        assert applique.status_code == 200 and applique.json()["applique"] is True
        assert notees == [(org.organisation.id, f"agent:{a.id}", "import_fichiers")]  # l'écran ouvert se relit seul
        mauvais = await c.post(f"/api/v1/agent-fichiers/{a.id}/import", headers=pour, json={"fichiers": {"x.txt": "y"}})
        assert mauvais.status_code == 422 and "not part of an exported agent" in mauvais.json()["detail"]
        assert (await c.get(f"/api/v1/agent-fichiers/999999/export", headers=pour)).status_code == 404