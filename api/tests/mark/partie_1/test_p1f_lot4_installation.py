"""[.mark] Plan final Partie 1, lot 4 (n° 141) : l'installation d'un restaurant part en tâche de fond ; la route rend l'identifiant, une route lit l'état.

Avant : ``POST /gabarits/{nom}/agents`` jouait toute l'installation (écritures, outils, agents, tests générés) dans la requête HTTP, sans délai. Règle : la route
ouvre l'installation, met UNE tâche en file (identifiant de tâche = l'installation), répond 202 ; la tâche reprend où l'installation s'était arrêtée ; l'état se
lit par identifiant, organisation relue (404 sinon).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from arq import Retry

from api.db import db_client
from api.services.installation_client.moteur import RefusInstallation
from api.tasks import installation_gabarit as TACHE
from api.tests.mark.equipe_commun import creer_compte, creer_organisation, entetes, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.partie_1.test_l17_gabarit import FORMULAIRE_COMPLET, _client_avec_sa_base
from api.tests.mark.test_base_client import base_essai  # noqa: F401


async def test_la_route_met_une_tache_en_file_rend_202_et_l_etat_se_lit_par_identifiant(db_session, base_essai, sans_preparation_des_organisations):  # noqa: F811
    from api.tests.mark.equipe_commun import client_http

    cas = await _client_avec_sa_base(db_session, base_essai)
    with patch("api.tasks.arq.enqueue_job", new=AsyncMock()) as file:
        async with client_http() as c:
            r = await c.post("/api/v1/gabarits/restauration/agents", json={"formulaire": FORMULAIRE_COMPLET}, headers=entetes(cas.jeton, cas.org))
            assert r.status_code == 202, r.text
            identifiant = r.json()["installation_id"]
            assert r.json()["etat"] == "en_cours" and file.await_count == 1
            args, kwargs = file.await_args
            assert args[1:3] == (identifiant, cas.user.id) and kwargs["_job_id"] == f"installer-un-restaurant-{identifiant}"
            # la même demande rejouée : la même installation, le même identifiant de tâche (arq n'en lance qu'une)
            r2 = await c.post("/api/v1/gabarits/restauration/agents", json={"formulaire": FORMULAIRE_COMPLET}, headers=entetes(cas.jeton, cas.org))
            assert r2.json()["installation_id"] == identifiant and file.await_args.kwargs["_job_id"] == kwargs["_job_id"]
            etat = await c.get(f"/api/v1/gabarits/installations/{identifiant}", headers=entetes(cas.jeton, cas.org))
            assert etat.status_code == 200 and etat.json()["etat"] == "ouverte" and etat.json()["echec"] is None and etat.json()["etape_courante"] == 2
            # une autre organisation ne voit pas cette installation
            autre = await creer_organisation(db_session, f"l4-autre-{uuid.uuid4().hex[:6]}")
            _, jeton_autre = await creer_compte(db_session, f"l4-{uuid.uuid4().hex[:8]}@example.com", role="Administrateur", organisations=[autre])
            refus = await c.get(f"/api/v1/gabarits/installations/{identifiant}", headers=entetes(jeton_autre, autre))
            assert refus.status_code == 404


async def test_la_tache_installe_pour_l_organisation_de_l_installation_et_repart_plus_tard_si_l_etape_est_tenue():
    appels = []

    async def installer(user, organization_id, formulaire, *, nom_base):
        appels.append((user.id, user.selected_organization_id, organization_id, nom_base))
        return {"echec": None}

    utilisateur = type("U", (), {"id": 7, "selected_organization_id": None})()
    ouverte = AsyncMock(return_value={"organization_id": 3, "etat": "ouverte"})
    membres = AsyncMock(return_value=[utilisateur])
    with patch.object(db_client, "installation_a_reprendre", new=ouverte), patch.object(db_client, "get_organization_users", new=membres), patch.object(
        db_client, "get_user_by_id", new=AsyncMock(return_value=utilisateur)
    ), patch.object(TACHE, "installer_un_restaurant", installer):
        await TACHE.installer_un_restaurant_en_tache({}, 41, 7, {"nom_etablissement": "X"}, "base_x")
    assert appels == [(7, 3, 3, "base_x")]  # l'organisation vient de l'installation 41, relue en base

    async def tenue(*_a, **_k):
        raise RefusInstallation(409, "en_cours")

    with patch.object(db_client, "installation_a_reprendre", new=ouverte), patch.object(db_client, "get_organization_users", new=membres), patch.object(
        db_client, "get_user_by_id", new=AsyncMock(return_value=utilisateur)
    ), patch.object(TACHE, "installer_un_restaurant", tenue):
        with pytest.raises(Retry):
            await TACHE.installer_un_restaurant_en_tache({}, 41, 7, {"nom_etablissement": "X"}, "base_x")


async def test_la_tache_n_installe_rien_pour_un_utilisateur_sorti_de_l_organisation_ni_pour_une_installation_close():
    appels = []

    async def installer(*_a, **_k):
        appels.append(1)
        return {"echec": None}

    utilisateur = type("U", (), {"id": 7, "selected_organization_id": None})()
    autre = type("U", (), {"id": 8})()
    with patch.object(db_client, "get_user_by_id", new=AsyncMock(return_value=utilisateur)), patch.object(TACHE, "installer_un_restaurant", installer):
        with patch.object(db_client, "installation_a_reprendre", new=AsyncMock(return_value={"organization_id": 3, "etat": "ouverte"})), patch.object(
            db_client, "get_organization_users", new=AsyncMock(return_value=[autre])
        ):
            await TACHE.installer_un_restaurant_en_tache({}, 41, 7, {}, "base_x")  # 7 n'est plus membre de l'organisation 3
        with patch.object(db_client, "installation_a_reprendre", new=AsyncMock(return_value={"organization_id": 3, "etat": "terminee"})):
            await TACHE.installer_un_restaurant_en_tache({}, 41, 7, {}, "base_x")
        with patch.object(db_client, "installation_a_reprendre", new=AsyncMock(return_value=None)):
            await TACHE.installer_un_restaurant_en_tache({}, 41, 7, {}, "base_x")
    assert appels == []


def test_la_tache_est_declaree_au_worker_arq():
    from api.tasks.arq import WorkerSettings
    from api.tasks.function_names import FunctionNames

    noms = {getattr(f, "name", getattr(f, "__name__", "")) for f in WorkerSettings.functions}
    assert FunctionNames.INSTALLER_UN_RESTAURANT in noms


async def test_un_plafond_de_transcription_illisible_ne_bloque_pas_l_installation_mais_se_voit_au_journal():
    """N° 152 : l'erreur n'est plus avalée sans journal."""
    from loguru import logger

    from api.services.gabarits import installation as I

    journal = []
    sortie = logger.add(lambda m: journal.append(m.record), level="ERROR")
    try:
        with patch("api.services.configuration.ai_model_configuration.get_resolved_ai_model_configuration", new=AsyncMock(side_effect=RuntimeError("config illisible"))):
            assert await I._plafond_de_l_organisation(1) is None
    finally:
        logger.remove(sortie)
    assert len(journal) == 1 and "transcription ceiling" in journal[0]["message"]


async def test_le_script_monte_les_bases_anciennes_sans_toucher_celles_qui_le_sont_deja(db_session, base_essai, sans_preparation_des_organisations):  # noqa: F811
    """N° 149, 150 : ``monter_la_forme`` : une base d'avant la forme est montée et son empreinte recalculée ; rejoué, plus rien à monter."""
    from api.outils import monter_la_forme as M
    from api.services.gabarits import installation as I

    cas = await _client_avec_sa_base(db_session, base_essai)
    resultat = await I.installer_un_restaurant(cas.user, cas.org, FORMULAIRE_COMPLET, nom_base=base_essai)
    application = resultat["application"]
    etape = "commande"
    montee = application["retouches"]["base"][etape]
    ancienne = {"noeuds": {i: {k: v for k, v in n.items() if k != "reglages"} for i, n in montee["noeuds"].items()},
                "sorties": [[s["source"], s["cible"], s["condition"], s["fermee_si_action_ouverte"], s["garde_l_action_ouverte"]] for s in montee["sorties"]]}
    retouches = {**application["retouches"], "base": {**application["retouches"]["base"], etape: ancienne}}
    await db_client.ecrire_l_application(cas.org, application["workflow_id"], retouches=retouches)

    assert await M.monter_les_applications(ecrire=False, organisation=cas.org) == {"applications": 1, "montees": 1}  # compte, n'écrit rien
    assert (await db_client.application_de(cas.org, application["workflow_id"]))["retouches"]["base"][etape] == ancienne
    assert await M.monter_les_applications(ecrire=True, organisation=cas.org) == {"applications": 1, "montees": 1}
    apres = await db_client.application_de(cas.org, application["workflow_id"])
    assert apres["retouches"]["base"][etape] == montee and apres["empreinte_retouches"] == I.empreinte(apres["retouches"]["base"])
    assert await M.monter_les_applications(ecrire=True, organisation=cas.org) == {"applications": 1, "montees": 0}  # idempotent
    # la sauvegarde : l'ancienne base et son ancienne empreinte, gardées, jamais écrasées par un second passage
    sauvegarde = apres["retouches"][M.CLE_DE_LA_SAUVEGARDE]
    assert sauvegarde["base"][etape] == ancienne and sauvegarde["empreinte_retouches"] is not None
    assert (await db_client.application_de(cas.org, application["workflow_id"]))["retouches"][M.CLE_DE_LA_SAUVEGARDE] == sauvegarde


