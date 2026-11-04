"""[.mark] Builder partie 2, U10 / S2 : le modèle « agent de site ».

| Test | Ce qu'il prouve |
|---|---|
| chemins (D175) | normalisation (majuscules, barre finale, paramètres, ancre, accents), segments entiers, ``..`` refusé |
| plus long préfixe | la page la plus précise l'emporte ; ``/sav`` ne couvre pas ``/savoir-faire`` ; page sans agent : rien |
| unicité | deux agents sur un même chemin du site sont refusés (même écrit autrement), tout ou rien ; un agent peut avoir plusieurs chemins |
| configuration par page | l'agent du chemin le plus long, sinon « tout le site », sinon ``actif: false`` ; domaine contrôlé ; ETag/304 ; cache vidé à l'enregistrement |
| dernier chargement | écrit, au plus une fois par minute |
| apparence (D198, D199) | défauts français et bleu .mark, 18 textes, retouche d'un élément sans toucher les autres, refus des valeurs invalides |
| canal (D153, D163) | téléphone par défaut ; pas de nouveau jeton sur un agent téléphonique (mais l'ancien garde le sien) ; pas de numéro ni de transfert d'appel sur un agent de site |
| agents-servis | canal, emplacement et état du widget ; un spécialisé prend le canal de son principal |
| autre organisation | chaque route ouverte au portail répond 404 (ou ne liste rien) avec la clé d'une autre organisation |
| Couleur de mon site (D203) | domaine non autorisé, adresse privée, redirection vers l'interne, page de 5 Mo coupée à 1 Mo, délai dépassé, limite de dix par heure |
"""

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from api.db.site_client import CheminDejaPris
from api.enums import ToolCategory
from api.schemas.apparence_widget import (
    COULEUR_MARK,
    ApparenceWidget,
    TEXTES_DEFAUT,
)
from api.services.groupe.agents_servis import assembler, AgentLu
from api.services.site_mark import canal as lib_canal
from api.services.site_mark import chemins, config_site, lecture_site
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)
from api.tests.mark.site_commun import creer_agent, creer_agent_avec_jeton, limiteur_en_memoire

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")

DONNEES = Path(__file__).parent / "donnees" / "site"
API = "/api/v1"
ORIGINE = {"Origin": "https://client.fr"}


# ----------------------------------------------------------------------------- chemins (D175)
@pytest.mark.parametrize(
    "brut, attendu",
    [
        (None, "/"),
        ("", "/"),
        ("/", "/"),
        ("/Tarifs/", "/tarifs"),
        ("/sav?x=1&y=2", "/sav"),
        ("/aide#section", "/aide"),
        ("/caf%C3%A9/Menu", "/café/menu"),
        ("//a///b//", "/a/b"),
        ("https://Client.fr/Aide/?q=1", "/aide"),
        ("tarifs", "/tarifs"),
        ("/a/./b", "/a/b"),
    ],
)
def test_normalisation_du_chemin(brut, attendu):
    assert chemins.normaliser(brut) == attendu


def test_un_chemin_qui_remonte_est_refuse():
    with pytest.raises(chemins.CheminInvalide):
        chemins.normaliser("/a/../b")
    with pytest.raises(chemins.CheminInvalide):
        chemins.normaliser("/" + "a" * 600)


def test_le_plus_long_prefixe_par_segments():
    agents = {"/": "tout", "/tarifs": "tarifs", "/aide": "aide", "/aide/retours": "retours", "/sav": "sav"}
    assert chemins.plus_long_prefixe(agents, "/tarifs/pro") == "tarifs"
    assert chemins.plus_long_prefixe(agents, "/Aide/Retours/") == "retours"
    assert chemins.plus_long_prefixe(agents, "/aide/faq") == "aide"
    assert chemins.plus_long_prefixe(agents, "/contact") == "tout"
    assert chemins.plus_long_prefixe(agents, "/") == "tout"
    # Un segment partiel ne couvre rien : /sav ne couvre pas /savoir-faire.
    assert chemins.plus_long_prefixe(agents, "/savoir-faire") == "tout"
    assert chemins.plus_long_prefixe({"/sav": "sav"}, "/savoir-faire") is None
    # Page sans agent et pas d'agent « tout le site » : rien.
    assert chemins.plus_long_prefixe({"/tarifs": "t"}, "/contact") is None


