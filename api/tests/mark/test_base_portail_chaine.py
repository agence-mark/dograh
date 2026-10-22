"""[.mark] Chantier agents-specialises, lots 8 et 9 : ce que la VRAIE route de l'après-appel écrit à côté de
l'appel (motifs multiples, agents de l'appel, horaires, incidents, issue de chaque transfert) et ce que
``agent_site`` apprend de l'agent.

Suite de ``test_base_portail.py`` (la base, la sécurité par ligne, les vues). Ici : le chemin d'un appel
fini jusqu'à la base du client, sur SMTP réel (boucle locale) et vraie base de test ; seuls les modèles
sont remplacés.

| Test | Ce qu'il prouve |
|---|---|
| appel complet | motifs, agents (noms lus dans Dograh), hors horaires, incident de repli, trois transferts : tout est écrit, rien deux fois |
| écriture reprise | une écriture qui aboutit après un échec est un incident ; sans échec, aucun |
| étape en échec définitif | l'échec définitif d'une étape d'après-appel est un incident lié à l'appel |
| agent_site | suit la fiche choisie par l'agent, une seule par agent, à la reprise comme à la synchronisation |
| travail de fond et parcours (018) | par la vraie route : travaux (outils, statut, durée), agent de chaque tour, parcours rendu, ni la demande ni le résultat écrits nulle part ; un agent seul garde l'envoi d'avant ; le portail ne lit que ses lieux ; 17 → 18 puis 018 rejouée |
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import asyncpg
import httpx
import pytest

from api.db.bases_clients import apres_appel as sql
from api.db.bases_clients import connexion as schema
from api.db.bases_clients import traces
from api.services.apres_appel import chaine
from api.tests.mark.test_apres_appel import (  # noqa: F401  (fixtures)
    _envoi,
    _executer_tout_de_suite,
    _organisation,
    _regler,
    base_v4,
    modele,
    smtp,
)
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_base_portail import (  # noqa: F401  (fixtures)
    _equipe_a_deux_lieux,
    base_portail,
    portail,
)


async def _run_perso(db_session, org, *, gathered, initial=None, evenements_en_plus=()):
    from api.tests.mark import test_apres_appel as t

    run = await db_session.create_workflow_run(
        name="essai",
        workflow_id=org.agent.id,
        mode="twilio",
        user_id=org.utilisateur.id,
        call_type=t.CallType.INBOUND,
        organization_id=org.organisation.id,
        definition_id=org.definition.id,
        initial_context={
            "caller_number": "+33612345678",
            "runtime_configuration": {
                "llm_provider": "mistral",
                "etablissement": {"id": "site-a"},
            },
            **(initial or {}),
        },
        gathered_context=gathered,
        logs={"realtime_feedback_events": [*t._evenements(), *evenements_en_plus]},
    )
    await db_session.update_workflow_run(
        run.id, usage_info={"call_duration_seconds": 61.0}
    )
    return run


async def test_un_appel_complet_range_motifs_agents_horaires_incidents_et_transferts(
    base_v4, smtp, modele, db_session, async_session
):
    from api.tasks.workflow_completion import process_workflow_completion

    org = await _organisation(async_session, db_session)
    # Le second agent de l'appel : un agent de CETTE organisation (son nom est lu dans Dograh).
    second = await db_session.create_workflow(
        name="Agent spécialisé",
        workflow_definition={"nodes": [], "edges": []},
        user_id=org.utilisateur.id,
        organization_id=org.organisation.id,
    )
    await _regler(db_session, org, base_v4, smtp)
    await _equipe_a_deux_lieux(base_v4)
    instant = datetime(2026, 10, 7, 9, 0, 5, tzinfo=UTC).isoformat()
    run = await _run_perso(
        db_session,
        org,
        gathered={
            "extracted_variables": {"nom": "Dupont", "motif": ["entretien", "devis"]},
            "call_disposition": "rappel_demande",
            "agent_transfers": [
                {
                    "destination_workflow_id": second.id,
                    "to_visit_id": "v2",
                    "outcome": "completed",
                },
                {
                    "destination_workflow_id": org.agent.id,
                    "to_visit_id": "v3",
                    "outcome": "completed",
                },
            ],
            "transferts_humains": [
                {"le": instant, "cible": "duo", "issue": "repondeur"},
                {
                    "le": "2026-10-07T09:00:30+00:00",
                    "cible": "numero:***6789",
                    "issue": "decroche",
                },
            ],
            "transferts": [
                {
                    "le": "2026-10-07T09:00:40+00:00",
                    "cible": "numero:***0000",
                    "issue": "sans_reponse",
                }
            ],
        },
        initial={"etat_ouverture": "FERME"},
        evenements_en_plus=[
            {
                "type": "mark-panne",
                "turn": 1,
                "timestamp": instant,
                "payload": {"brique": "voix", "raison": "delai", "decision": "repli"},
            }
        ],
    )
    with patch("api.tasks.arq.enqueue_job", await _executer_tout_de_suite([])):
        await process_workflow_completion(None, run.id)
    bloc = await db_session.lire_apres_appel(run.id)
    assert bloc["etapes"]["ecriture"]["statut"] == "ok", bloc

    connexion = await schema.connecter(base_v4)
    try:
        appel = await connexion.fetchrow(
            "SELECT id, motif, hors_horaires, demande_id FROM mark.appel WHERE dograh_run_id = $1",
            run.id,
        )
        assert appel["motif"] == "entretien" and appel["hors_horaires"] is True
        assert [
            r["motif"]
            for r in await connexion.fetch(
                "SELECT motif FROM mark.appel_motif WHERE appel_id = $1 ORDER BY ordre",
                appel["id"],
            )
        ] == ["entretien", "devis"]
        agents = await connexion.fetch(
            "SELECT aa.ordre, a.dograh_workflow_id AS wid, a.nom FROM mark.appel_agent aa "
            "JOIN mark.agent a ON a.id = aa.agent_id WHERE aa.appel_id = $1 ORDER BY aa.ordre",
            appel["id"],
        )
        assert [(r["ordre"], r["wid"]) for r in agents] == [
            (1, org.agent.id),
            (2, second.id),
            (3, org.agent.id),
        ]
        assert agents[1]["nom"] == "Agent spécialisé"
        # D82 : un transfert vers un humain, un numéro, un renvoi : une ligne d'action chacun.
        actions = await connexion.fetch(
            "SELECT destinataire, statut, erreur FROM mark.action "
            "WHERE appel_id = $1 AND canal = 'transfert' ORDER BY envoyee_le",
            appel["id"],
        )
        assert [tuple(r) for r in actions] == [
            ("duo", "echec", "repondeur"),
            ("numero:***6789", "delivree", None),
            ("numero:***0000", "echec", "sans_reponse"),
        ]
        # Le repli de la voix est un incident, lié à l'appel.
        incidents = await connexion.fetch(
            "SELECT i.brique, i.cause FROM mark.incident i JOIN mark.incident_appel ia ON ia.incident_id = i.id "
            "WHERE ia.appel_id = $1",
            appel["id"],
        )
        assert [tuple(r) for r in incidents] == [
            ("voix", "outage_fallback : delai → repli")
        ]
        # Rejoué (le filet, une tâche reprise) : rien d'écrit deux fois.
        assert (
            await traces.ecrire_issues_de_transfert(
                connexion,
                appel["id"],
                appel["demande_id"],
                [{"le": instant, "cible": "duo", "issue": "repondeur"}],
            )
            == 0
        )
    finally:
        await connexion.close()


async def test_une_ecriture_reprise_apres_un_echec_est_un_incident(
    base_v4, smtp, modele, db_session, async_session
):
    """La base du client était injoignable, puis revenue : l'écriture qui aboutit le dit."""
    connexion = await schema.connecter(base_v4)
    try:
        await sql.recevoir_appel(connexion, _envoi(41))
        appel = await connexion.fetchval(
            "SELECT id FROM mark.appel WHERE dograh_run_id = 41"
        )
        ctx = SimpleNamespace(envoi={})
        panne = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        await chaine._traces_de_l_appel(
            ctx,
            connexion,
            {"appel_id": appel, "demande_id": None},
            {"etapes": {"ecriture": {"statut": "echec", "le": panne}}},
        )
        lignes = await connexion.fetch(
            "SELECT i.brique, i.cause FROM mark.incident i JOIN mark.incident_appel ia ON ia.incident_id = i.id "
            "WHERE ia.appel_id = $1",
            appel,
        )
        assert [tuple(r) for r in lignes] == [
            ("base_client", "ecriture_de_l_appel_en_echec_puis_reprise")
        ]
        # Sans échec avant : aucun incident de plus.
        await chaine._traces_de_l_appel(
            ctx,
            connexion,
            {"appel_id": appel},
            {"etapes": {"ecriture": {"statut": "en_cours"}}},
        )
        assert await connexion.fetchval("SELECT count(*) FROM mark.incident") == 1
    finally:
        await connexion.close()


