"""[.mark] Builder partie 2, U10.3 / lot S3 : le chemin d'une conversation du widget jusqu'à la base du client, et les
routes publiques de l'avis, du rappel et de l'événement.

Vraie application, vraie base de Dograh, vraie base du client (le rattachement est remplacé par la base de test).
Le cloisonnement d'abord : une session, une clé de site ou un domaine d'une autre organisation est refusé.

| Test | Ce qu'il prouve |
|---|---|
| widget ou essai | un run du widget est une vraie conversation (canal site, page, mode) ; un run de l'écran de Dograh reste un essai |
| avis : accès | domaine non autorisé 403, session inconnue 404, session d'une autre organisation : jamais écrit chez l'autre |
| avis : règles | pas avant la fin (409), une fois (409), bornes (422), rappel sans coordonnées (422) |
| avis : base | écrit dans la base de l'organisation de la session ; avant la conversation, il attend sur le run et entre avec elle |
| rappel | refusé tant que le plafond n'est pas atteint, domaine contrôlé, limité par adresse, écrit une demande « rappel » |
| événements | comptés par jour et par agent, domaine contrôlé ; le portail ne lit que les agents de son organisation |
| conservation | les sessions du widget plus vieilles que la durée écrite sont effacées, les récentes restent |
| relance d'une action | l'action d'une autre organisation n'existe pas ; seule une action en échec repart ; un échec définitif est refusé |
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.db.bases_clients import apres_appel as sql
from api.db.bases_clients import connexion as schema
from api.schemas.apres_appel import ApresAppelAgent, ReglagesApresAppel
from api.services.apres_appel import chaine
from api.services.apres_appel.envoi import construire_envoi
from api.services.apres_appel.modules import ContexteModule
from api.services.site_mark import config_site
from api.services.site_mark.conservation import purger_sessions
from api.services.site_mark.conversations import (
    CONSERVATION_SESSIONS_JOURS,
    champs_du_site,
    est_du_widget,
    mode_de,
    page_de,
)
from api.tests.mark.equipe_commun import client_http, creer_compte, entetes
from api.tests.mark.site_commun import creer_agent_avec_jeton, limiteur_en_memoire
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401

API = "/api/v1"
INIT = f"{API}/public/embed/init"
CLIENT = {"Origin": "https://client.fr"}
AILLEURS = {"Origin": "https://evil.example"}

AVIS = {"etoiles": 4, "obtenu": "oui", "raisons": ["clair"], "commentaire": "Merci"}


# --------------------------------------------------------------------------- #
# Le décor
# --------------------------------------------------------------------------- #


async def _widget(db_session, async_session, *, reglages_mark=None, organisation_id=None, chemins=("/",)):
    """Un agent de site : jeton, site (domaine client.fr), emplacement."""
    org, user, wf, jeton = await creer_agent_avec_jeton(
        db_session,
        async_session,
        organisation_id=organisation_id,
        allowed_domains=["client.fr"],
        reglages_mark=reglages_mark,
    )
    site = await db_session.creer_site(org, "Site du client", ["client.fr"])
    await db_session.poser_emplacement(org, jeton.id, site.id, list(chemins))
    config_site.vider_le_cache()
    return SimpleNamespace(org=org, user=user, wf=wf, jeton=jeton, site=site)


async def _session(client, w, contexte=None):
    corps = {"token": w.jeton.token}
    if contexte is not None:
        corps["context_variables"] = contexte
    r = await client.post(INIT, json=corps, headers=CLIENT)
    assert r.status_code == 200, r.text
    return r.json()


@contextmanager
def _base_du_client(nom_base, organisations_vues=None):
    """Le rattachement de l'organisation remplacé par la base de test ; les organisations vues sont notées."""
    from api.routes import public_embed_conversations as routes

    async def ecrire(organization_id, operation):
        if organisations_vues is not None:
            organisations_vues.append(organization_id)
        connexion = await schema.connecter(nom_base)
        try:
            return await operation(connexion)
        finally:
            await connexion.close()

    with patch.object(routes, "_ecrire_dans_la_base", ecrire), patch.object(
        routes, "_base_rattachee", AsyncMock(return_value=True)
    ):
        yield


