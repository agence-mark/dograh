"""[.mark] Le direct d'un appel simulé (chantier direct-et-passe-muette, lot A, P1 à P5).

Ce qui doit tenir : chaque événement du pipeline arrive dans le direct du run, horodaté comme dans le
journal, dans l'ordre ; le direct est borné, et sa fin s'écrit toujours ; **le canal ne fait jamais
attendre l'appel, même quand Redis ne répond plus** (revue du lot A) ; le canal est retiré à la fin de
l'appel même s'il échoue ; la route ne montre que le direct d'un run simulé de l'organisation de
l'utilisateur, à partir de l'index demandé, et dit fini un run terminé sans marqueur de fin.

Chaque scénario tourne dans une seule boucle : la tâche d'écriture du direct vit dans la boucle de
l'appel.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import appel_simule as route
from api.services.appel_simule import direct
from api.services.appel_simule import pipeline as pipeline_simule
from api.services.auth.depends import get_user_with_selected_organization
from api.services.pipecat.ws_sender_registry import get_ws_sender
from api.tests.mark.boucle_isolee import (
    executer_sans_toucher_la_boucle_courante as executer,
)

ORG = 7


class RedisFactice:
    def __init__(self, fige: bool = False):
        self.listes: dict[str, list[str]] = {}
        self.expirations: dict[str, int] = {}
        self.fige = fige

    async def _attendre(self):
        if self.fige:
            await asyncio.Event().wait()  # Accepte la connexion, ne répond jamais.

    def pipeline(self, transaction=True):
        redis, operations = self, []

        class Transaction:
            def rpush(self, cle, valeur):
                operations.append(("rpush", cle, valeur))

            def expire(self, cle, secondes):
                operations.append(("expire", cle, secondes))

            async def execute(self):
                await redis._attendre()
                for nom, cle, valeur in operations:
                    if nom == "rpush":
                        redis.listes.setdefault(cle, []).append(valeur)
                    else:
                        redis.expirations[cle] = valeur

        return Transaction()

    async def lrange(self, cle, debut, fin):
        valeurs = self.listes.get(cle, [])
        return valeurs[debut:] if fin == -1 else valeurs[debut : fin + 1]

    async def delete(self, cle):
        await self._attendre()
        self.listes.pop(cle, None)


@pytest.fixture
def redis():
    faux = RedisFactice()
    with patch.object(direct, "_client_redis", AsyncMock(return_value=faux)):
        yield faux


def test_chaque_evenement_arrive_horodate_et_dans_l_ordre(redis):
    async def scenario():
        await direct.ouvrir_le_direct(42)
        canal = get_ws_sender(42)
        assert canal is not None
        await canal(
            {
                "type": "rtf-user-transcription",
                "payload": {"text": "Bonjour", "final": True},
            }
        )
        await canal(
            {
                "type": "rtf-bot-text",
                "payload": {"text": "Bonjour, que puis-je pour vous ?"},
                "node_id": "n1",
                "node_name": "Accueil",
            }
        )
        await asyncio.sleep(0.05)
        avant_la_fin = await direct.lire_le_direct(42, 0)
        await direct.fermer_le_direct(42)
        return avant_la_fin, await direct.lire_le_direct(42, avant_la_fin["suivant"])

    lu, suite = executer(scenario())
    assert [e["type"] for e in lu["evenements"]] == [
        "rtf-user-transcription",
        "rtf-bot-text",
    ]
    assert all("timestamp" in e for e in lu["evenements"])
    assert lu["suivant"] == 2 and lu["fini"] is False
    assert redis.expirations[direct.cle_du_direct(42)] == direct.DUREE_DE_VIE_S
    assert get_ws_sender(42) is None
    assert suite == {"evenements": [], "suivant": 3, "fini": True}


def test_le_direct_est_borne_et_sa_fin_s_ecrit_toujours(redis):
    async def scenario():
        with patch.object(direct, "MAX_EVENEMENTS", 3):
            await direct.ouvrir_le_direct(5)
            canal = get_ws_sender(5)
            for i in range(6):
                await canal({"type": "rtf-bot-text", "payload": {"text": str(i)}})
            await direct.fermer_le_direct(5)
        return await direct.lire_le_direct(5, 0)

    lu = executer(scenario())
    assert [e["type"] for e in lu["evenements"]] == [
        "rtf-bot-text",
        "rtf-bot-text",
        direct.TYPE_TRONQUE,
    ]
    assert lu["fini"] is True


def test_un_redis_fige_ne_fait_jamais_attendre_l_appel():
    # R1, revue du lot A : Redis accepte la connexion et ne répond plus. Le canal rend la main tout
    # de suite (un changement d'étape l'attend), et la fermeture abandonne dans son délai.
    fige = RedisFactice(fige=True)

    async def scenario():
        with (
            patch.object(direct, "_client_redis", AsyncMock(return_value=fige)),
            patch.object(direct, "DELAI_ECRITURE_S", 0.05),
            patch.object(direct, "DELAI_FERMETURE_S", 0.2),
            patch.object(direct.logger, "error"),
        ):
            await direct.ouvrir_le_direct(9)
            canal = get_ws_sender(9)
            debut = time.monotonic()
            for i in range(50):
                await canal({"type": "rtf-bot-text", "payload": {"text": str(i)}})
            duree_du_canal = time.monotonic() - debut
            debut = time.monotonic()
            await direct.fermer_le_direct(9)
            return duree_du_canal, time.monotonic() - debut

    duree_du_canal, duree_de_fermeture = executer(scenario())
    assert duree_du_canal < 0.05
    assert duree_de_fermeture < 1.0
    assert get_ws_sender(9) is None


def test_un_redis_absent_ne_casse_rien():
    async def scenario():
        with (
            patch.object(
                direct, "_client_redis", AsyncMock(side_effect=ConnectionError("redis"))
            ),
            patch.object(direct.logger, "error") as erreur,
        ):
            await direct.ouvrir_le_direct(10)
            await get_ws_sender(10)({"type": "rtf-bot-text", "payload": {}})
            await direct.fermer_le_direct(10)
            return erreur.call_args_list

    appels = executer(scenario())
    assert appels and all("[.mark]" in a.args[0] for a in appels)


def test_le_canal_est_retire_meme_si_l_appel_echoue(redis):
    run = SimpleNamespace(
        id=77, workflow_id=34, definition=SimpleNamespace(workflow_configurations={})
    )
    db = MagicMock()
    db.get_workflow_run = AsyncMock(return_value=run)
    db.get_workflow = AsyncMock(
        return_value=SimpleNamespace(id=34, user_id=3, workflow_configurations={})
    )
    vu_pendant = {}

    async def pipeline_qui_echoue(*args, **kwargs):
        vu_pendant["canal"] = get_ws_sender(77)
        raise RuntimeError("panne du pipeline")

    async def scenario():
        with pytest.raises(RuntimeError, match="panne du pipeline"):
            await pipeline_simule.jouer_appel_simule(
                MagicMock(),
                workflow_run_id=77,
                organization_id=ORG,
                stream_sid="s",
                call_sid="c",
            )
        return await direct.lire_le_direct(77, 0)

    with (
        patch.object(pipeline_simule, "db_client", db),
        patch.object(
            pipeline_simule,
            "get_effective_ai_model_configuration_for_workflow",
            AsyncMock(return_value=SimpleNamespace(is_realtime=False, realtime=None)),
        ),
        patch.object(pipeline_simule, "creer_transport", AsyncMock()),
        patch.object(pipeline_simule, "create_audio_config", MagicMock()),
        patch.object(
            pipeline_simule.run_pipeline, "_run_pipeline_impl", pipeline_qui_echoue
        ),
    ):
        lu = executer(scenario())
    assert vu_pendant["canal"] is not None
    assert get_ws_sender(77) is None
    assert lu["fini"] is True


@pytest.fixture
def ecran(redis):
    runs = {
        1: SimpleNamespace(id=1, mode="simulated", state="running"),
        2: SimpleNamespace(id=2, mode="smallwebrtc", state="running"),
        3: SimpleNamespace(id=3, mode="simulated", state="completed"),
    }
    db = MagicMock()
    db.get_workflow_run = AsyncMock(
        side_effect=lambda rid, organization_id=None: (
            runs.get(rid) if organization_id == ORG else None
        )
    )
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: (
        SimpleNamespace(id=3, selected_organization_id=ORG)
    )
    with patch.object(route, "db_client", db):
        yield TestClient(app), db


def _remplir(run_id, textes):
    async def scenario():
        await direct.ouvrir_le_direct(run_id)
        canal = get_ws_sender(run_id)
        for texte in textes:
            await canal({"type": "rtf-bot-text", "payload": {"text": texte}})
        await asyncio.sleep(0.05)

    executer(scenario())


def test_la_route_ne_montre_que_le_direct_d_un_run_simule_de_l_organisation(ecran):
    client, db = ecran
    _remplir(1, ("un", "deux", "trois"))
    reponse = client.get("/appel-simule/runs/1/direct?depuis=1")
    assert reponse.status_code == 200
    corps = reponse.json()
    assert [e["payload"]["text"] for e in corps["evenements"]] == ["deux", "trois"]
    assert corps["suivant"] == 3 and corps["fini"] is False
    # R7 : un run qui n'est pas simulé, un run inconnu, une autre organisation → 404.
    assert client.get("/appel-simule/runs/2/direct").status_code == 404
    assert client.get("/appel-simule/runs/99/direct").status_code == 404
    db.get_workflow_run.side_effect = lambda rid, organization_id=None: None
    assert client.get("/appel-simule/runs/1/direct").status_code == 404


def test_un_run_termine_sans_marqueur_de_fin_est_fini(ecran):
    # Revue du lot A : échec avant l'appel, processus perdu ou direct expiré ; l'écran s'arrête.
    client, _ = ecran
    assert client.get("/appel-simule/runs/3/direct").json() == {
        "evenements": [],
        "suivant": 0,
        "fini": True,
    }


def test_un_direct_illisible_le_dit_sans_rien_casser(ecran):
    client, _ = ecran
    with patch.object(
        route, "lire_le_direct", AsyncMock(side_effect=ConnectionError())
    ):
        reponse = client.get("/appel-simule/runs/1/direct")
    assert reponse.status_code == 503
    assert "Live view unavailable" in reponse.json()["detail"]