def test_l_empreinte_d_une_version_figee_sans_les_outils_ne_les_compte_pas_et_celle_d_apres_les_compte():
    """N° 155 : ``VERSION_FIGEE_SANS_LES_OUTILS`` : changer un outil ne change pas l'empreinte des versions déjà figées, et change celle des suivantes."""
    from api.services.gabarits import gabarit as G

    d, t, r = {"etapes": ["accueil"]}, {"accueil": "texte"}, {"modele": {}}
    ancienne = G.VERSION_FIGEE_SANS_LES_OUTILS
    assert G._empreinte(d, t, r, ancienne, "outils-a") == G._empreinte(d, t, r, ancienne, "outils-b") == G._empreinte(d, t, r, ancienne, None)
    assert G._empreinte(d, t, r, ancienne + 1, "outils-a") != G._empreinte(d, t, r, ancienne + 1, "outils-b")
    assert G._empreinte(d, t, r, ancienne + 1, None) == G._empreinte(d, t, r, ancienne + 1)


def test_la_tache_ne_garde_pas_son_resultat_pour_qu_un_echec_puisse_repartir_sous_le_meme_identifiant():
    """Arq garde le résultat d'une tâche une heure et refuse de remettre en file le même identifiant : sans ``keep_result=0``, une installation en échec rejouée ne
    partirait pas, et la route répondrait pourtant « en cours »."""
    from api.tasks.arq import WorkerSettings

    declaree = next(f for f in WorkerSettings.functions if getattr(f, "name", None) == "installer_un_restaurant_en_tache")
    assert declaree.keep_result_s == 0