async def _appel_dans_la_base(nom_base, run_id, **plus):
    from api.tests.mark.test_apres_appel import _envoi

    connexion = await schema.connecter(nom_base)
    try:
        return await sql.recevoir_appel(
            connexion,
            _envoi(run_id, numero=None, canal="site", demande=None, contact={}, **plus),
        )
    finally:
        await connexion.close()


# --------------------------------------------------------------------------- #
# Widget ou essai
# --------------------------------------------------------------------------- #


async def test_un_run_du_widget_est_une_vraie_conversation_et_un_essai_de_l_ecran_reste_un_essai(
    db_session, async_session
):
    w = await _widget(db_session, async_session)
    with limiteur_en_memoire():
        async with client_http() as c:
            session = await _session(c, w, {"page_url": "https://client.fr/Tarifs/?x=1#haut"})
    run = await db_session.get_workflow_run(session["workflow_run_id"], organization_id=w.org)
    assert est_du_widget(run)
    assert page_de(run) == "/tarifs" and mode_de(run) == "voix"
    assert champs_du_site(run) == {"canal": "site", "mode_site": "voix", "page": "/tarifs"}
    agent = ApresAppelAgent(actif=True)
    assert chaine.est_un_essai_exclu(run, agent) is False  # même mode « navigateur », mais c'est le widget
    # Un test lancé depuis l'écran de Dograh : même moteur, ni annotation ni marqueur.
    essai = SimpleNamespace(mode="smallwebrtc", annotations={}, initial_context={"page_url": "https://client.fr/x"})
    assert est_du_widget(essai) is False and champs_du_site(essai) == {}
    assert chaine.est_un_essai_exclu(essai, agent) is True
    # Une page ne peut pas se déclarer widget : la clé réservée est écartée de son contexte.
    with limiteur_en_memoire():
        async with client_http() as c:
            triche = await _session(c, w, {"canal_mark": "site", "embed": "x"})
    run_triche = await db_session.get_workflow_run(triche["workflow_run_id"], organization_id=w.org)
    assert run_triche.initial_context["canal_mark"] == "site" and "embed" not in run_triche.initial_context  # posé par le serveur
    # Le mode écrit et la bascule vers l'écrit en cours de voix.
    ecrit = SimpleNamespace(mode="textchat", annotations={"embed": {"source": "embed_widget", "modality": "text"}}, initial_context={})
    assert mode_de(ecrit) == "ecrit"
    bascule = SimpleNamespace(mode="smallwebrtc", annotations={"embed": {"source": "embed_widget", "modes": ["voix", "ecrit"]}}, initial_context={})
    assert mode_de(bascule) == "voix_puis_ecrit"


async def test_l_envoi_d_un_run_du_widget_porte_canal_page_mode_et_celui_d_un_autre_reste_le_meme():
    agent = ApresAppelAgent(actif=True)
    base = dict(
        id=5, workflow_id=7, definition_id=70, definition=None, workflow=None, logs={}, usage_info={},
        gathered_context={}, cost_info={}, created_at=datetime.now(UTC), is_completed=True, call_type=None,
    )
    widget = SimpleNamespace(
        **base, mode="smallwebrtc",
        annotations={"embed": {"source": "embed_widget", "modality": "voice", "avis": {"etoiles": 5}}},
        initial_context={"page_url": "https://client.fr/aide", "canal_mark": "site"},
    )
    ecran = SimpleNamespace(**base, mode="smallwebrtc", annotations={}, initial_context={})
    envoi_widget = construire_envoi(widget, {}, agent)
    envoi_ecran = construire_envoi(ecran, {}, agent)
    assert (envoi_widget["canal"], envoi_widget["page"], envoi_widget["mode_site"]) == ("site", "/aide", "voix")
    assert envoi_widget["avis"] == {"etoiles": 5}
    assert envoi_ecran["canal"] == "navigateur"
    assert not {"page", "mode_site", "avis"} & set(envoi_ecran)


# --------------------------------------------------------------------------- #
# L'avis : accès
# --------------------------------------------------------------------------- #