# ----------------------------------------------------------------------------- unicité et configuration par page
async def _site_avec_agents(db_session, async_session, chemins_par_agent):
    """Un site et un agent par entrée de ``chemins_par_agent`` (liste de chemins) ; rend (organisation, site, jetons)."""
    organisation_id = None
    jetons = []
    site = None
    for chemins_de_lagent in chemins_par_agent:
        organisation_id, _, _, jeton = await creer_agent_avec_jeton(
            db_session, async_session, organisation_id=organisation_id
        )
        if site is None:
            site = await db_session.creer_site(organisation_id, "Site du client", ["client.fr"])
        await db_session.poser_emplacement(
            organisation_id, jeton.id, site.id, [chemins.normaliser(c) for c in chemins_de_lagent]
        )
        jetons.append(jeton)
    return organisation_id, site, jetons


async def test_deux_agents_sur_le_meme_chemin_sont_refuses_et_rien_ne_change(db_session, async_session):
    organisation_id, site, (premier,) = await _site_avec_agents(db_session, async_session, [["/Tarifs/"]])
    _, _, _, second = await creer_agent_avec_jeton(db_session, async_session, organisation_id=organisation_id)
    id_premier, id_second, id_site = premier.id, second.id, site.id
    with pytest.raises(CheminDejaPris) as erreur:
        # « /tarifs?x=1 » est le même chemin une fois normalisé.
        await db_session.poser_emplacement(
            organisation_id, id_second, id_site, [chemins.normaliser("/aide"), chemins.normaliser("/tarifs?x=1")]
        )
    assert erreur.value.chemin == "/tarifs"
    # Tout ou rien : « /aide » n'a pas été pris non plus, et le premier garde sa page.
    assert await db_session.lire_chemins_du_jeton(id_second) == []
    assert [c.chemin for c in await db_session.lire_chemins_du_jeton(id_premier)] == ["/tarifs"]


async def test_un_agent_peut_servir_plusieurs_chemins_et_les_reposer(db_session, async_session):
    organisation_id, site, (agent,) = await _site_avec_agents(db_session, async_session, [["/tarifs", "/aide"]])
    assert [c.chemin for c in await db_session.lire_chemins_du_jeton(agent.id)] == ["/tarifs", "/aide"]
    await db_session.poser_emplacement(organisation_id, agent.id, site.id, ["/tarifs", "/contact"])  # il se remplace lui-même
    assert [c.chemin for c in await db_session.lire_chemins_du_jeton(agent.id)] == ["/tarifs", "/contact"]


async def _configuration(client, cle, chemin, origine="https://client.fr", etag=None):
    entete = {"Origin": origine}
    if etag:
        entete["If-None-Match"] = etag
    return await client.get(f"{API}/public/embed/site/{cle}/config", params={"chemin": chemin}, headers=entete)


async def test_la_configuration_rend_l_agent_du_chemin_le_plus_long(db_session, async_session):
    config_site.vider_le_cache()
    _, site, (racine, tarifs, aide) = await _site_avec_agents(
        db_session, async_session, [["/"], ["/tarifs"], ["/aide", "/faq"]]
    )
    async with client_http() as c:
        assert (await _configuration(c, site.cle, "/tarifs/pro")).json()["token"] == tarifs.token
        assert (await _configuration(c, site.cle, "/FAQ/")).json()["token"] == aide.token
        assert (await _configuration(c, site.cle, "/contact")).json()["token"] == racine.token
        assert (await _configuration(c, site.cle, "/")).json()["token"] == racine.token


async def test_sans_agent_tout_le_site_une_page_sans_agent_n_affiche_rien(db_session, async_session):
    config_site.vider_le_cache()
    _, site, (tarifs,) = await _site_avec_agents(db_session, async_session, [["/tarifs"]])
    async with client_http() as c:
        assert (await _configuration(c, site.cle, "/tarifs")).json()["token"] == tarifs.token
        reponse = await _configuration(c, site.cle, "/contact")
    assert reponse.status_code == 200
    assert reponse.json() == {"actif": False}


async def test_un_jeton_inactif_ne_sert_plus_sa_page(db_session, async_session):
    config_site.vider_le_cache()
    organisation_id, site, (racine, tarifs) = await _site_avec_agents(db_session, async_session, [["/"], ["/tarifs"]])
    await db_session.update_embed_token(tarifs.id, organisation_id, is_active=False)
    async with client_http() as c:
        assert (await _configuration(c, site.cle, "/tarifs")).json()["token"] == racine.token


async def test_le_domaine_est_controle_a_chaque_requete_meme_avec_le_cache(db_session, async_session):
    config_site.vider_le_cache()
    _, site, _ = await _site_avec_agents(db_session, async_session, [["/"]])
    async with client_http() as c:
        assert (await _configuration(c, site.cle, "/")).status_code == 200  # remplit le cache
        refuse = await _configuration(c, site.cle, "/", origine="https://pirate.example")
        inconnue = await _configuration(c, "site_inconnu", "/")
        invalide = await c.get(f"{API}/public/embed/site/{site.cle}/config", params={"chemin": "/a/../b"}, headers=ORIGINE)
    assert refuse.status_code == 403
    assert inconnue.status_code == 404
    assert invalide.status_code == 400