async def test_la_route_dit_quand_arq_tient_deja_la_tache(db_session, base_essai, sans_preparation_des_organisations):  # noqa: F811
    from api.tests.mark.equipe_commun import client_http

    cas = await _client_avec_sa_base(db_session, base_essai)
    with patch("api.tasks.arq.enqueue_job", new=AsyncMock(return_value=None)):  # arq : un travail de cet identifiant existe déjà
        async with client_http() as c:
            r = await c.post("/api/v1/gabarits/restauration/agents", json={"formulaire": FORMULAIRE_COMPLET}, headers=entetes(cas.jeton, cas.org))
    assert r.status_code == 202 and r.json()["deja_en_file"] is True


async def test_une_base_d_ancienne_forme_donne_un_409_sans_texte_interne_sur_toute_route():
    """Entre le déploiement et le script de montée, la lecture d'un agent ou la diffusion qui trouve une forme ancienne répond UN code, jamais une 500."""
    from api.app import app
    from api.services.gabarits.forme import FormeAMonter, exiger_la_forme_actuelle
    from api.tests.mark.equipe_commun import client_http

    @app.get("/api/v1/_essai_forme_a_monter")
    async def _lever():
        exiger_la_forme_actuelle({"noeuds": {}})  # sans numéro de forme

    try:
        async with client_http() as c:
            r = await c.get("/api/v1/_essai_forme_a_monter")
    finally:
        app.router.routes[:] = [x for x in app.router.routes if getattr(x, "path", "") != "/api/v1/_essai_forme_a_monter"]
    assert r.status_code == 409 and r.json() == {"detail": {"code": "forme_a_monter"}}
    assert FormeAMonter  # le texte interne (le nom du script) ne sort pas
    assert "monter_la_forme" not in r.text