async def test_une_etape_d_apres_appel_en_echec_definitif_est_un_incident(
    base_v4, smtp, modele, db_session, async_session
):
    org = await _organisation(async_session, db_session, modules=["webhook"])
    await _regler(
        db_session, org, base_v4, smtp, webhook_url="https://webhook.example.org/fin"
    )
    await _equipe_a_deux_lieux(base_v4)
    run = await _run_perso(
        db_session,
        org,
        gathered={
            "extracted_variables": {"nom": "Dupont", "motif": "entretien"},
            "call_disposition": "rappel_demande",
        },
    )
    enqueue = await _executer_tout_de_suite([])
    with patch(
        "api.services.apres_appel.modules.nouveau_client",
        lambda **options: httpx.AsyncClient(
            transport=httpx.MockTransport(lambda requete: httpx.Response(500)),
            **options,
        ),
    ):
        await chaine.demarrer(run.id, enqueue=enqueue)
        await chaine.executer(run.id, ["module:webhook"], 2, enqueue=enqueue)
        await chaine.executer(run.id, ["module:webhook"], 3, enqueue=enqueue)
    connexion = await schema.connecter(base_v4)
    try:
        lignes = await connexion.fetch(
            "SELECT i.brique, ia.appel_id IS NOT NULL AS lie FROM mark.incident i "
            "LEFT JOIN mark.incident_appel ia ON ia.incident_id = i.id WHERE i.brique LIKE 'apres_appel:%'"
        )
        assert [tuple(r) for r in lignes] == [("apres_appel:module:webhook", True)]
    finally:
        await connexion.close()


