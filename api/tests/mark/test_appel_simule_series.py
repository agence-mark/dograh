"""[.mark] Les séries de l'appelant simulé (chantier langwatch-et-fenetre-du-run, lot 3, L9 à L13, L18,
L19, Q1 à Q3).

Ce qui doit tenir : la série s'arrête avant de dépasser son plafond et quand on l'arrête à
l'écran ; une seule série à la fois par organisation ; le sous-processus ne reçoit QUE les deux
clés choisies (aucune variable de l'API, rien pour LangWatch) ; un secret n'apparaît jamais dans
une erreur rangée ; le renvoi suit la décision du scénario ; la latence du scénario fait échouer ;
les scénarios d'un agent ne touchent pas ceux d'un autre ; les routes restent dans l'organisation.
"""

from __future__ import annotations

import asyncio
import os
import sys
import textwrap
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import appel_simule as route
from api.schemas.appel_simule import (
    Comportements,
    ReglagesAppelantSimule,
    RoleSimule,
    ScenarioSimule,
    VoixSimulee,
)
from api.schemas.fenetre_du_run import LignePrix, ReglagesFenetreDuRun
from api.services.analyse_run.du_run import bloc_simulation
from api.services.appel_simule import reglages as stockage
from api.services.appel_simule import serie as moteur
from api.services.appel_simule.reglages import AppelDeSerie, SerieSimulee
from api.services.auth.depends import get_user_with_selected_organization

ORG = 7


def _scenario(i="s1", workflow_id=34, **champs):
    return ScenarioSimule(
        id=i,
        workflow_id=workflow_id,
        nom=champs.pop("nom", f"Scénario {i}"),
        role=champs.pop("role", "Un particulier qui appelle pour un rendez-vous."),
        criteres=champs.pop("criteres", ["L'agent demande le nom"]),
        **champs,
    )


def _reglages(**champs):
    return ReglagesAppelantSimule(
        appelant=RoleSimule(consigne="Consigne générale.", identifiant="cle-mistral"),
        juge=RoleSimule(consigne="Juge.", identifiant="cle-mistral"),
        voix=VoixSimulee(voix="voix-fr", identifiant="cle-eleven"),
        **champs,
    )


class Configurations:
    """``organization_configurations`` en mémoire."""

    def __init__(self):
        self.lignes: dict[tuple[int, str], dict] = {}

    async def get_configuration(self, org, cle):
        valeur = self.lignes.get((org, cle))
        return None if valeur is None else SimpleNamespace(value=valeur)

    async def upsert_configuration(self, org, cle, valeur):
        self.lignes[(org, cle)] = valeur


class RedisFactice:
    def __init__(self):
        self.valeurs: dict[str, str] = {}

    async def set(self, cle, valeur, nx=False, ex=None):
        if nx and cle in self.valeurs:
            return None
        self.valeurs[cle] = valeur
        return True

    async def get(self, cle):
        return self.valeurs.get(cle)

    async def delete(self, *cles):
        for cle in cles:
            self.valeurs.pop(cle, None)


@pytest.fixture
def base():
    configurations = Configurations()
    db = MagicMock()
    db.get_configuration = configurations.get_configuration
    db.upsert_configuration = configurations.upsert_configuration
    db.get_workflow = AsyncMock(
        side_effect=lambda wid, organization_id=None: (
            SimpleNamespace(id=wid, user_id=3)
            if organization_id == ORG and wid == 34
            else None
        )
    )
    identifiants = {
        "cle-mistral": {"header_name": "Authorization", "api_key": "SECRET-MISTRAL"},
        "cle-eleven": {"header_name": "xi-api-key", "api_key": "SECRET-ELEVEN"},
    }
    db.get_credential_by_uuid = AsyncMock(
        side_effect=lambda u, org: (
            SimpleNamespace(credential_data=identifiants[u])
            if org == ORG and u in identifiants
            else None
        )
    )
    redis = RedisFactice()
    file = AsyncMock()
    with (
        patch.object(stockage, "db_client", db),
        patch.object(moteur, "db_client", db),
        patch.object(route, "db_client", db),
        patch.object(moteur, "_client_redis", AsyncMock(return_value=redis)),
        patch.object(moteur, "lire_reglages_fenetre", AsyncMock(return_value=None)),
        patch("api.tasks.arq.enqueue_job", file),
    ):
        yield SimpleNamespace(
            db=db, redis=redis, file=file, configurations=configurations
        )