async def test_l_avis_refuse_un_autre_domaine_une_session_inconnue_et_n_ecrit_que_chez_son_organisation(
    db_session, async_session, base_prete
):
    w = await _widget(db_session, async_session)
    autre = await _widget(db_session, async_session)
    with limiteur_en_memoire():
        async with client_http() as c:
            session = await _session(c, w)
            await db_session.update_workflow_run(session["workflow_run_id"], is_completed=True)
            url = f"{API}/public/embed/avis/{session['session_token']}"
            assert (await c.post(url, json=AVIS, headers=AILLEURS)).status_code == 403
            inconnue = await c.post(f"{API}/public/embed/avis/emb_session_inconnue", json=AVIS, headers=CLIENT)
            assert inconnue.status_code == 404
            vues: list[int] = []
            with _base_du_client(base_prete, vues):
                ok = await c.post(url, json=AVIS, headers=CLIENT)
    assert ok.status_code == 200, ok.text
    assert vues == [w.org] and autre.org not in vues  # jamais la base d'une autre organisation


# --------------------------------------------------------------------------- #
# L'avis : règles
# --------------------------------------------------------------------------- #


async def test_l_avis_ni_avant_la_fin_ni_deux_fois_et_borne(db_session, async_session, base_prete):
    w = await _widget(db_session, async_session)
    with limiteur_en_memoire():
        async with client_http() as c:
            session = await _session(c, w)
            url = f"{API}/public/embed/avis/{session['session_token']}"
            with _base_du_client(base_prete):
                avant = await c.post(url, json=AVIS, headers=CLIENT)
                assert avant.status_code == 409 and avant.json()["detail"]["code"] == "conversation_not_finished"
                await db_session.update_workflow_run(session["workflow_run_id"], is_completed=True)
                # Les bornes et les champs inconnus.
                assert (await c.post(url, json={**AVIS, "etoiles": 6}, headers=CLIENT)).status_code == 422
                assert (await c.post(url, json={**AVIS, "etoiles": 0}, headers=CLIENT)).status_code == 422
                assert (await c.post(url, json={**AVIS, "intrus": 1}, headers=CLIENT)).status_code == 422
                assert (await c.post(url, json={**AVIS, "commentaire": "x" * 2001}, headers=CLIENT)).status_code == 422
                assert (await c.post(url, json={**AVIS, "contact": {"mail": "pas-un-mail"}}, headers=CLIENT)).status_code == 422
                assert (await c.post(url, json={**AVIS, "contact": {"telephone": "abc"}}, headers=CLIENT)).status_code == 422
                # Un rappel demandé sans moyen de rappeler.
                sans_moyen = await c.post(url, json={**AVIS, "etoiles": 1, "rappel_demande": True}, headers=CLIENT)
                assert sans_moyen.status_code == 422
                premier = await c.post(url, json=AVIS, headers=CLIENT)
                second = await c.post(url, json={**AVIS, "etoiles": 1}, headers=CLIENT)
    assert premier.status_code == 200
    assert second.status_code == 409 and second.json()["detail"]["code"] == "review_already_given"


# --------------------------------------------------------------------------- #
# L'avis : la base du client
# --------------------------------------------------------------------------- #


