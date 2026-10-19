"""[.mark] Santé des connexions et qualité de la liaison audio (fiabilite-orchestration, lot 9, F11).

Au banc du 19/10, la voix saccadée du 1463 était le wifi du poste, et rien dans le run ne le disait.
Le run garde maintenant : les connexions au modèle (ouvertes ou reprises, par agent), le temps de la
première connexion de la transcription et de la voix, et pendant un appel navigateur la liaison
audio (paquets, gigue, aller-retour).

| Test | Ce qu'il prouve |
|---|---|
| lecture des statistiques | vraies classes d'aiortc : voix reçue (perdus, gigue en ms) et compte rendu du navigateur (aller-retour) ; la vidéo est ignorée |
| bilan | dernier relevé et pires valeurs |
| surveillance (R1) | la tâche relève plusieurs fois, et à l'annulation écrit le bilan dans ``mark_reseau`` par le vrai chemin d'écriture du run |
| sans statistiques | une connexion qui n'en donne pas : pas de tâche, aucun bruit |
| panne du relevé | un relevé qui échoue n'arrête pas la surveillance ni l'appel |
| postes | connexion ouverte puis reprise, notée avec l'hôte, jamais la clé |
| fabrique d'agents (R1) | par la vraie fabrique : le collègue au même fournisseur note « reprise » dans la fiche de l'appel |
| coupures | chaque événement de connexion dit après combien de temps il est arrivé |
| analyse | le bloc ``network`` lit tout cela ; sans rien : « non capté » |
"""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiortc.stats import (
    RTCInboundRtpStreamStats,
    RTCRemoteInboundRtpStreamStats,
    RTCStatsReport,
)

from api.services.analyse_run.analyse import analyser_run
from api.services.analyse_run.incidents_appel import (
    TYPE_CONNEXION,
    brancher_les_connexions,
)
from api.services.analyse_run.reseau import (
    CLE_RESEAU,
    BilanDeLaLiaison,
    lancer_la_surveillance,
    lire_les_stats,
    surveiller_la_liaison,
)
from api.services.groupe.postes import Postes
from api.tests.mark.test_agent_transfere_reglages_mark import _fabrique
from api.tests.mark.test_trace_modele import _service
from api.tests.mark.test_trace_sur_chaque_agent import _construire_collegue

MAINTENANT = datetime(2026, 10, 19, tzinfo=timezone.utc)


def _rapport(perdus_entree=2, jitter_entree=480, perdus_sortie=5, jitter_sortie=960, rtt=0.08):
    rapport = RTCStatsReport()
    rapport["in"] = RTCInboundRtpStreamStats(
        timestamp=MAINTENANT,
        type="inbound-rtp",
        id="in",
        ssrc=1,
        kind="audio",
        transportId="t",
        packetsReceived=1000,
        packetsLost=perdus_entree,
        jitter=jitter_entree,
    )
    rapport["out"] = RTCRemoteInboundRtpStreamStats(
        timestamp=MAINTENANT,
        type="remote-inbound-rtp",
        id="out",
        ssrc=2,
        kind="audio",
        transportId="t",
        packetsReceived=900,
        packetsLost=perdus_sortie,
        jitter=jitter_sortie,
        roundTripTime=rtt,
        fractionLost=0.01,
    )
    rapport["video"] = RTCInboundRtpStreamStats(
        timestamp=MAINTENANT,
        type="inbound-rtp",
        id="video",
        ssrc=3,
        kind="video",
        transportId="t",
        packetsReceived=1,
        packetsLost=999,
        jitter=9999,
    )
    return rapport


def test_les_statistiques_d_aiortc_sont_lues_en_millisecondes_et_la_video_ignoree():
    releve = lire_les_stats(_rapport())
    assert releve["inbound"] == {"packets_received": 1000, "packets_lost": 2, "jitter_ms": 10.0}
    assert releve["outbound"] == {"packets_lost": 5, "jitter_ms": 20.0, "round_trip_ms": 80.0}
    assert lire_les_stats(RTCStatsReport()) == {"inbound": None, "outbound": None}


def test_le_bilan_garde_le_dernier_releve_et_les_pires_valeurs():
    bilan = BilanDeLaLiaison()
    assert bilan.en_dict()["status"] == "unavailable"
    bilan.ajouter(lire_les_stats(_rapport(jitter_entree=1920, rtt=0.30)))
    bilan.ajouter(lire_les_stats(_rapport(jitter_entree=480, rtt=0.08)))
    donnees = bilan.en_dict()
    assert donnees["status"] == "ok" and donnees["samples"] == 2
    assert donnees["last"]["inbound"]["jitter_ms"] == 10.0
    assert donnees["worst"] == {"jitter_ms_in": 40.0, "jitter_ms_out": 20.0, "round_trip_ms": 300.0}


@pytest.mark.asyncio
async def test_la_surveillance_ecrit_le_bilan_au_run_par_le_vrai_chemin():
    db = SimpleNamespace(update_workflow_run=AsyncMock())
    appels = []

    async def stats():
        appels.append(1)
        return _rapport()

    connexion = SimpleNamespace(pc=SimpleNamespace(getStats=stats))
    tache = lancer_la_surveillance(connexion, 1468, db, periode_s=0.01)
    assert tache is not None
    await asyncio.sleep(0.1)
    tache.cancel()
    await asyncio.gather(tache, return_exceptions=True)

    assert len(appels) >= 2
    db.update_workflow_run.assert_awaited_once()
    envoi = db.update_workflow_run.await_args.kwargs
    assert envoi["run_id"] == 1468
    bilan = envoi["gathered_context"][CLE_RESEAU]
    assert bilan["status"] == "ok" and bilan["samples"] >= 2
    assert bilan["last"]["outbound"]["round_trip_ms"] == 80.0