async def test_etag_304_et_cache_vide_a_l_enregistrement_d_une_apparence(db_session, async_session):
    config_site.vider_le_cache()
    organisation_id, site, (agent,) = await _site_avec_agents(db_session, async_session, [["/"]])
    async with client_http() as c:
        premiere = await _configuration(c, site.cle, "/")
        etag = premiere.headers["etag"]
        assert premiere.headers["cache-control"] == "public, max-age=300"
        assert (await _configuration(c, site.cle, "/", etag=etag)).status_code == 304
        # Le client change la couleur de base : le cache est vidé, le nouvel ETag est rendu.
        apparence = ApparenceWidget(couleur_base="#aa2200").model_dump(mode="json")
        await db_session.update_embed_token(
            agent.id, organisation_id, settings={"apparence": apparence}
        )
        config_site.vider_le_cache(site.cle)
        apres = await _configuration(c, site.cle, "/", etag=etag)
    assert apres.status_code == 200
    assert apres.json()["apparence"]["couleur_base"] == "#aa2200"
    assert apres.headers["etag"] != etag


async def test_le_dernier_chargement_est_ecrit_au_plus_une_fois_par_minute(db_session, async_session):
    config_site.vider_le_cache()
    config_site._dernier_chargement_ecrit.clear()
    _, site, _ = await _site_avec_agents(db_session, async_session, [["/"]])
    assert (await db_session.lire_site_par_cle(site.cle)).dernier_chargement is None
    assert await config_site.noter_le_chargement(db_session, site.id) is True
    premier = (await db_session.lire_site_par_cle(site.cle)).dernier_chargement
    assert premier is not None
    await asyncio.sleep(0.05)
    assert await config_site.noter_le_chargement(db_session, site.id) is False  # moins d'une minute
    assert (await db_session.lire_site_par_cle(site.cle)).dernier_chargement == premier


# ----------------------------------------------------------------------------- apparence
def test_apparence_par_defaut_bleu_mark_francais_vingt_quatre_textes():
    a = ApparenceWidget()
    assert a.couleur_base == COULEUR_MARK == "#1b5fb0"
    assert a.orbe_animee is True and a.embleme == "orbe" and a.avis is True
    assert len(TEXTES_DEFAUT) == 24  # 18 d'origine + 6 de V5 (titre, avis, deux cases, passer, écrire)
    assert a.textes.model_dump() == TEXTES_DEFAUT
    assert a.textes.accroche == "Une question ?\nParlez-moi."  # les retours à la ligne sont gardés
    # Tout est tiré de la base et du fond, sauf le rouge de « raccrocher », le gris de la bulle de l'assistant et les textes.
    assert set(a.couleurs_resolues().values()) <= {"#1b5fb0", "#ffffff", "#0f1c2e", "#dc2626", "#f1f1f1"}


def test_retoucher_un_element_ne_touche_aucun_autre():
    base = ApparenceWidget().couleurs_resolues()
    retouchee = ApparenceWidget(couleurs={"raccrocher": "#CC0000"}).couleurs_resolues()
    assert retouchee["raccrocher"] == "#cc0000"
    assert {k: v for k, v in retouchee.items() if k != "raccrocher"} == {k: v for k, v in base.items() if k != "raccrocher"}
    # Changer la base déplace les éléments non retouchés, jamais l'élément retouché.
    autre = ApparenceWidget(couleur_base="#00aa00", couleurs={"raccrocher": "#CC0000"}).couleurs_resolues()
    assert autre["raccrocher"] == "#cc0000" and autre["orbe"] == "#00aa00" and autre["boutons"] == "#00aa00"


@pytest.mark.parametrize(
    "corps",
    [
        {"couleur_base": "bleu"},
        {"couleur_base": "#12345"},
        {"couleurs": {"element_inconnu": "#ffffff"}},
        {"couleurs": {"orbe": "rouge"}},
        {"police": "comic-sans"},
        {"textes": {"accroche": "a\nb\nc\nd"}},
        {"textes": {"accroche": "x" * 121}},
        {"textes": {"merci": ""}},
        {"textes": {"merci": "x" * 201}},
        {"textes": {"texte_inconnu": "x"}},
        {"logo_url": "http://pas-https.example/logo.png"},
        {"lien_confidentialite": "javascript:alert(1)"},
        {"delai_s": 500},
        {"position": "milieu"},
        {"champ_inconnu": 1},
    ],
)
def test_une_apparence_invalide_est_refusee(corps):
    with pytest.raises(ValidationError):
        ApparenceWidget.model_validate(corps)