async def test_l_avis_entre_dans_la_base_et_un_avis_avant_la_conversation_entre_avec_elle(
    db_session, async_session, base_prete
):
    w = await _widget(db_session, async_session)
    with limiteur_en_memoire():
        async with client_http() as c:
            # 1. La conversation est déjà dans la base : l'avis y entre tout de suite, coordonnées comprises.
            s1 = await _session(c, w)
            run1 = s1["workflow_run_id"]
            await db_session.update_workflow_run(run1, is_completed=True)
            res1 = await _appel_dans_la_base(base_prete, run1)
            contact = {"nom": "Claire", "telephone": "06 44 44 55 55", "mail": "Claire@Exemple.fr"}
            with _base_du_client(base_prete):
                r1 = await c.post(
                    f"{API}/public/embed/avis/{s1['session_token']}",
                    json={**AVIS, "etoiles": 2, "rappel_demande": True, "contact": contact},
                    headers=CLIENT,
                )
            assert r1.status_code == 200, r1.text
            # 2. La conversation n'est pas encore dans la base : l'avis attend sur le run.
            s2 = await _session(c, w)
            run2 = s2["workflow_run_id"]
            await db_session.update_workflow_run(run2, is_completed=True)
            with _base_du_client(base_prete):
                r2 = await c.post(
                    f"{API}/public/embed/avis/{s2['session_token']}", json={**AVIS, "etoiles": 5}, headers=CLIENT
                )
            assert r2.status_code == 200
    connexion = await schema.connecter(base_prete)
    try:
        ligne = await connexion.fetchrow("SELECT etoiles, rappel_demande FROM mark.avis WHERE appel_id = $1", res1["appel_id"])
        assert dict(ligne) == {"etoiles": 2, "rappel_demande": True}
        contact_id = await connexion.fetchval("SELECT contact_id FROM mark.appel WHERE id = $1", res1["appel_id"])
        assert await connexion.fetchval("SELECT mail FROM mark.contact WHERE id = $1", contact_id) == "claire@exemple.fr"
        assert await connexion.fetchval("SELECT contact_id FROM mark.telephone WHERE numero = '+33644445555'") == contact_id
        assert await connexion.fetchval("SELECT count(*) FROM mark.demande WHERE type = 'rappel'") == 1
        # Plus de coordonnées dans Dograh une fois l'avis écrit chez le client.
        run_1 = await db_session.get_workflow_run(run1, organization_id=w.org)
        assert run_1.annotations["embed"]["avis"].get("ecrit") is True and "contact" not in run_1.annotations["embed"]["avis"]
        # L'avis de la seconde attend sur le run, puis entre avec sa conversation.
        run_2 = await db_session.get_workflow_run(run2, organization_id=w.org)
        envoi = construire_envoi(run_2, {}, ApresAppelAgent(actif=True))
        assert envoi["avis"]["etoiles"] == 5
        assert await connexion.fetchval("SELECT count(*) FROM mark.avis") == 1
        await sql.recevoir_appel(connexion, {**_envoi_minimal(run2), "avis": envoi["avis"]})
        assert await connexion.fetchval("SELECT count(*) FROM mark.avis") == 2
    finally:
        await connexion.close()


def _envoi_minimal(run_id):
    from api.tests.mark.test_apres_appel import _envoi

    return _envoi(run_id, numero=None, canal="site", demande=None, contact={})


async def test_sans_base_rattachee_l_avis_attend_sur_le_run_sans_erreur(db_session, async_session):
    w = await _widget(db_session, async_session)
    with limiteur_en_memoire():
        async with client_http() as c:
            session = await _session(c, w)
            await db_session.update_workflow_run(session["workflow_run_id"], is_completed=True)
            r = await c.post(f"{API}/public/embed/avis/{session['session_token']}", json=AVIS, headers=CLIENT)
    assert r.status_code == 200
    run = await db_session.get_workflow_run(session["workflow_run_id"], organization_id=w.org)
    assert run.annotations["embed"]["avis"]["etoiles"] == 4


async def test_sans_base_rattachee_l_avis_ne_garde_ni_coordonnees_ni_commentaire(db_session, async_session):
    """Revue serveur M6 : sans base rattachée, rien ne recevra les coordonnées ni le texte libre du visiteur."""
    w = await _widget(db_session, async_session)
    contact = {"nom": "Claire", "telephone": "06 44 44 55 55", "mail": "claire@exemple.fr"}
    with limiteur_en_memoire():
        async with client_http() as c:
            session = await _session(c, w)
            await db_session.update_workflow_run(session["workflow_run_id"], is_completed=True)
            r = await c.post(
                f"{API}/public/embed/avis/{session['session_token']}",
                json={**AVIS, "rappel_demande": True, "contact": contact},
                headers=CLIENT,
            )
    assert r.status_code == 200, r.text
    run = await db_session.get_workflow_run(session["workflow_run_id"], organization_id=w.org)
    avis = run.annotations["embed"]["avis"]
    assert avis["etoiles"] == 4 and avis["obtenu"] == "oui"
    assert "contact" not in avis and "commentaire" not in avis
    assert "Claire" not in json.dumps(run.annotations) and "Merci" not in json.dumps(run.annotations)


