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
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import httpx

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
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_base_portail import _equipe_a_deux_lieux


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
