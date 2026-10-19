"""[.mark] Le chronomètre par tour et la mesure M2 (fiabilite-orchestration, lot 9, F8 et F11).

M1 (déjà là) : dernier mot de l'appelant selon Soniox → premier TEXTE de l'agent. M2 (nouveau) :
dernier mot → premier SON sorti de la voix. Le chronomètre découpe le tour en étapes (tour décidé
fini, requête partie, premier mot du modèle, première phrase complète, envoi à la voix, premier son).

Deux outils indépendants, un cas rouge connu (R7) : le run 1468 du banc du 19/10 (copie Large 3,
5G), gelé SANS TEXTE dans ``donnees/run_1468_trace_figee.json`` : serveur 1,7 s (M1), 3,3 s à
l'oreille (détection de voix sur l'enregistrement, ``mark_silences``). Constat du lot : M2 retombe sur M1
(à 0,15 s près : le premier son sort de la voix au moment où le premier texte est noté) ; les 1,6 s qui
manquent à l'oreille sont APRÈS le service de voix (sortie audio, réseau, tampon du navigateur), et le
chronomètre l'écrit (``heard_minus_m2_secs``) au lieu de le cacher.

| Test | Ce qu'il prouve |
|---|---|
| équivalence | le serveur et ``chronometreDuRun`` de ``mesures-run.mjs`` rendent les MÊMES chiffres sur 35 runs du corpus du 05/10 et sur le 1468 (attendus calculés par l'outil du labo) |
| 1468 | M1 médiane 1,6 à 1,8 s ; M2 à 0,15 s de M1 et sous l'oreille (3,26 s) ; l'écart restant à l'oreille est écrit |
| étapes | chaque tour mesuré : les étapes se suivent dans l'ordre ; le tour à outil (tour 2) a une requête qui part après la fin de tour |
| tour non mesuré | un tour sans transcription finale ne donne pas de M2 et dit pourquoi |
| écart fabriqué (R7) | un écart d'une milliseconde sur la voix est vu |
| analyse | le bloc ``chrono`` de l'analyse du run porte les tours et les contrôles |
"""

import copy
import json
import math
from pathlib import Path

import pytest

from api.services.analyse_run.analyse import analyser_run
from api.services.analyse_run.mesures import (
    ETAPES_DU_CHRONOMETRE,
    chronometre_du_run,
    controle_des_mesures,
    mediane_basse,
    mesurer_run,
)

DONNEES = Path(__file__).parent / "donnees"
CORPUS = DONNEES / "analyse_run_corpus_2026-10-05.json"
GELE = DONNEES / "run_1468_trace_figee.json"
ATTENDUS = DONNEES / "chrono_attendus_2026-10-19.json"


def _comme_json(valeur):
    if isinstance(valeur, float) and math.isnan(valeur):
        return None
    if isinstance(valeur, dict):
        return {k: _comme_json(v) for k, v in valeur.items()}
    if isinstance(valeur, list):
        return [_comme_json(v) for v in valeur]
    return valeur


@pytest.fixture(scope="module")
def runs():
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))["runs"]
    return {str(r["id"]): r for r in [*corpus, json.loads(GELE.read_text(encoding="utf-8"))]}


@pytest.fixture(scope="module")
def attendus():
    return json.loads(ATTENDUS.read_text(encoding="utf-8"))


def test_meme_chronometre_que_l_outil_du_labo(runs, attendus):
    assert len(runs) == 36 and set(runs) == set(attendus)
    mesures = 0
    for identifiant, run in runs.items():
        obtenu = _comme_json(chronometre_du_run(run))
        assert obtenu == attendus[identifiant], f"run {identifiant}"
        mesures += len(obtenu["m2"])
    assert mesures >= 250  # 279 M2 sur le corpus à l'écriture


def test_le_1468_m2_entre_le_serveur_et_l_oreille(runs):
    run = runs["1468"]
    m1 = mediane_basse(mesurer_run(run)["tour"])
    chrono = chronometre_du_run(run)
    m2 = mediane_basse(chrono["m2"])
    oreille = run["gathered_context"]["mark_silences"]["median_secs"]
    assert 1.6 <= m1 <= 1.8  # le « 0,7 s » faux de R11 ne revient pas : le serveur disait 1,7 s
    assert oreille == pytest.approx(3.264)
    assert abs(m2 - m1) < 0.15 and m2 < oreille  # M2 compte la voix ; il ne voit pas la sortie audio
    controles = controle_des_mesures(run, oreille)
    assert controles["m1_median_secs"] == m1 and controles["m2_median_secs"] == m2
    # Ce que le chronomètre ne voit pas encore est écrit, pas caché : plus d'une seconde ici.
    assert controles["heard_minus_m2_secs"] == pytest.approx(oreille - m2, abs=0.001)
    assert controles["heard_minus_m2_secs"] > 1.0
    assert len(chrono["m2"]) == 7


def test_les_etapes_se_suivent_et_le_tour_a_outil_a_une_requete_tardive(runs):
    chrono = chronometre_du_run(runs["1468"])
    mesures = [t for t in chrono["tours"] if t["mesure"]]
    assert len(mesures) == 7
    for tour in mesures:
        assert tour["finDeTour"] <= tour["requete"] <= tour["premierMot"] <= tour["voix"] <= tour["premierSon"]
        assert tour["m2"] == tour["premierSon"]
        assert all(tour[e] is not None for e in ETAPES_DU_CHRONOMETRE if e != "phrase")
    par_tour = {t["tour"]: t for t in chrono["tours"]}
    # Tour 2 : une porte franchie, deux passes du modèle : la requête qui parle part plus tard.
    assert par_tour[2]["passes"] == 2
    assert par_tour[2]["requete"] - par_tour[2]["finDeTour"] > 1.0
    # Tour 3 : une seule passe, la requête est celle de la fin de tour.
    assert par_tour[3]["passes"] == 1 and par_tour[3]["requete"] == par_tour[3]["finDeTour"]


def test_un_tour_sans_transcription_finale_n_a_pas_de_m2(runs):
    chrono = chronometre_du_run(runs["1468"])
    tour_11 = next(t for t in chrono["tours"] if t["tour"] == 11)
    assert tour_11["mesure"] is False and tour_11["raison"] == "no_final_transcript"
    assert tour_11["m2"] is None and tour_11["premierSon"] is None


def test_un_ecart_fabrique_est_vu(runs, attendus):
    """R7 : sans ce test, une comparaison toujours vraie passerait inaperçue."""
    run = copy.deepcopy(runs["1468"])
    for evenement in run["logs"]["realtime_feedback_events"]:
        if evenement["type"] == "mark-latency-breakdown" and evenement["turn"] == 3:
            for ttfb in evenement["payload"]["ttfb"]:
                if "TTSService" in ttfb["processor"]:
                    ttfb["duration_secs"] += 0.001
    assert _comme_json(chronometre_du_run(run)) != attendus["1468"]


def test_l_analyse_du_run_porte_le_chronometre(runs):
    analyse = analyser_run(runs["1468"])
    chrono = analyse["chrono"]
    assert chrono["status"] == "ok" and chrono["m2_count"] == 7
    tour_3 = next(t for t in chrono["turns"] if t["turn"] == 3)
    assert tour_3["measured"] and set(tour_3["stages"]) == {
        "turn_closed",
        "request_sent",
        "first_model_word",
        "first_sentence",
        "sent_to_voice",
        "first_sound",
    }
    assert chrono["controls"]["heard_median_secs"] == pytest.approx(3.264)
    assert analyser_run({"id": 1, "logs": {"realtime_feedback_events": []}})["chrono"]["status"] == "not_captured"