async def test_l_avis_en_attente_est_reduit_des_que_sa_conversation_entre_dans_la_base(
    db_session, async_session, base_prete
):
    """Revue serveur M6 : l'après-appel écrit la conversation avec son avis, puis Dograh n'en garde que le fait."""
    w = await _widget(db_session, async_session)
    contact = {"nom": "Claire", "telephone": "06 44 44 55 55"}
    with limiteur_en_memoire():
        async with client_http() as c:
            session = await _session(c, w)
            run_id = session["workflow_run_id"]
            await db_session.update_workflow_run(run_id, is_completed=True)
            with _base_du_client(base_prete):
                r = await c.post(
                    f"{API}/public/embed/avis/{session['session_token']}",
                    json={**AVIS, "rappel_demande": True, "contact": contact},
                    headers=CLIENT,
                )
    assert r.status_code == 200, r.text
    run = await db_session.get_workflow_run(run_id, organization_id=w.org)
    assert run.annotations["embed"]["avis"]["contact"]["nom"] == "Claire"  # en attente : entier, pour la base
    envoi = {**_envoi_minimal(run_id), "avis": construire_envoi(run, {}, ApresAppelAgent(actif=True))["avis"]}
    ctx = ContexteModule(
        organization_id=w.org, run=run, reglages=ReglagesApresAppel(), agent=ApresAppelAgent(actif=True), envoi=envoi
    )

    async def la_base_de_test(_organization_id):
        return await schema.connecter(base_prete)

    with patch.object(chaine, "_base", la_base_de_test):
        await chaine._ecriture(ctx, {})
    connexion = await schema.connecter(base_prete)
    try:
        assert await connexion.fetchval("SELECT count(*) FROM mark.avis") == 1
    finally:
        await connexion.close()
    apres = await db_session.get_workflow_run(run_id, organization_id=w.org)
    assert set(apres.annotations["embed"]["avis"]) == {"ecrit", "le"}
    assert "Claire" not in json.dumps(apres.annotations)


# --------------------------------------------------------------------------- #
# Le rappel
# --------------------------------------------------------------------------- #


async def test_le_rappel_n_est_permis_qu_au_plafond_atteint_et_ecrit_une_demande(db_session, async_session, base_prete):
    w = await _widget(db_session, async_session, reglages_mark={"plafond_conversations_mois": 1}, chemins=("/", "/aide"))
    url = f"{API}/public/embed/rappel/{w.site.cle}"
    corps = {"chemin": "/aide", "contact": {"nom": "Léa", "telephone": "0655556666"}, "message": "Rappelez-moi"}
    with limiteur_en_memoire():
        async with client_http() as c:
            with _base_du_client(base_prete):
                pas_encore = await c.post(url, json=corps, headers=CLIENT)
                assert pas_encore.status_code == 409 and pas_encore.json()["detail"]["code"] == "cap_not_reached"
                await _session(c, w)  # la seule conversation du mois
                refuse = await c.post(INIT, json={"token": w.jeton.token}, headers=CLIENT)
                assert refuse.status_code == 403 and refuse.json()["detail"]["code"] == "monthly_cap_reached"
                # Les contrôles d'accès.
                assert (await c.post(url, json=corps, headers=AILLEURS)).status_code == 403
                assert (await c.post(f"{API}/public/embed/rappel/site_inconnu", json=corps, headers=CLIENT)).status_code == 404
                assert (await c.post(url, json={**corps, "contact": {"nom": "Sans moyen"}}, headers=CLIENT)).status_code == 422
                assert (await c.post(url, json={**corps, "chemin": "/a/../b"}, headers=CLIENT)).status_code == 400
                ok = await c.post(url, json=corps, headers=CLIENT)
    assert ok.status_code == 200, ok.text
    connexion = await schema.connecter(base_prete)
    try:
        ligne = await connexion.fetchrow("SELECT type, resume, contact_id FROM mark.demande WHERE type = 'rappel'")
        assert ligne and "/aide" in ligne["resume"] and "Rappelez-moi" in ligne["resume"]
        assert await connexion.fetchval("SELECT contact_id FROM mark.telephone WHERE numero = '+33655556666'") == ligne["contact_id"]
    finally:
        await connexion.close()