# --------------------------------------------------------------------------- #
# agent_site suit le choix de fiche de l'agent (M3)
# --------------------------------------------------------------------------- #


async def test_agent_site_suit_la_fiche_choisie_a_la_reprise_et_a_la_synchronisation(
    base_v4, smtp, db_session, async_session
):
    from api.enums import OrganizationConfigurationKey
    from api.services.base_client.agents import synchroniser_agent_site
    from api.services.etablissements.reprise import ecrire_rattachements

    org = await _organisation(async_session, db_session)
    o = org.organisation.id
    await _equipe_a_deux_lieux(base_v4)
    # Sans base rattachée : rien n'est écrit, rien ne lève.
    assert await synchroniser_agent_site(o, org.agent.id, "Agent", "site-a") is False
    await db_session.upsert_configuration(
        o, OrganizationConfigurationKey.BASE_CLIENT.value, {"nom_base": base_v4}
    )

    async def lieux():
        c = await schema.connecter(base_v4)
        try:
            return [
                r["cle"]
                for r in await c.fetch(
                    "SELECT s.cle FROM mark.agent_site x JOIN mark.agent a ON a.id = x.agent_id "
                    "JOIN mark.site s ON s.id = x.site_id WHERE a.dograh_workflow_id = $1",
                    org.agent.id,
                )
            ]
        finally:
            await c.close()

    assert (
        await synchroniser_agent_site(o, org.agent.id, "Agent d'essai", "site-a")
        is True
    )
    assert await lieux() == ["site-a"]
    # Un seul établissement par agent : le choix change, la ligne suit.
    assert (
        await synchroniser_agent_site(o, org.agent.id, "Agent d'essai", "site-b")
        is True
    )
    assert await lieux() == ["site-b"]
    # Une fiche que la base ne connaît pas : rien de lié, dit (False) ; l'ancien lien est retiré.
    assert (
        await synchroniser_agent_site(o, org.agent.id, None, "fiche-inconnue") is False
    )
    assert await lieux() == []
    # La reprise des fiches écrit le choix de l'agent ET le range dans la base du client.
    await ecrire_rattachements(o, {org.agent.id: "site-a"})
    assert await lieux() == ["site-a"]