def test_police_celle_du_site_et_liste_fermee():
    assert ApparenceWidget(police="site").police == "site"
    assert ApparenceWidget(embleme="logo", logo_url="https://client.fr/logo.png").logo_url == "https://client.fr/logo.png"


# ----------------------------------------------------------------------------- canal
def test_le_canal_par_defaut_est_le_telephone_et_un_specialise_prend_celui_du_principal():
    assert lib_canal.canal_de(None) == "telephone"
    assert lib_canal.canal_de({"canal": "site"}) == "site"
    assert lib_canal.canal_de({"canal": "n'importe quoi"}) == "telephone"
    assert lib_canal.canal_de({}, {"canal": "site"}) == "site"
    assert lib_canal.canal_de({"canal": "site"}, {}) == "telephone"


def _outil(categorie, nom="outil", config=None):
    from types import SimpleNamespace

    return SimpleNamespace(category=categorie, name=nom, tool_uuid=nom, definition={"config": config or {}})


def test_un_agent_de_site_refuse_les_outils_de_transfert_d_appel():
    transfert = _outil(ToolCategory.TRANSFER_CALL.value, "transferer")
    personne = _outil(ToolCategory.INTEGRATION.value, "joindre", {"connecteur": "equipe", "action": "diriger_vers_personne"})
    http = _outil(ToolCategory.HTTP_API.value, "api")
    assert lib_canal.refus_transfert_sur_agent_de_site("site", [http]) is None
    assert "transferer" in lib_canal.refus_transfert_sur_agent_de_site("site", [http, transfert])
    assert "joindre" in lib_canal.refus_transfert_sur_agent_de_site("site", [personne])
    assert lib_canal.refus_transfert_sur_agent_de_site("telephone", [transfert, personne]) is None


def test_refus_de_cohérence_jeton_et_numero():
    assert lib_canal.refus_jeton_sur_agent("telephone")
    assert lib_canal.refus_jeton_sur_agent("site") is None
    assert lib_canal.refus_numero_sur_agent("site")
    assert lib_canal.refus_numero_sur_agent("telephone") is None


async def test_pas_de_nouveau_jeton_sur_un_agent_telephonique_mais_l_ancien_garde_le_sien(db_session, async_session):
    # Un agent téléphonique SANS jeton : refusé.
    organisation_id, user, sans_jeton = await creer_agent(db_session, async_session)
    # Un agent qui a DÉJÀ son jeton (avant U10) : sa mise à jour passe (zéro perte).
    _, _, _, avec_jeton = await creer_agent_avec_jeton(db_session, async_session, organisation_id=organisation_id)
    from api.routes import workflow_embed
    from api.routes.workflow_embed import EmbedTokenRequest
    from fastapi import HTTPException

    utilisateur = type("U", (), {"selected_organization_id": organisation_id, "id": user.id, "provider_id": "p"})()
    with pytest.raises(HTTPException) as refus:
        await workflow_embed.create_or_update_embed_token(
            sans_jeton.id, None, EmbedTokenRequest(allowed_domains=["client.fr"]), utilisateur
        )
    assert refus.value.status_code == 409
    mis_a_jour = await workflow_embed.create_or_update_embed_token(
        avec_jeton.workflow_id, None, EmbedTokenRequest(allowed_domains=["client.fr"]), utilisateur
    )
    assert mis_a_jour.token == avec_jeton.token


async def test_un_numero_ne_mene_pas_a_un_agent_de_site(db_session, async_session):
    from fastapi import HTTPException

    from api.routes.organization import _refuser_numero_sur_agent_de_site

    organisation_id, _, agent = await creer_agent(db_session, async_session)
    await _refuser_numero_sur_agent_de_site(agent.id, organisation_id)  # téléphonique : permis
    await db_session.save_workflow_draft(agent.id, workflow_configurations={"canal": "site"})
    with pytest.raises(HTTPException) as refus:
        await _refuser_numero_sur_agent_de_site(agent.id, organisation_id)
    assert refus.value.status_code == 409


# ----------------------------------------------------------------------------- routes du portail
async def _acces(db_session, nom, organisations, *, tous_les_clients=True):
    role = await db_session.creer_role(
        nom=f"Portail-{nom}",
        labo_ouvert=True,
        tous_les_clients=tous_les_clients,
        permissions=["agents.modifier"],
        organisations=[] if tous_les_clients else list(organisations),
    )
    user, jeton = await creer_compte(db_session, f"{nom}@example.com", organisations=organisations)
    await db_session.poser_membre(user.id, role)
    return jeton