async def test_le_rappel_est_limite_par_adresse(db_session, async_session, base_prete):
    w = await _widget(db_session, async_session, reglages_mark={"plafond_conversations_mois": 1})
    url = f"{API}/public/embed/rappel/{w.site.cle}"
    corps = {"contact": {"mail": "lea@exemple.fr"}}
    with limiteur_en_memoire():
        async with client_http() as c:
            await _session(c, w)
            with _base_du_client(base_prete):
                codes = [(await c.post(url, json=corps, headers=CLIENT)).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]


async def test_le_rappel_sans_agent_pour_la_page_ou_sans_base_repond_proprement(db_session, async_session, base_prete):
    w = await _widget(db_session, async_session, reglages_mark={"plafond_conversations_mois": 1}, chemins=("/aide",))
    url = f"{API}/public/embed/rappel/{w.site.cle}"
    with limiteur_en_memoire():
        async with client_http() as c:
            sans_agent = await c.post(url, json={"chemin": "/tarifs", "contact": {"mail": "a@b.fr"}}, headers=CLIENT)
            assert sans_agent.status_code == 404
            await _session(c, w)
            sans_base = await c.post(url, json={"chemin": "/aide", "contact": {"mail": "a@b.fr"}}, headers=CLIENT)
    assert sans_base.status_code == 503 and sans_base.json()["detail"]["code"] == "unavailable"


# --------------------------------------------------------------------------- #
# Les événements anonymes
# --------------------------------------------------------------------------- #


async def _acces(db_session, nom, organisations):
    role = await db_session.creer_role(
        nom=f"Portail-{nom}", labo_ouvert=True, tous_les_clients=False,
        permissions=["agents.modifier"], organisations=list(organisations),
    )
    user, jeton = await creer_compte(db_session, f"{nom}@example.com", organisations=organisations)
    await db_session.poser_membre(user.id, role)
    return jeton


async def test_les_evenements_sont_comptes_par_jour_et_le_portail_ne_lit_que_son_organisation(db_session, async_session):
    a = await _widget(db_session, async_session)
    b = await _widget(db_session, async_session)
    jeton_a = await _acces(db_session, "evt-a", [a.org])
    jeton_b = await _acces(db_session, "evt-b", [b.org])
    url = f"{API}/public/embed/evenement"
    async with client_http() as c:
        for evenement in ("affiche", "affiche", "affiche", "ouvert"):
            r = await c.post(url, json={"cle": a.site.cle, "chemin": "/", "evenement": evenement}, headers=CLIENT)
            assert r.status_code == 200, r.text
        par_jeton = await c.post(url, json={"token": a.jeton.token, "evenement": "ouvert"}, headers=CLIENT)
        assert par_jeton.status_code == 200  # l'ancien script par jeton compte aussi
        # Accès : domaine, site inconnu, jeton inconnu, évènement inconnu, rien du tout.
        assert (await c.post(url, json={"cle": a.site.cle, "evenement": "affiche"}, headers=AILLEURS)).status_code == 403
        assert (await c.post(url, json={"cle": "site_inconnu", "evenement": "affiche"}, headers=CLIENT)).status_code == 404
        assert (await c.post(url, json={"token": "inconnu", "evenement": "affiche"}, headers=CLIENT)).status_code in (403, 404)
        assert (await c.post(url, json={"cle": a.site.cle, "evenement": "clic"}, headers=CLIENT)).status_code == 422
        assert (await c.post(url, json={"evenement": "affiche"}, headers=CLIENT)).status_code == 422
        # Le portail : l'organisation A voit ses compteurs, l'organisation B n'en voit aucun de A.
        vue_a = await c.get(f"{API}/organizations/agents-site/evenements", headers=entetes(jeton_a, a.org))
        vue_b = await c.get(f"{API}/organizations/agents-site/evenements", headers=entetes(jeton_b, b.org))
        mauvaise_periode = await c.get(
            f"{API}/organizations/agents-site/evenements?du=2026-01-01&au=2020-01-01", headers=entetes(jeton_a, a.org)
        )
    assert vue_a.status_code == 200 and vue_b.status_code == 200
    lignes = vue_a.json()
    assert [(l["workflow_id"], l["affiche"], l["ouvert"]) for l in lignes] == [(a.wf.id, 3, 2)]
    assert vue_b.json() == []
    assert mauvaise_periode.status_code == 422