# --------------------------------------------------------------------------- #
# Lot F2 (migration 018) : le travail du cerveau de fond et le parcours de l'appel
# --------------------------------------------------------------------------- #

TEXTE_DE_LA_DEMANDE = "DEMANDE-CONFIEE-AU-FOND-9f3a"
TEXTE_DU_RESULTAT = "RESULTAT-DU-FOND-7c1d"


def _evenements_par_etape(etapes):
    """Les événements d'un appel court, chaque tour portant le nom de son étape (``node_name``)."""
    from api.tests.mark import test_apres_appel as t

    return [{**e, "node_name": etapes[e["turn"]]} for e in t._evenements()]


async def test_le_travail_de_fond_et_le_parcours_sont_ecrits_sans_aucun_texte(
    base_v4, smtp, modele, db_session, async_session
):
    """Par la VRAIE route de l'après-appel : une ligne de travail par travail (outils, statut,
    durée), l'agent de chaque tour, le parcours rendu ; ni la demande confiée au fond ni son résultat
    ne sont écrits nulle part dans la base du client."""
    from api.tasks.workflow_completion import process_workflow_completion

    org = await _organisation(async_session, db_session)
    second = await db_session.create_workflow(
        name="Agent spécialisé",
        workflow_definition={"nodes": [], "edges": []},
        user_id=org.utilisateur.id,
        organization_id=org.organisation.id,
    )
    await _regler(db_session, org, base_v4, smtp)
    run = await _run_perso(
        db_session,
        org,
        gathered={
            "extracted_variables": {"nom": "Dupont", "motif": "entretien"},
            "agent_transfers": [
                {
                    "destination_workflow_id": second.id,
                    "to_visit_id": "v2",
                    "outcome": "completed",
                }
            ],
            "parcours_etapes": [
                {"agent": "Agent d'essai", "agent_id": org.agent.id, "etape": "accueil"},
                {"agent": "Agent spécialisé", "agent_id": second.id, "etape": "suite"},
            ],
            "travaux": [
                {
                    "agent": "Agent d'essai",
                    "demande": TEXTE_DE_LA_DEMANDE,
                    "statut": "termine",
                    "outils": ["outil_a", "outil_b"],
                    "duree_ms": 1840,
                    "jetons_entree": 120,
                    "jetons_sortie": 30,
                    "resultat": TEXTE_DU_RESULTAT,
                },
                {
                    "demande": "autre demande confiée",
                    "statut": "echec",
                    "outils": [],
                    "duree_ms": 95,
                },
            ],
        },
    )
    # Les événements de l'appel portent le nom de l'étape de chaque tour.
    await db_session.update_workflow_run(
        run.id,
        logs={"realtime_feedback_events": _evenements_par_etape({1: "accueil", 2: "suite"})},
    )
    with patch("api.tasks.arq.enqueue_job", await _executer_tout_de_suite([])):
        await process_workflow_completion(None, run.id)
    bloc = await db_session.lire_apres_appel(run.id)
    assert bloc["etapes"]["ecriture"]["statut"] == "ok", bloc

    connexion = await schema.connecter(base_v4)
    try:
        appel = await connexion.fetchrow(
            "SELECT id, parcours FROM mark.appel WHERE dograh_run_id = $1", run.id
        )
        assert appel["parcours"] == "Agent d'essai › accueil › Agent spécialisé › suite"
        travaux = await connexion.fetch(
            "SELECT ordre, statut, duree_ms, outils FROM mark.travail_fond "
            "WHERE appel_id = $1 ORDER BY ordre",
            appel["id"],
        )
        assert [(r["ordre"], r["statut"], r["duree_ms"], list(r["outils"])) for r in travaux] == [
            (1, "termine", 1840, ["outil_a", "outil_b"]),
            (2, "echec", 95, []),
        ]
        tours = await connexion.fetch(
            "SELECT t.numero, a.dograh_workflow_id AS wid FROM mark.tour t "
            "LEFT JOIN mark.agent a ON a.id = t.agent_id WHERE t.appel_id = $1 ORDER BY t.numero",
            appel["id"],
        )
        assert [(r["numero"], r["wid"]) for r in tours] == [
            (1, org.agent.id),
            (2, second.id),
        ]
    finally:
        await connexion.close()
    # Ni le texte de la demande ni celui du résultat : dans aucune ligne d'aucune table (lues par
    # le propriétaire, qui peut tout lire).
    connexion = await schema.connecter_proprietaire(base_v4)
    try:
        for table in await connexion.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'mark'"
        ):
            lignes = await connexion.fetch(
                f"SELECT row_to_json(t)::text AS ligne FROM mark.{table['tablename']} t"
            )
            for ligne in lignes:
                assert TEXTE_DE_LA_DEMANDE not in ligne["ligne"], table["tablename"]
                assert TEXTE_DU_RESULTAT not in ligne["ligne"], table["tablename"]
                assert "autre demande confiée" not in ligne["ligne"], table["tablename"]
    finally:
        await connexion.close()