# --- Ce que reçoit le lanceur ------------------------------------------------------------------


def test_la_consigne_n_ajoute_que_les_comportements_coches():
    scenario = _scenario(
        consigne="Tu donnes ton adresse seulement si on te la demande.",
        comportements=Comportements(presse=True, hesite=False),
    )
    consigne = moteur.consigne_de_l_appelant(_reglages(), scenario)
    assert consigne.startswith("Consigne générale.")
    assert "Ton rôle : Un particulier qui appelle pour un rendez-vous." in consigne
    assert "Tu donnes ton adresse" in consigne
    assert moteur.COMPORTEMENTS["presse"] in consigne
    assert moteur.COMPORTEMENTS["hesite"] not in consigne


def test_l_entree_du_lanceur_porte_la_voix_et_la_coupure():
    entree = moteur.entree_du_lanceur(
        "wss://x/ws/1/j",
        _reglages(),
        _scenario(comportements=Comportements(coupe_la_parole=True), tours_max=6),
    )
    assert entree["appelant"]["voix"] == "elevenlabs/voix-fr"
    assert entree["appelant"]["coupe_la_parole"] == moteur.PROBABILITE_COUPURE
    assert entree["scenario"]["tours_max"] == 6
    assert entree["juge"]["modele"] == "mistral/mistral-small-latest"
    assert "SECRET" not in str(entree)


def test_le_sous_processus_ne_recoit_que_les_deux_cles(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "cle-de-l-agent")
    monkeypatch.setenv("LANGWATCH_API_KEY", "cle-langwatch")
    env = moteur.environnement("SECRET-MISTRAL", "SECRET-ELEVEN", "/tmp/x")
    assert env["SIMULATEUR_CLE_MODELE"] == "SECRET-MISTRAL"
    assert env["ELEVENLABS_API_KEY"] == "SECRET-ELEVEN"
    assert env["HOME"] == env["SCENARIO_CACHE_DIR"] == "/tmp/x"
    assert not any(k.startswith("LANGWATCH") for k in env)
    assert "cle-de-l-agent" not in env.values()
    assert set(env) == {
        "PATH",
        "HOME",
        "SCENARIO_CACHE_DIR",
        "SCENARIO_HEADLESS",
        "SCENARIO_DISABLE_SIMULATION_REPORT_INFO",
        "PYTHONUTF8",
        "PYTHONUNBUFFERED",
        "SIMULATEUR_CLE_MODELE",
        "ELEVENLABS_API_KEY",
    }


def test_l_adresse_websocket_suit_celle_de_l_api():
    assert moteur.base_ws("https://api.exemple.fr") == "wss://api.exemple.fr"
    assert moteur.base_ws("http://localhost:8000") == "ws://localhost:8000"


def test_le_verdict_est_la_derniere_ligne_marquee():
    sortie = 'bruit\nMARK_VERDICT {"success": false}\nMARK_VERDICT {"success": true}\n'
    assert moteur.lire_le_verdict(sortie) == {"success": True}
    assert "error" in moteur.lire_le_verdict("rien")
    assert "error" in moteur.lire_le_verdict("MARK_VERDICT {pas du json")


# --- Le sous-processus, pour de vrai (un faux lanceur) -------------------------------------------


def _faux_lanceur(tmp_path, corps: str):
    chemin = tmp_path / "jouer.py"
    chemin.write_text(textwrap.dedent(corps), encoding="utf-8")
    return chemin


