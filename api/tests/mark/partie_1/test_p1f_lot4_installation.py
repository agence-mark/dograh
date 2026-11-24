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
            assert args[1:3] == (cas.org, cas.user.id) and kwargs["_job_id"] == f"installer-un-restaurant-{identifiant}"
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


async def test_la_tache_installe_pour_l_organisation_donnee_et_repart_plus_tard_si_l_etape_est_tenue():
    appels = []

    async def installer(user, organization_id, formulaire, *, nom_base):
        appels.append((user.id, user.selected_organization_id, organization_id, nom_base))
        return {"echec": None}

    utilisateur = type("U", (), {"id": 7, "selected_organization_id": None})()
    with patch.object(db_client, "get_user_by_id", new=AsyncMock(return_value=utilisateur)), patch.object(TACHE, "installer_un_restaurant", installer):
        await TACHE.installer_un_restaurant_en_tache({}, 3, 7, {"nom_etablissement": "X"}, "base_x")
    assert appels == [(7, 3, 3, "base_x")]

    async def tenue(*_a, **_k):
        raise RefusInstallation(409, "en_cours")

    with patch.object(db_client, "get_user_by_id", new=AsyncMock(return_value=utilisateur)), patch.object(TACHE, "installer_un_restaurant", tenue):
        with pytest.raises(Retry):
            await TACHE.installer_un_restaurant_en_tache({}, 3, 7, {"nom_etablissement": "X"}, "base_x")


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


def test_l_empreinte_d_une_version_figee_sans_les_outils_ne_les_compte_pas_et_celle_d_apres_les_compte():
    """N° 155 : ``VERSION_FIGEE_SANS_LES_OUTILS`` : changer un outil ne change pas l'empreinte des versions déjà figées, et change celle des suivantes."""
    from api.services.gabarits import gabarit as G

    d, t, r = {"etapes": ["accueil"]}, {"accueil": "texte"}, {"modele": {}}
    ancienne = G.VERSION_FIGEE_SANS_LES_OUTILS
    assert G._empreinte(d, t, r, ancienne, "outils-a") == G._empreinte(d, t, r, ancienne, "outils-b") == G._empreinte(d, t, r, ancienne, None)
    assert G._empreinte(d, t, r, ancienne + 1, "outils-a") != G._empreinte(d, t, r, ancienne + 1, "outils-b")
    assert G._empreinte(d, t, r, ancienne + 1, None) == G._empreinte(d, t, r, ancienne + 1)