def test_l_envoi_d_un_agent_seul_garde_la_forme_d_avant_et_ne_porte_aucun_texte_du_fond():
    from api.services.apres_appel.envoi import (
        agent_de_chaque_tour,
        parcours_de,
        travaux_de,
    )

    # Sans parcours (un agent seul) : rien n'est posé sur les tours.
    tours = [{"numero": 1, "etape": "accueil"}]
    agent_de_chaque_tour(tours, parcours_de({}))
    assert tours == [{"numero": 1, "etape": "accueil"}]
    # Les travaux : ni demande ni résultat dans ce qui part ; un travail sans demande est ignoré.
    sortie = travaux_de(
        {
            "travaux": [
                {"demande": "x", "resultat": "y", "statut": "termine", "outils": ["o"], "duree_ms": 5},
                {"statut": "termine"},
            ]
        }
    )
    assert sortie == [{"statut": "termine", "outils": ["o"], "duree_ms": 5}]
    # Le parcours se lit dans l'ordre : le tour d'une étape déjà atteinte garde l'agent courant,
    # un tour d'une étape plus loin avance dans le parcours (jamais en arrière).
    entrees = [
        {"agent_id": 1, "etape": "accueil"},
        {"agent_id": 2, "etape": "suite"},
        {"agent_id": 1, "etape": "fin"},
    ]
    tours = [
        {"numero": 1, "etape": "accueil"},
        {"numero": 2, "etape": "suite"},
        {"numero": 3, "etape": "suite"},
        {"numero": 4, "etape": "fin"},
        {"numero": 5, "etape": "accueil"},
    ]
    agent_de_chaque_tour(tours, entrees)
    assert [t["agent_id"] for t in tours] == [1, 2, 2, 1, 1]