async def test_le_lanceur_recoit_l_entree_et_l_environnement(tmp_path):
    lanceur = _faux_lanceur(
        tmp_path,
        """
        import json, os, sys
        entree = json.load(sys.stdin)
        print("MARK_VERDICT " + json.dumps({
            "success": True,
            "adresse": entree["adresse"],
            "cle": os.environ.get("SIMULATEUR_CLE_MODELE"),
            "langwatch": any(k.startswith("LANGWATCH") for k in os.environ),
        }))
        """,
    )
    env = moteur.environnement("SECRET-MISTRAL", "SECRET-ELEVEN", str(tmp_path))
    # Windows (poste de dev) : sans ces deux variables, un processus crée un dossier
    # « %SystemDrive% » dans le dossier courant. Sans effet sous Linux (CI, image).
    for variable in ("SYSTEMROOT", "SYSTEMDRIVE"):
        if variable in os.environ:
            env[variable] = os.environ[variable]
    with (
        patch.object(moteur, "PYTHON_SIMULATEUR", sys.executable),
        patch.object(moteur, "LANCEUR", lanceur),
    ):
        verdict = await moteur.lancer_le_lanceur({"adresse": "wss://x"}, env, 60, [])
    assert verdict == {
        "success": True,
        "adresse": "wss://x",
        "cle": "SECRET-MISTRAL",
        "langwatch": False,
    }


async def test_une_erreur_rangee_ne_montre_jamais_un_secret(tmp_path):
    lanceur = _faux_lanceur(
        tmp_path,
        """
        import json
        print("MARK_VERDICT " + json.dumps({"error": "AuthenticationError: bad key SECRET-MISTRAL"}))
        """,
    )
    with (
        patch.object(moteur, "PYTHON_SIMULATEUR", sys.executable),
        patch.object(moteur, "LANCEUR", lanceur),
    ):
        verdict = await moteur.lancer_le_lanceur({}, None, 60, ["SECRET-MISTRAL"])
    assert verdict["error"] == "AuthenticationError: bad key ***"


async def test_un_lanceur_qui_ne_finit_pas_est_arrete(tmp_path):
    lanceur = _faux_lanceur(tmp_path, "import time\ntime.sleep(30)\n")
    with (
        patch.object(moteur, "PYTHON_SIMULATEUR", sys.executable),
        patch.object(moteur, "LANCEUR", lanceur),
    ):
        verdict = await moteur.lancer_le_lanceur({}, None, 1, [])
    assert verdict["error"].startswith("the simulator did not finish")


# --- Le renvoi, le verdict, le coût -------------------------------------------------------------


@pytest.mark.parametrize(
    ("decision", "attendu"),
    [("accepte", True), ("refuse", False), ("sans_reponse", None)],
)
async def test_le_renvoi_suit_la_decision_du_scenario(decision, attendu):
    donner = AsyncMock(return_value=True)
    fin = asyncio.Event()
    with (
        patch.object(moteur, "renvoi_en_attente", AsyncMock(return_value=True)),
        patch.object(moteur, "donner_la_decision", donner),
        patch.object(moteur, "INTERVALLE_S", 0.01),
    ):
        tache = asyncio.create_task(moteur.suivre_le_renvoi(12, decision, fin))
        await asyncio.sleep(0.05)
        fin.set()
        await tache
    if attendu is None:
        donner.assert_not_awaited()
    else:
        donner.assert_awaited()
        assert donner.await_args.args == (12, attendu)


def _analyse(pire=2.0, cout=0.03):
    return {
        "latency": {"stats": {"worst_silence_secs": pire, "median_silence_secs": 1.1}},
        "summary": {"cost": {"status": "ok", "total": cout, "partial": False}},
        "incidents": {"items": [{"kind": "slow_turn"}]},
    }


def test_un_tour_trop_lent_fait_echouer_le_scenario():
    verdict = {"success": True, "passed_criteria": ["a"], "failed_criteria": []}
    cout = {"total": 0.01, "unpriced": []}
    assert moteur.resultat_de_l_appel(verdict, _analyse(), _scenario(), cout)["success"]
    resultat = moteur.resultat_de_l_appel(
        verdict, _analyse(pire=4.2), _scenario(latence_max_s=3), cout
    )
    assert resultat["success"] is False
    assert resultat["failed_criteria"] == ["latency: worst turn 4.20 s > 3.0 s"]
    assert resultat["agent_cost"] == 0.03
    assert resultat["incidents"] == 1