async def test_le_canal_puis_l_emplacement_puis_la_configuration_de_bout_en_bout(db_session, async_session):
    config_site.vider_le_cache()
    org = await creer_organisation(db_session, "site-bout-en-bout")
    jeton_compte = await _acces(db_session, "boutenbout", [org])
    _, _, agent = await creer_agent(db_session, async_session, organisation_id=org)
    async with client_http() as c:
        h = entetes(jeton_compte, org)
        site = (await c.post(f"{API}/organizations/sites", headers=h, json={"nom": "Client", "allowed_domains": ["client.fr"]})).json()
        assert "?site=" + site["cle"] in site["script"]
        # Agent téléphonique : pas de widget.
        refuse = await c.put(f"{API}/organizations/agents-site/{agent.id}/emplacement", headers=h, json={"site_id": site["id"], "chemins": ["/"]})
        assert refuse.status_code == 409
        canal = await c.put(f"{API}/organizations/agents-site/{agent.id}/canal", headers=h, json={"canal": "site"})
        assert canal.status_code == 200 and canal.json()["canal"] == "site"
        place = await c.put(
            f"{API}/organizations/agents-site/{agent.id}/emplacement", headers=h, json={"site_id": site["id"], "chemins": ["/Tarifs/", "/aide"]}
        )
        assert place.status_code == 200, place.text
        assert place.json()["chemins"] == ["/tarifs", "/aide"]
        # Une autre fois sur le même chemin : refusé.
        _, _, autre = await creer_agent(db_session, async_session, organisation_id=org)
        await c.put(f"{API}/organizations/agents-site/{autre.id}/canal", headers=h, json={"canal": "site"})
        conflit = await c.put(
            f"{API}/organizations/agents-site/{autre.id}/emplacement", headers=h, json={"site_id": site["id"], "chemins": ["/aide"]}
        )
        assert conflit.status_code == 409
        # Apparence, puis lecture publique de la page.
        enregistre = await c.put(
            f"{API}/organizations/agents-site/{agent.id}/apparence", headers=h, json={"couleur_base": "#112233", "textes": {"accroche": "Bonjour\nà vous"}}
        )
        assert enregistre.status_code == 200, enregistre.text
        public = await c.get(f"{API}/public/embed/site/{site['cle']}/config", params={"chemin": "/tarifs"}, headers=ORIGINE)
        assert public.json()["apparence"]["couleur_base"] == "#112233"
        assert public.json()["apparence"]["textes"]["accroche"] == "Bonjour\nà vous"
        invalide = await c.put(f"{API}/organizations/agents-site/{agent.id}/apparence", headers=h, json={"couleur_base": "bleu"})
        assert invalide.status_code == 422
        # Réglages .mark : défauts, puis changement, puis hors bornes refusé.
        reglages = (await c.get(f"{API}/organizations/agents-site/{agent.id}/reglages", headers=h)).json()
        assert (reglages["plafond_conversations_mois"], reglages["duree_max_s"], reglages["sessions_par_heure_et_ip"]) == (500, 600, 10)
        change = await c.put(f"{API}/organizations/agents-site/{agent.id}/reglages", headers=h, json={"duree_max_s": 900, "allowed_domains": ["client.fr"]})
        assert change.status_code == 200 and change.json()["duree_max_s"] == 900 and change.json()["plafond_minutes_mois"] == 1500
        assert (await c.put(f"{API}/organizations/agents-site/{agent.id}/reglages", headers=h, json={"duree_max_s": 5})).status_code == 422
        # Agents servis : ce que lisent les appels est la version PUBLIÉE ; publiée, le canal « site » se lit.
        avant = (await c.get(f"{API}/organizations/agents-servis", headers=h)).json()
        assert next(a for a in avant["agents"] if a["id"] == agent.id)["canal"] == "telephone"
        await db_session.publish_workflow_draft(agent.id)
        # La session des tests est partagée : ses lignes déjà lues (versions chargées avant la publication) sont relues.
        async_session.expire_all()
        servis = (await c.get(f"{API}/organizations/agents-servis", headers=h)).json()
    ligne = next(a for a in servis["agents"] if a["id"] == agent.id)
    assert ligne["canal"] == "site"
    assert ligne["emplacement"]["chemins"] == ["/tarifs", "/aide"] and ligne["emplacement"]["site_cle"] == site["cle"]
    assert ligne["emplacement"]["widget_actif"] is True