async def test_un_compteur_au_plafond_du_jour_ne_bouge_plus(db_session, async_session):
    w = await _widget(db_session, async_session)
    jour = datetime.now(UTC).date()
    assert await db_session.compter_evenement(w.jeton.id, jour, "affiche", 2) is True
    assert await db_session.compter_evenement(w.jeton.id, jour, "affiche", 2) is True
    assert await db_session.compter_evenement(w.jeton.id, jour, "affiche", 2) is False
    with pytest.raises(ValueError):
        await db_session.compter_evenement(w.jeton.id, jour, "adresse_ip", 2)


# --------------------------------------------------------------------------- #
# La conservation
# --------------------------------------------------------------------------- #


async def test_les_sessions_du_widget_ont_une_duree_de_conservation(db_session, async_session):
    w = await _widget(db_session, async_session)
    vieille = await db_session.create_embed_session(
        session_token="emb_session_vieille", embed_token_id=w.jeton.id, workflow_run_id=None,
        client_ip="203.0.113.9", user_agent="Navigateur", origin="https://client.fr",
        expires_at=datetime.now(UTC) - timedelta(days=CONSERVATION_SESSIONS_JOURS + 5),
    )
    recente = await db_session.create_embed_session(
        session_token="emb_session_recente", embed_token_id=w.jeton.id, workflow_run_id=None,
        client_ip="203.0.113.9", user_agent="Navigateur", origin="https://client.fr",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    from sqlalchemy import text

    async with db_session.async_session() as s:
        await s.execute(
            text("UPDATE embed_sessions SET created_at = :c WHERE id = :i"),
            {"c": datetime.now(UTC) - timedelta(days=CONSERVATION_SESSIONS_JOURS + 5), "i": vieille.id},
        )
        await s.commit()
    assert CONSERVATION_SESSIONS_JOURS == 30
    assert await purger_sessions() >= 1
    assert await db_session.get_embed_session_by_token("emb_session_vieille") is None
    assert await db_session.get_embed_session_by_token("emb_session_recente") is not None
    assert recente.id


# --------------------------------------------------------------------------- #
# La relance d'une action
# --------------------------------------------------------------------------- #


async def test_la_relance_d_une_action_ne_touche_que_son_organisation_et_son_echec(db_session, async_session, base_prete):
    w = await _widget(db_session, async_session)
    autre = await _widget(db_session, async_session)
    jeton_a = await _acces(db_session, "rel-a", [w.org])
    jeton_b = await _acces(db_session, "rel-b", [autre.org])
    with limiteur_en_memoire():
        async with client_http() as c:
            session = await _session(c, w)
    run_id = session["workflow_run_id"]
    res = await _appel_dans_la_base(base_prete, run_id)
    connexion = await schema.connecter(base_prete)
    try:
        echec = await connexion.fetchval(
            "INSERT INTO mark.action (appel_id, canal, destinataire, statut) VALUES ($1, 'mail', 'x@exemple.fr', 'echec') RETURNING id",
            res["appel_id"],
        )
        faite = await connexion.fetchval(
            "INSERT INTO mark.action (appel_id, canal, destinataire, statut) VALUES ($1, 'mail', 'y@exemple.fr', 'envoyee') RETURNING id",
            res["appel_id"],
        )
    finally:
        await connexion.close()
    url = lambda i: f"{API}/organizations/apres-appel/actions/{i}/relancer"  # noqa: E731
    relancer = AsyncMock()
    with (
        patch("api.routes.apres_appel.nom_de_la_base", AsyncMock(return_value=base_prete)),
        patch.object(chaine, "relancer", relancer),
    ):
        async with client_http() as c:
            # L'organisation B n'a pas cette base : l'action de A n'existe pas pour elle.
            with patch("api.routes.apres_appel.nom_de_la_base", AsyncMock(return_value=None)):
                autre_org = await c.post(url(echec), headers=entetes(jeton_b, autre.org))
            assert autre_org.status_code == 404
            # Même avec une base visible, le run de l'action n'est pas celui de B.
            croise = await c.post(url(echec), headers=entetes(jeton_b, autre.org))
            assert croise.status_code == 404
            assert (await c.post(url(99999), headers=entetes(jeton_a, w.org))).status_code == 404
            # En échec mais sans étape en échec à rejouer : échec définitif.
            definitif = await c.post(url(echec), headers=entetes(jeton_a, w.org))
            assert definitif.status_code == 409 and "final" in definitif.json()["detail"]
            relancer.assert_not_awaited()
            # Une étape « mail » en échec : une action déjà faite ne repart quand même jamais.
            await db_session.fusionner_apres_appel(run_id, etape="mail", valeur={"statut": "echec"})
            deja_faite = await c.post(url(faite), headers=entetes(jeton_a, w.org))
            assert deja_faite.status_code == 409 and "failed action" in deja_faite.json()["detail"]
            relancer.assert_not_awaited()
            # L'action en échec repart par la même fonction que le « Réessayer » du run.
            repart = await c.post(url(echec), headers=entetes(jeton_a, w.org))
    assert repart.status_code == 200, repart.text
    assert repart.json() == {"action_id": echec, "etape": "mail", "statut": "en_attente"}
    relancer.assert_awaited_once_with(run_id, "mail")


# --------------------------------------------------------------------------- #
# Le secours écrit (lot S4) : /init avec mode « ecrit »
# --------------------------------------------------------------------------- #


async def test_le_secours_ecrit_n_est_permis_qu_a_un_agent_de_site(db_session, async_session):
    from api.schemas.embed_chat import PublicEmbedChatSessionResponse

    w = await _widget(db_session, async_session)
    _, _, _, hors_site = await creer_agent_avec_jeton(db_session, async_session, allowed_domains=["client.fr"])

    async def _demarrer(**_kw):
        return SimpleNamespace()

    async def _autorise(**_kw):
        return SimpleNamespace(has_quota=True)

    async def _ok(*_a, **_kw):
        return True

    reponse_chat = PublicEmbedChatSessionResponse(revision=1, state="running", is_completed=False, turns=[])
    with (
        limiteur_en_memoire(),
        patch("api.routes.public_embed.start_embed_text_chat", _demarrer),
        patch("api.routes.public_embed.build_public_chat_session_response", lambda _s: reponse_chat),
        patch("api.routes.public_embed.authorize_embed_workflow_run_start", _autorise),
        patch("api.routes.public_embed.allow_embed_chat_init", _ok),
    ):
        async with client_http() as c:
            ecrit = await c.post(INIT, json={"token": w.jeton.token, "mode": "ecrit"}, headers=CLIENT)
            voix = await c.post(INIT, json={"token": w.jeton.token, "mode": "voix"}, headers=CLIENT)
            sans_mode = await c.post(INIT, json={"token": w.jeton.token}, headers=CLIENT)
            # Un jeton sans site ne change jamais de modalité, quoi que demande la requête.
            hors = await c.post(INIT, json={"token": hors_site.token, "mode": "ecrit"}, headers=CLIENT)
            inconnu = await c.post(INIT, json={"token": w.jeton.token, "mode": "telephone"}, headers=CLIENT)
    assert ecrit.status_code == 200, ecrit.text
    assert ecrit.json()["widget_type"] == "chat" and ecrit.json()["chat_session"]["revision"] == 1
    assert voix.json()["widget_type"] == "voice" and sans_mode.json()["widget_type"] == "voice"
    assert hors.json()["widget_type"] == "voice"
    assert inconnu.status_code == 422
    run = await db_session.get_workflow_run(ecrit.json()["workflow_run_id"], organization_id=w.org)
    assert run.mode == "textchat" and est_du_widget(run) and mode_de(run) == "ecrit"
    assert champs_du_site(run)["canal"] == "site"