def test_une_erreur_du_simulateur_n_est_jamais_une_reussite():
    resultat = moteur.resultat_de_l_appel(
        {"success": True, "error": "boom"},
        _analyse(),
        _scenario(),
        {"total": 0, "unpriced": []},
    )
    assert resultat["success"] is False and resultat["error"] == "boom"


def test_le_cout_de_l_appelant_au_tarif_de_la_table():
    table = ReglagesFenetreDuRun(
        lignes=[
            LignePrix(
                brique="tts",
                modele="eleven_v3",
                par_million_caracteres=100,
                date_du_tarif=date(2026, 10, 1),
            ),
            LignePrix(
                brique="stt",
                modele="scribe_v1",
                par_minute=0.4,
                date_du_tarif=date(2026, 10, 1),
            ),
        ]
    )
    verdict = {
        "messages": [
            {"role": "user", "content": "x" * 1000},
            {"role": "assistant", "content": "y" * 99},
        ]
    }
    cout = moteur.cout_de_l_appelant(verdict, 90, table)
    assert cout["characters"] == 1000
    assert cout["total"] == round(1000 / 1_000_000 * 100 + 1.5 * 0.4, 4)
    assert cout["unpriced"] == ["llm: simulated caller and judge"]
    assert set(moteur.cout_de_l_appelant(verdict, 90, None)["unpriced"]) == {
        "llm: simulated caller and judge",
        "tts: eleven_v3",
        "stt: scribe_v1",
    }


def test_l_estimation_vient_des_appels_deja_joues_de_l_agent():
    joue = SerieSimulee(
        id="a",
        workflow_id=34,
        lancee_le="x",
        lancee_par=3,
        plafond=5,
        appels=[
            AppelDeSerie(scenario_id="s", scenario_nom="s", cout=0.2),
            AppelDeSerie(scenario_id="s", scenario_nom="s", cout=0.4),
        ],
    )
    assert moteur.estimer_le_cout([joue], 34, 5) == 1.5
    assert moteur.estimer_le_cout([joue], 99, 5) is None


# --- Le stockage, par agent ---------------------------------------------------------------------


async def test_les_scenarios_d_un_agent_ne_touchent_pas_ceux_d_un_autre(base):
    await stockage.remplacer_scenarios(ORG, 34, [_scenario("a"), _scenario("b")])
    await stockage.remplacer_scenarios(ORG, 35, [_scenario("c", workflow_id=35)])
    await stockage.remplacer_scenarios(ORG, 34, [_scenario("b")])
    assert [s.id for s in await stockage.lire_scenarios(ORG, 34)] == ["b"]
    assert [s.id for s in await stockage.lire_scenarios(ORG, 35)] == ["c"]
    with pytest.raises(ValueError):
        await stockage.remplacer_scenarios(ORG, 34, [_scenario("d", workflow_id=35)])


def test_deux_scenarios_du_meme_agent_ne_portent_pas_le_meme_nom():
    from api.schemas.appel_simule import BibliothequeScenarios

    with pytest.raises(ValueError):
        BibliothequeScenarios(
            scenarios=[_scenario("a", nom="Panne"), _scenario("b", nom="panne ")]
        )


# --- Lancer une série ---------------------------------------------------------------------------


async def _preparer(base, reglages=None, scenarios=("s1", "s2", "s3")):
    await stockage.enregistrer_reglages(ORG, reglages or _reglages())
    await stockage.remplacer_scenarios(ORG, 34, [_scenario(i) for i in scenarios])