async def test_un_agent_de_site_avec_un_outil_de_transfert_est_refuse(db_session, async_session):
    org = await creer_organisation(db_session, "site-transfert")
    jeton_compte = await _acces(db_session, "transfert", [org])
    _, user, agent = await creer_agent(db_session, async_session, organisation_id=org)
    outil = await db_session.create_tool(
        organization_id=org, user_id=user.id, name="Transférer", definition={"config": {}}, category=ToolCategory.TRANSFER_CALL.value
    )
    await db_session.save_workflow_draft(
        agent.id, workflow_definition={"nodes": [{"id": "1", "type": "agentNode", "data": {"tool_uuids": [outil.tool_uuid]}}], "edges": []}
    )
    async with client_http() as c:
        refus = await c.put(f"{API}/organizations/agents-site/{agent.id}/canal", headers=entetes(jeton_compte, org), json={"canal": "site"})
    assert refus.status_code == 409 and "Transférer" in refus.json()["detail"]


async def test_un_spécialise_prend_le_canal_de_son_principal():
    principal = AgentLu(id=1, nom="Accueil", version_publiee=1, configurations={"canal": "site", "agents_specialises": [2]})
    specialise = AgentLu(id=2, nom="Tarifs", version_publiee=1, configurations={"agent_principal_id": 1})
    seul = AgentLu(id=3, nom="Standard", version_publiee=1, configurations={})
    servis = assembler([principal, specialise, seul], {}, set())
    canaux = {a.id: a.canal for a in servis.agents}
    assert canaux == {1: "site", 2: "site", 3: "telephone"}


# ----------------------------------------------------------------------------- autre organisation (refus)
async def test_chaque_route_du_portail_refuse_la_cle_d_une_autre_organisation(db_session, async_session):
    org_a = await creer_organisation(db_session, "site-org-a")
    org_b = await creer_organisation(db_session, "site-org-b")
    _, _, agent_a = await creer_agent(db_session, async_session, organisation_id=org_a)
    site_a = await db_session.creer_site(org_a, "Site A", ["a.fr"])
    jeton_a = await db_session.create_embed_token(workflow_id=agent_a.id, organization_id=org_a, created_by=agent_a.user_id)
    await db_session.poser_emplacement(org_a, jeton_a.id, site_a.id, ["/"])
    jeton_b = await _acces(db_session, "orgb", [org_b], tous_les_clients=False)
    h = entetes(jeton_b, org_b)
    base = f"{API}/organizations/agents-site/{agent_a.id}"
    async with client_http() as c:
        reponses = {
            "lire emplacement": await c.get(base, headers=h),
            "régler canal": await c.put(f"{base}/canal", headers=h, json={"canal": "site"}),
            "poser emplacement": await c.put(f"{base}/emplacement", headers=h, json={"site_id": site_a.id, "chemins": ["/"]}),
            "lire apparence": await c.get(f"{base}/apparence", headers=h),
            "régler apparence": await c.put(f"{base}/apparence", headers=h, json={"couleur_base": "#000000"}),
            "lire réglages": await c.get(f"{base}/reglages", headers=h),
            "régler réglages": await c.put(f"{base}/reglages", headers=h, json={"duree_max_s": 61}),
            "lire le site": await c.post(f"{base}/lire-site", headers=h, json={}),
            "régler un site": await c.put(f"{API}/organizations/sites/{site_a.id}", headers=h, json={"nom": "Pris"}),
        }
        sites_b = (await c.get(f"{API}/organizations/sites", headers=h)).json()
        servis_b = (await c.get(f"{API}/organizations/agents-servis", headers=h)).json()
        # L'agent de B pose son jeton sur le site de A : le site de A n'existe pas pour B.
        _, _, agent_b = await creer_agent(db_session, async_session, organisation_id=org_b)
        await c.put(f"{API}/organizations/agents-site/{agent_b.id}/canal", headers=h, json={"canal": "site"})
        croise = await c.put(f"{API}/organizations/agents-site/{agent_b.id}/emplacement", headers=h, json={"site_id": site_a.id, "chemins": ["/"]})
        # Et l'en-tête de l'organisation A, où le compte B n'est pas membre, est refusé par la porte d'accès.
        porte = await c.get(base, headers=entetes(jeton_b, org_a))
    mauvaises = {nom: r.status_code for nom, r in reponses.items() if r.status_code != 404}
    assert not mauvaises, mauvaises
    assert sites_b == [] and all(a["id"] != agent_a.id for a in servis_b["agents"])
    assert croise.status_code == 404
    assert porte.status_code == 403
    # Rien n'a bougé chez A.
    assert (await db_session.lire_site(site_a.id, org_a)).nom == "Site A"
    assert [c.chemin for c in await db_session.lire_chemins_du_site(site_a.id)] == ["/"]


# ----------------------------------------------------------------------------- Couleur de mon site (D203)
def _reponse_enregistree(nom, statut=200, entetes=None):
    corps = (DONNEES / nom).read_bytes()

    async def morceaux():
        for i in range(0, len(corps), 4096):
            yield corps[i : i + 4096]

    return lecture_site.ReponseHttp(statut, entetes or {"content-type": "text/html; charset=utf-8"}, morceaux())


