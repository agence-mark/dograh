"""[.mark] Le direct d'un appel simulé (chantier direct-et-passe-muette, lot A, P1 à P5).

Ce qui doit tenir : chaque événement du pipeline arrive dans le direct du run, horodaté comme dans le
journal, dans l'ordre ; le direct est borné, et sa fin s'écrit toujours ; un direct en panne ne casse
jamais l'appel ; le canal est retiré à la fin de l'appel même s'il échoue ; la route ne montre que le
direct d'un run simulé de l'organisation de l'utilisateur, à partir de l'index demandé.
"""

from __future__ import annotations

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
    def __init__(self):
        self.listes: dict[str, list[str]] = {}
        self.expirations: dict[str, int] = {}

    async def rpush(self, cle, valeur):
        self.listes.setdefault(cle, []).append(valeur)

    async def llen(self, cle):
        return len(self.listes.get(cle, []))

    async def lrange(self, cle, debut, fin):
        valeurs = self.listes.get(cle, [])
        return valeurs[debut:] if fin == -1 else valeurs[debut : fin + 1]

    async def expire(self, cle, secondes):
        self.expirations[cle] = secondes

    async def delete(self, cle):
        self.listes.pop(cle, None)


@pytest.fixture
def redis():
    faux = RedisFactice()
    with patch.object(direct, "_client_redis", AsyncMock(return_value=faux)):
        yield faux


def test_chaque_evenement_arrive_horodate_et_dans_l_ordre(redis):
    executer(direct.ouvrir_le_direct(42))
    canal = get_ws_sender(42)
    assert canal is not None
    executer(
        canal(
            {
                "type": "rtf-user-transcription",
                "payload": {"text": "Bonjour", "final": True},
            }
        )
    )
    executer(
        canal(
            {
                "type": "rtf-bot-text",
                "payload": {"text": "Bonjour, que puis-je pour vous ?"},
                "node_id": "n1",
                "node_name": "Accueil",
            }
        )
    )
    lu = executer(direct.lire_le_direct(42, 0))
    assert [e["type"] for e in lu["evenements"]] == [
        "rtf-user-transcription",
        "rtf-bot-text",
    ]
    assert all("timestamp" in e for e in lu["evenements"])
    assert lu["suivant"] == 2 and lu["fini"] is False
    assert redis.expirations[direct.cle_du_direct(42)] == direct.DUREE_DE_VIE_S
    # Relu à partir du suivant : rien de neuf, puis la fin.
    executer(direct.fermer_le_direct(42))
    assert get_ws_sender(42) is None
    suite = executer(direct.lire_le_direct(42, lu["suivant"]))
    assert suite == {"evenements": [], "suivant": 3, "fini": True}


def test_le_direct_est_borne_et_sa_fin_s_ecrit_toujours(redis):
    with patch.object(direct, "MAX_EVENEMENTS", 3):
        canal = direct.canal_du_direct(5)
        for i in range(6):
            executer(canal({"type": "rtf-bot-text", "payload": {"text": str(i)}}))
        executer(direct.fermer_le_direct(5))
    lu = executer(direct.lire_le_direct(5, 0))
    assert [e["type"] for e in lu["evenements"]] == [
        "rtf-bot-text",
        "rtf-bot-text",
        direct.TYPE_TRONQUE,
    ]
    assert lu["fini"] is True


def test_un_direct_en_panne_ne_casse_jamais_l_appel():
    # R1 : Redis absent ; le canal avale l'erreur et l'écrit au journal.
    with (
        patch.object(
            direct, "_client_redis", AsyncMock(side_effect=ConnectionError("redis"))
        ),
        patch.object(direct.logger, "error") as erreur,
    ):
        executer(direct.canal_du_direct(9)({"type": "rtf-bot-text", "payload": {}}))
        executer(direct.fermer_le_direct(9))
    assert "[.mark]" in erreur.call_args_list[0].args[0]


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
        with pytest.raises(RuntimeError, match="panne du pipeline"):
            executer(
                pipeline_simule.jouer_appel_simule(
                    MagicMock(),
                    workflow_run_id=77,
                    organization_id=ORG,
                    stream_sid="s",
                    call_sid="c",
                )
            )
    assert vu_pendant["canal"] is not None
    assert get_ws_sender(77) is None
    assert executer(direct.lire_le_direct(77, 0))["fini"] is True


@pytest.fixture
def ecran(redis):
    runs = {
        1: SimpleNamespace(id=1, mode="simulated"),
        2: SimpleNamespace(id=2, mode="smallwebrtc"),
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


def test_la_route_ne_montre_que_le_direct_d_un_run_simule_de_l_organisation(ecran):
    client, db = ecran
    canal = direct.canal_du_direct(1)
    for texte in ("un", "deux", "trois"):
        executer(canal({"type": "rtf-bot-text", "payload": {"text": texte}}))
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


def test_un_direct_illisible_le_dit_sans_rien_casser(ecran):
    client, _ = ecran
    with patch.object(
        route, "lire_le_direct", AsyncMock(side_effect=ConnectionError())
    ):
        reponse = client.get("/appel-simule/runs/1/direct")
    assert reponse.status_code == 503
    assert "Live view unavailable" in reponse.json()["detail"]