async def test_une_serie_se_lance_et_part_en_file(base):
    await _preparer(base)
    serie = await moteur.lancer_serie(ORG, 3, 34, ["s1", "s2"])
    assert serie.etat == "en_cours" and serie.plafond == 5.0
    assert [a.scenario_id for a in serie.appels] == ["s1", "s2"]
    base.file.assert_awaited_once()
    assert base.file.await_args.args[1:] == (ORG, serie.id)
    assert (await stockage.lire_serie(ORG, serie.id)).id == serie.id


async def test_une_seule_serie_a_la_fois(base):
    await _preparer(base)
    await moteur.lancer_serie(ORG, 3, 34, ["s1"])
    with pytest.raises(moteur.SerieRefusee, match="already playing"):
        await moteur.lancer_serie(ORG, 3, 34, ["s2"])


@pytest.mark.parametrize(
    ("reglages", "ids", "message"),
    [
        (None, ["inconnu"], "not filed"),
        (_reglages(taille_max_serie=1), ["s1", "s2"], "at most"),
        (
            _reglages().model_copy(
                update={"voix": VoixSimulee(voix="v", identifiant=None)}
            ),
            ["s1"],
            "ElevenLabs credential",
        ),
        (
            _reglages().model_copy(
                update={"appelant": RoleSimule(consigne="c", identifiant="autre")}
            ),
            ["s1"],
            "same model credential",
        ),
    ],
)
async def test_une_serie_mal_reglee_est_refusee_sans_verrou(
    base, reglages, ids, message
):
    await _preparer(base, reglages)
    with pytest.raises(moteur.SerieRefusee, match=message):
        await moteur.lancer_serie(ORG, 3, 34, ids)
    base.file.assert_not_awaited()
    assert not base.redis.valeurs


# --- Jouer une série : plafond et arrêt ---------------------------------------------------------


def _appel_qui_coute(montant):
    async def jouer(org, workflow, serie, appel, scenario, reglages, cles, table):
        appel.etat, appel.reussi, appel.cout = "joue", True, montant
        serie.cout = round(serie.cout + montant, 4)

    return jouer


async def test_la_serie_s_arrete_avant_de_depasser_le_plafond(base):
    await _preparer(base)
    serie = await moteur.lancer_serie(ORG, 3, 34, ["s1", "s2", "s3"])
    with patch.object(moteur, "_jouer_un_appel", side_effect=_appel_qui_coute(2.0)):
        await moteur.jouer_serie(ORG, serie.id)
    finale = await stockage.lire_serie(ORG, serie.id)
    assert finale.etat == "arretee_plafond"
    assert [a.etat for a in finale.appels] == ["joue", "joue", "a_jouer"]
    assert finale.cout == 4.0 and finale.terminee_le
    assert not base.redis.valeurs  # verrou rendu


async def test_une_serie_arretee_a_l_ecran_ne_joue_plus(base):
    await _preparer(base)
    serie = await moteur.lancer_serie(ORG, 3, 34, ["s1", "s2"])
    assert await moteur.arreter_serie(ORG, serie.id)
    jouer = AsyncMock()
    with patch.object(moteur, "_jouer_un_appel", jouer):
        await moteur.jouer_serie(ORG, serie.id)
    jouer.assert_not_awaited()
    assert (await stockage.lire_serie(ORG, serie.id)).etat == "arretee"
    assert not base.redis.valeurs


async def test_un_appel_en_echec_n_arrete_pas_la_serie(base):
    await _preparer(base)
    serie = await moteur.lancer_serie(ORG, 3, 34, ["s1", "s2"])
    appels = iter([RuntimeError("boom"), None])

    async def jouer(org, workflow, serie_, appel, *reste):
        erreur = next(appels)
        if erreur:
            raise erreur
        appel.etat, appel.cout = "joue", 0.1

    with patch.object(moteur, "_jouer_un_appel", side_effect=jouer):
        await moteur.jouer_serie(ORG, serie.id)
    finale = await stockage.lire_serie(ORG, serie.id)
    assert finale.etat == "terminee"
    assert [(a.etat, a.erreur) for a in finale.appels] == [
        ("echec", "RuntimeError"),
        ("joue", None),
    ]