class ReseauEnregistre:
    """Un faux réseau : ``noms`` associe un hôte à ses adresses ; ``pages`` à sa réponse (fichier enregistré)."""

    def __init__(self, noms, pages):
        self.noms, self.pages, self.appels = noms, pages, []

    async def resoudre(self, hote):
        return self.noms.get(hote, [])

    async def ouvrir(self, ip, hote, cible):
        self.appels.append((ip, hote, cible))
        return self.pages[(hote, cible)]()


DOMAINES = ["client.fr"]


async def test_la_couleur_du_site_est_lue_dans_une_page_enregistree():
    reseau = ReseauEnregistre(
        {"client.fr": ["93.184.216.34"]}, {("client.fr", "/"): lambda: _reponse_enregistree("accueil-theme-color.html")}
    )
    lue = await lecture_site.lire_couleur_du_site("https://client.fr/", DOMAINES, resoudre=reseau.resoudre, ouvrir=reseau.ouvrir)
    assert lue.couleur == "#1f6f4a" and lue.sources == ["theme-color"]
    assert lue.logo_url == "https://client.fr/img/logo.png"
    assert reseau.appels == [("93.184.216.34", "client.fr", "/")]  # la connexion va à l'adresse vérifiée


async def test_la_couleur_vient_des_variables_css_sans_theme_color():
    reseau = ReseauEnregistre({"client.fr": ["93.184.216.34"]}, {("client.fr", "/"): lambda: _reponse_enregistree("accueil-variable-css.html")})
    lue = await lecture_site.lire_couleur_du_site("https://client.fr/", DOMAINES, resoudre=reseau.resoudre, ouvrir=reseau.ouvrir)
    assert lue.couleur == "#aa3300" and lue.sources == ["css-variable"]
    assert lue.logo_url is None  # l'adresse du script n'est jamais lue


async def test_un_domaine_non_autorise_est_refuse_sans_aucune_requete():
    reseau = ReseauEnregistre({"autre.example": ["93.184.216.34"]}, {})
    for adresse in ("https://autre.example/", "http://client.fr/", "https://client.fr:8443/", "https://user:pw@client.fr/"):
        with pytest.raises(lecture_site.LectureRefusee):
            await lecture_site.lire_couleur_du_site(adresse, DOMAINES, resoudre=reseau.resoudre, ouvrir=reseau.ouvrir)
    with pytest.raises(lecture_site.LectureRefusee):  # « * » seul ne donne aucun droit de lecture
        await lecture_site.lire_couleur_du_site("https://autre.example/", ["*"], resoudre=reseau.resoudre, ouvrir=reseau.ouvrir)
    assert reseau.appels == []


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "192.168.1.10", "172.16.0.3", "::1", "fe80::1", "0.0.0.0", "100.64.0.1"])
async def test_un_domaine_autorise_qui_resout_vers_une_adresse_interne_est_refuse(ip):
    reseau = ReseauEnregistre({"client.fr": [ip]}, {})
    with pytest.raises(lecture_site.LectureRefusee) as refus:
        await lecture_site.lire_couleur_du_site("https://client.fr/", DOMAINES, resoudre=reseau.resoudre, ouvrir=reseau.ouvrir)
    assert refus.value.code == "adresse_interne"
    assert reseau.appels == []


async def test_une_resolution_mixte_dont_une_adresse_interne_est_refusee():
    reseau = ReseauEnregistre({"client.fr": ["93.184.216.34", "10.0.0.5"]}, {})
    with pytest.raises(lecture_site.LectureRefusee):
        await lecture_site.lire_couleur_du_site("https://client.fr/", DOMAINES, resoudre=reseau.resoudre, ouvrir=reseau.ouvrir)


async def test_une_redirection_vers_une_adresse_interne_ou_un_autre_domaine_est_refusee():
    def vers(destination):
        return lambda: _reponse_enregistree("vide.html", 302, {"location": destination, "content-type": "text/html"})

    for destination in ("https://interne.client.fr/admin", "https://autre.example/", "http://client.fr/", "https://127.0.0.1/"):
        reseau = ReseauEnregistre(
            {"client.fr": ["93.184.216.34"], "interne.client.fr": ["10.0.0.9"], "autre.example": ["93.184.216.35"]},
            {("client.fr", "/"): vers(destination)},
        )
        with pytest.raises(lecture_site.LectureRefusee):
            await lecture_site.lire_couleur_du_site("https://client.fr/", DOMAINES, resoudre=reseau.resoudre, ouvrir=reseau.ouvrir)
        assert len(reseau.appels) == 1  # la seconde adresse n'a jamais été ouverte