async def test_un_appel_sans_travail_ni_parcours_s_ecrit_comme_avant(base_v4):
    connexion = await schema.connecter(base_v4)
    try:
        resultat = await sql.recevoir_appel(connexion, _envoi(501))
        assert resultat["doublon"] is False
        assert (
            await connexion.fetchval(
                "SELECT count(*) FROM mark.travail_fond WHERE appel_id = $1",
                resultat["appel_id"],
            )
            == 0
        )
        assert (
            await connexion.fetchval(
                "SELECT parcours FROM mark.appel WHERE id = $1", resultat["appel_id"]
            )
            is None
        )
        assert (
            await connexion.fetchval(
                "SELECT agent_id FROM mark.tour WHERE appel_id = $1", resultat["appel_id"]
            )
            is None
        )
        # Rejoué : rien d'écrit deux fois.
        assert (await sql.recevoir_appel(connexion, _envoi(501)))["doublon"] is True
    finally:
        await connexion.close()


async def test_le_portail_ne_lit_que_le_travail_de_fond_de_ses_lieux(portail):
    from api.tests.mark.test_base_portail import _compter, _connexion_du_portail

    ids = portail.ids
    connexion = await schema.connecter(portail.base)
    try:
        await connexion.execute(
            "INSERT INTO mark.travail_fond (appel_id, ordre, statut, duree_ms, outils) VALUES "
            "($1, 1, 'termine', 10, '{a}'), ($2, 1, 'termine', 20, '{b}')",
            ids["appel"][901],
            ids["appel"][903],
        )
    finally:
        await connexion.close()
    a = str(ids["site"]["site-a"])
    c = await _connexion_du_portail(portail.base, a)
    try:
        assert [
            r["duree_ms"] for r in await c.fetch("SELECT duree_ms FROM mark.travail_fond")
        ] == [10]
        # Lecture seule : le portail n'écrit pas dans le travail de fond.
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await c.execute("DELETE FROM mark.travail_fond")
    finally:
        await c.close()
    for variable in (None, "", "garbage"):
        c = await _connexion_du_portail(portail.base, variable)
        try:
            assert await _compter(c, "travail_fond") == 0, variable
        finally:
            await c.close()
    c = await _connexion_du_portail(portail.base, "*")
    try:
        assert await _compter(c, "travail_fond") == 2
    finally:
        await c.close()


async def test_une_base_en_version_17_monte_en_18_et_la_018_se_rejoue(base_essai):
    from api.tests.mark.test_base_portail import (
        _appel,
        _appliquer_jusqua,
        _base_en_version_14,
    )

    await _base_en_version_14(base_essai)
    proprietaire = await schema.connecter_proprietaire(base_essai)
    try:
        assert await _appliquer_jusqua(proprietaire, 17) == [15, 16, 17]
        # Un appel écrit par la fonction de la 016 (avant la 018) : ses tours n'ont pas d'agent.
        ancien = await sql.recevoir_appel(proprietaire, _appel(1, None, "+33600000001"))
        assert await schema.version_de(proprietaire) == 17
        assert await schema.appliquer_migrations(proprietaire) == [18]
        assert await schema.version_de(proprietaire) == 18 == schema.version_attendue()
        # Rejouée (sans sa ligne de version) : rien ne casse, rien ne se duplique.
        migration = next(m for m in schema.migrations() if m.version == 18)
        corps = migration.sql[: migration.sql.index("INSERT INTO schema_version")]
        async with proprietaire.transaction():
            await proprietaire.execute(corps)
        assert await schema.appliquer_migrations(proprietaire) == []
        # L'appel d'avant est intact ; un appel d'après écrit son travail.
        assert (
            await proprietaire.fetchval(
                "SELECT count(*) FROM mark.tour WHERE appel_id = $1", ancien["appel_id"]
            )
            == 1
        )
        neuf = await sql.recevoir_appel(
            proprietaire,
            _appel(
                2,
                None,
                "+33600000002",
                travaux=[{"statut": "termine", "outils": ["o"], "duree_ms": 7}],
                parcours="Agent › accueil",
            ),
        )
        assert (
            await proprietaire.fetchval(
                "SELECT count(*) FROM mark.travail_fond WHERE appel_id = $1",
                neuf["appel_id"],
            )
            == 1
        )
    finally:
        await proprietaire.close()