# --- Le bloc Simulation de la fenêtre ----------------------------------------------------------


def test_le_bloc_simulation_ne_montre_jamais_l_empreinte_du_jeton():
    run = SimpleNamespace(
        extra={
            "mark_simulation": {"serie_id": "a", "jeton_sha256": "abc", "resultat": {}}
        }
    )
    assert bloc_simulation(run) == {"serie_id": "a", "resultat": {}}
    assert bloc_simulation(SimpleNamespace(extra={})) is None


# --- Les routes de l'écran : dans l'organisation ------------------------------------------------


@pytest.fixture
def ecran(base):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: (
        SimpleNamespace(id=3, selected_organization_id=ORG)
    )
    return TestClient(app)


def test_les_scenarios_d_un_agent_d_une_autre_organisation_sont_introuvables(ecran):
    assert ecran.get("/appel-simule/agents/99/scenarios").status_code == 404
    reponse = ecran.put(
        "/appel-simule/agents/99/scenarios",
        json=[_scenario(workflow_id=99).model_dump()],
    )
    assert reponse.status_code == 404


def test_un_identifiant_inconnu_ne_s_enregistre_pas(ecran):
    corps = _reglages().model_dump()
    corps["voix"]["identifiant"] = "identifiant-d-une-autre-organisation"
    assert ecran.put("/appel-simule/reglages", json=corps).status_code == 404
    assert (
        ecran.put("/appel-simule/reglages", json=_reglages().model_dump()).status_code
        == 200
    )
    lus = ecran.get("/appel-simule/reglages").json()
    assert lus["voix"]["identifiant"] == "cle-eleven"
    assert "SECRET" not in str(lus)


def test_un_lancement_refuse_dit_pourquoi(ecran):
    reponse = ecran.post(
        "/appel-simule/agents/34/series", json={"scenario_ids": ["inconnu"]}
    )
    assert reponse.status_code == 409
    assert "not filed" in reponse.json()["detail"]


def test_le_rapport_ne_lit_que_les_runs_de_l_agent_de_la_serie(ecran, base):
    serie = SerieSimulee(
        id="r",
        workflow_id=34,
        lancee_le="x",
        lancee_par=3,
        plafond=5,
        appels=[
            AppelDeSerie(scenario_id="s", scenario_nom="s", run_id=1, etat="joue"),
            AppelDeSerie(scenario_id="s", scenario_nom="s", run_id=2, etat="joue"),
        ],
    )
    base.configurations.lignes[(ORG, stockage.CLE_SERIES)] = stockage.RegistreSeries(
        series=[serie]
    ).model_dump(mode="json")
    runs = {
        1: SimpleNamespace(
            workflow_id=34, extra={"mark_simulation": {"resultat": {"success": True}}}
        ),
        2: SimpleNamespace(
            workflow_id=35, extra={"mark_simulation": {"resultat": {"success": True}}}
        ),
    }
    base.db.get_workflow_run = AsyncMock(
        side_effect=lambda i, organization_id=None: (
            runs.get(i) if organization_id == ORG else None
        )
    )
    rapport = ecran.get("/appel-simule/series/r").json()
    assert [a["resultat"] for a in rapport["appels"]] == [{"success": True}, None]
    assert ecran.get("/appel-simule/series/inconnue").status_code == 404


# --- Hors des statistiques réelles (L9) ----------------------------------------------------------


async def test_le_rapport_quotidien_ignore_les_appels_simules():
    from datetime import UTC, datetime

    from sqlalchemy.dialects import postgresql

    from api.db.reports_client import ReportsClient

    requetes = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *erreur):
            return False

        async def execute(self, requete):
            requetes.append(requete)
            return SimpleNamespace(all=lambda: [])

    client = ReportsClient.__new__(ReportsClient)
    client.async_session = Session
    debut = datetime(2026, 10, 5, tzinfo=UTC)
    assert await client.get_workflow_runs_for_daily_report(ORG, debut, debut) == []
    sql = str(
        requetes[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "workflow_runs.mode != 'simulated'" in sql