async def test_une_redirection_vers_un_domaine_autorise_est_suivie_trois_fois_au_plus():
    pages = {("client.fr", "/"): lambda: _reponse_enregistree("vide.html", 301, {"location": "/accueil", "content-type": "text/html"}),
             ("client.fr", "/accueil"): lambda: _reponse_enregistree("accueil-theme-color.html")}
    reseau = ReseauEnregistre({"client.fr": ["93.184.216.34"]}, pages)
    lue = await lecture_site.lire_couleur_du_site("https://client.fr/", DOMAINES, resoudre=reseau.resoudre, ouvrir=reseau.ouvrir)
    assert lue.couleur == "#1f6f4a"
    boucle = ReseauEnregistre(
        {"client.fr": ["93.184.216.34"]},
        {("client.fr", "/"): lambda: _reponse_enregistree("vide.html", 301, {"location": "/", "content-type": "text/html"})},
    )
    with pytest.raises(lecture_site.LectureRefusee) as refus:
        await lecture_site.lire_couleur_du_site("https://client.fr/", DOMAINES, resoudre=boucle.resoudre, ouvrir=boucle.ouvrir)
    assert refus.value.code == "trop_de_redirections" and len(boucle.appels) == lecture_site.REDIRECTIONS_MAX + 1


async def test_une_page_de_cinq_megaoctets_est_coupee_a_un_megaoctet():
    lu = {"octets": 0}

    async def enorme():
        for _ in range(5):
            yield b"<html><head><meta name='theme-color' content='#123456'></head>" if lu["octets"] == 0 else b"x" * 1_000_000
            lu["octets"] += 1_000_000

    reponse = lambda: lecture_site.ReponseHttp(200, {"content-type": "text/html"}, enorme())  # noqa: E731
    reseau = ReseauEnregistre({"client.fr": ["93.184.216.34"]}, {("client.fr", "/"): reponse})
    html, _ = await lecture_site.lire_page("https://client.fr/", DOMAINES, resoudre=reseau.resoudre, ouvrir=reseau.ouvrir)
    assert len(html) <= lecture_site.TAILLE_MAX + 100
    assert lu["octets"] < 5_000_000  # la lecture s'est arrêtée


async def test_un_type_autre_que_html_et_un_delai_depasse_sont_des_erreurs_propres(monkeypatch):
    reseau = ReseauEnregistre(
        {"client.fr": ["93.184.216.34"]},
        {("client.fr", "/"): lambda: _reponse_enregistree("accueil-theme-color.html", 200, {"content-type": "application/pdf"})},
    )
    with pytest.raises(lecture_site.LectureRefusee) as refus:
        await lecture_site.lire_couleur_du_site("https://client.fr/", DOMAINES, resoudre=reseau.resoudre, ouvrir=reseau.ouvrir)
    assert refus.value.code == "type_refuse"

    async def lent(*_):
        await asyncio.sleep(10)

    monkeypatch.setattr(lecture_site, "DELAI_S", 0.2)
    with pytest.raises(lecture_site.LectureRefusee) as refus:
        await lecture_site.lire_couleur_du_site("https://client.fr/", DOMAINES, resoudre=lambda h: lent(h), ouvrir=lent)
    assert refus.value.code == "delai_depasse"


async def test_la_route_lire_site_limite_a_dix_par_heure_et_exige_un_domaine(db_session, async_session):
    org = await creer_organisation(db_session, "site-lecture")
    jeton_compte = await _acces(db_session, "lecture", [org])
    _, _, agent, jeton = await creer_agent_avec_jeton(db_session, async_session, organisation_id=org)
    h = entetes(jeton_compte, org)
    url = f"{API}/organizations/agents-site/{agent.id}/lire-site"
    reseau = ReseauEnregistre({"client.fr": ["93.184.216.34"]}, {("client.fr", "/"): lambda: _reponse_enregistree("accueil-theme-color.html")})
    with limiteur_en_memoire(), patch.object(lecture_site, "resoudre_dns", reseau.resoudre), patch.object(lecture_site, "ouvrir_httpx", reseau.ouvrir):
        async with client_http() as c:
            sans_domaine = await c.post(url, headers=h, json={})
            await c.put(f"{API}/organizations/agents-site/{agent.id}/reglages", headers=h, json={"allowed_domains": ["client.fr"]})
            lues = [await c.post(url, headers=h, json={}) for _ in range(11)]
    assert sans_domaine.status_code == 422
    assert [r.status_code for r in lues] == [200] * 10 + [429]
    assert lues[0].json() == {"couleur": "#1f6f4a", "logo_url": "https://client.fr/img/logo.png", "sources": ["theme-color"]}