async def _application_d_ancienne_forme(db_session, base_essai, sans_preparation):  # noqa: F811
    from api.services.gabarits import installation as I

    cas = await _client_avec_sa_base(db_session, base_essai)
    resultat = await I.installer_un_restaurant(cas.user, cas.org, FORMULAIRE_COMPLET, nom_base=base_essai)
    application = resultat["application"]
    etape = "commande"
    montee = application["retouches"]["base"][etape]
    ancienne = {"noeuds": {i: {k: v for k, v in n.items() if k != "reglages"} for i, n in montee["noeuds"].items()},
                "sorties": [[s["source"], s["cible"], s["condition"], s["fermee_si_action_ouverte"], s["garde_l_action_ouverte"]] for s in montee["sorties"]]}
    return cas, application, etape, ancienne


async def test_la_sauvegarde_garde_la_base_et_l_empreinte_d_avant_meme_avec_une_diffusion_en_attente(db_session, base_essai, sans_preparation_des_organisations):  # noqa: F811
    """Second audit du lot 4 : une diffusion en attente ne doit pas prendre la place de la sauvegarde (la boucle sur ``en_attente`` écrasait l'état d'avant)."""
    from api.outils import monter_la_forme as M

    cas, application, etape, ancienne = await _application_d_ancienne_forme(db_session, base_essai, sans_preparation_des_organisations)
    attente = {"version": 9, "trous": {}, "refus": False, "etapes": {etape: {"branche_id": 1, "forme": {"noeuds": {}, "sorties": []}}}}
    retouches = {**application["retouches"], "base": {**application["retouches"]["base"], etape: ancienne}, "en_attente": attente}
    await db_client.ecrire_l_application(cas.org, application["workflow_id"], retouches=retouches)
    avant = await db_client.application_de(cas.org, application["workflow_id"])

    assert await M.monter_les_applications(ecrire=True, organisation=cas.org) == {"applications": 1, "montees": 2}  # la base ET la diffusion en attente
    apres = await db_client.application_de(cas.org, application["workflow_id"])
    sauvegarde = apres["retouches"][M.CLE_DE_LA_SAUVEGARDE]
    assert sauvegarde["base"][etape] == ancienne
    assert sauvegarde["empreinte_retouches"] == avant["empreinte_retouches"]
    assert sauvegarde["en_attente"] == attente  # la diffusion en attente d'avant, telle qu'elle était


async def test_une_diffusion_refuse_l_application_d_ancienne_forme_sans_arreter_les_autres(db_session, base_essai, sans_preparation_des_organisations):  # noqa: F811
    """Une base d'ancienne forme refuse CETTE application (comme un trou manquant) ; la diffusion « toutes » ne s'arrête pas à moitié."""
    from api.services.gabarits import diffusion as D
    from api.services.gabarits import gabarit as G

    cas, application, etape, ancienne = await _application_d_ancienne_forme(db_session, base_essai, sans_preparation_des_organisations)
    retouches = {**application["retouches"], "base": {**application["retouches"]["base"], etape: ancienne}}
    await db_client.ecrire_l_application(cas.org, application["workflow_id"], retouches=retouches)
    a = await db_client.application_de(cas.org, application["workflow_id"])
    resultat = await D._diffuser_une_application(cas.user, G.charger(), a)
    assert resultat == {"application": {"etat": "refusee", "raison": "forme_a_monter"}}