def test_une_connexion_sans_statistiques_n_a_pas_de_surveillance():
    assert lancer_la_surveillance(SimpleNamespace(), 1, SimpleNamespace()) is None
    assert lancer_la_surveillance(SimpleNamespace(pc=SimpleNamespace()), 1, SimpleNamespace()) is None


@pytest.mark.asyncio
async def test_un_releve_qui_echoue_n_arrete_ni_la_surveillance_ni_l_appel():
    ecrit = []
    essais = []

    async def stats():
        essais.append(1)
        if len(essais) == 1:
            raise RuntimeError("pas encore de pair")
        return _rapport()

    async def ecrire(bilan):
        ecrit.append(bilan)

    tache = asyncio.create_task(surveiller_la_liaison(stats, ecrire, periode_s=0.01))
    await asyncio.sleep(0.08)
    tache.cancel()
    await asyncio.gather(tache, return_exceptions=True)
    assert len(essais) >= 2 and ecrit[0]["status"] == "ok"


def test_les_postes_notent_ouvert_puis_repris_avec_l_hote_jamais_la_cle():
    notes: list[dict] = []
    postes = Postes(noter=notes.append)
    premier, _ = _service()
    second, _ = _service()
    # Deux services visant la même adresse avec la même clé : le second reprend la connexion.
    postes.enregistrer(premier, "Accueil")
    assert postes.partager(second, "Collègue") is True
    assert [(n["event"], n["agent"]) for n in notes] == [("opened", "Accueil"), ("reused", "Collègue")]
    assert all(set(n) == {"event", "agent", "host", "after_secs"} for n in notes)
    assert "cle-de-test" not in str(notes)


@pytest.mark.asyncio
async def test_la_fabrique_d_agents_note_la_reprise_dans_la_fiche_de_l_appel():
    fiche: dict = {}
    moteur = SimpleNamespace(_gathered_context=fiche)
    accueil, _ = _service()
    collegue, _ = _service()
    fabrique = _fabrique()
    fabrique._moteur_de_l_appel = lambda: moteur
    fabrique.postes.enregistrer(accueil, "Accueil")
    await _construire_collegue(fabrique, [collegue], {})
    assert [(n["event"], n["agent"]) for n in fiche["mark_connexions_modele"]] == [
        ("opened", "Accueil"),
        ("reused", "Collègue"),
    ]


@pytest.mark.asyncio
async def test_chaque_evenement_de_connexion_dit_apres_combien_de_temps():
    class Service:
        def __init__(self):
            self._event_handlers = {
                "on_connected": [],
                "on_disconnected": [],
                "on_connection_error": [],
            }
            self.gestionnaires = {}

        def add_event_handler(self, nom, f):
            self.gestionnaires[nom] = f

    class Journal:
        def __init__(self):
            self.evenements = []

        async def append(self, e):
            self.evenements.append(e)

    service, journal = Service(), Journal()
    assert brancher_les_connexions({"voice": service}, journal) == ["voice"]
    await service.gestionnaires["on_connected"](service)
    await asyncio.sleep(0.02)
    await service.gestionnaires["on_connection_error"](service, "coupé")
    connecte, erreur = journal.evenements
    assert connecte["type"] == TYPE_CONNEXION and connecte["payload"]["event"] == "connected"
    assert 0 <= connecte["payload"]["after_secs"] <= erreur["payload"]["after_secs"]
    assert erreur["payload"]["error"] == "coupé"


def test_l_analyse_lit_les_connexions_et_la_liaison_et_dit_non_capte_sans_rien():
    run = {
        "id": 9,
        "logs": {
            "realtime_feedback_events": [
                {
                    "type": TYPE_CONNEXION,
                    "turn": 1,
                    "payload": {"component": "voice", "event": "connected", "after_secs": 0.42},
                },
                {
                    "type": TYPE_CONNEXION,
                    "turn": 4,
                    "payload": {"component": "voice", "event": "disconnected"},
                },
                {
                    "type": TYPE_CONNEXION,
                    "turn": 4,
                    "payload": {"component": "transcription", "event": "error"},
                },
            ]
        },
        "gathered_context": {
            "mark_connexions_modele": [
                {"event": "opened", "agent": "Accueil", "host": "api.exemple.test", "after_secs": 0.0},
                {"event": "reused", "agent": "Collègue", "host": "api.exemple.test", "after_secs": 12.0},
            ],
            "mark_reseau": {"status": "ok", "samples": 3, "last": {}, "worst": {"round_trip_ms": 300.0}},
        },
    }
    reseau = analyser_run(run)["network"]
    assert reseau["status"] == "ok"
    assert reseau["providers"]["voice"] == {
        "connected": 1,
        "disconnected": 1,
        "errors": 0,
        "first_connect_secs": 0.42,
    }
    assert reseau["providers"]["transcription"]["errors"] == 1
    assert (reseau["model"]["opened"], reseau["model"]["reused"]) == (1, 1)
    assert reseau["link"]["worst"]["round_trip_ms"] == 300.0
    assert analyser_run({"id": 1})["network"]["status"] == "not_captured"
