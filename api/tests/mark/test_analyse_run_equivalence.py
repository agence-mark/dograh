"""La fenêtre du run et l'outil du labo rendent les MÊMES chiffres (.mark, chantier
langwatch-et-fenetre-du-run, décision L1).

Question : ``api/services/analyse_run/mesures.py`` calcule-t-il, run par run, exactement ce que
``Labo-agent-vocal/agents/outils/mesures-run.mjs`` calcule ?

Corpus : ``donnees/analyse_run_corpus_2026-10-05.json``, 35 runs de l'agent n° 34 (33 vocaux,
2 au clavier) exportés SANS TEXTE par ``exporter-corpus-analyse-run.mjs``, avec ce que l'outil du
labo a calculé dessus (``attendus``). L'export a vérifié que retirer les textes ne change aucun
chiffre.

Rouge prouvé (R7) : un écart fabriqué sur un seul tour est vu (dernier test).
"""

import copy
import json
import math
from pathlib import Path

import pytest

from api.services.analyse_run.mesures import mediane_basse, mesurer_run

CORPUS = Path(__file__).parent / "donnees" / "analyse_run_corpus_2026-10-05.json"


def _comme_json(valeur):
    """Ce que JSON.stringify écrit : NaN devient null."""
    if isinstance(valeur, float) and math.isnan(valeur):
        return None
    if isinstance(valeur, dict):
        return {k: _comme_json(v) for k, v in valeur.items()}
    if isinstance(valeur, list):
        return [_comme_json(v) for v in valeur]
    return valeur


def _resume(mesure: dict) -> dict:
    """Comme l'export : le nombre de post-scriptums, pas leur contenu."""
    return _comme_json({**mesure, "postScriptums": len(mesure["postScriptums"])})


@pytest.fixture(scope="module")
def corpus():
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def test_le_corpus_couvre_assez_de_runs_et_de_tours(corpus):
    assert len(corpus["runs"]) >= 30
    tours = sum(len(a["detailTours"]) for a in corpus["attendus"].values())
    assert tours >= 250  # 272 tours mesurés à l'export du 05/10
    # Le corpus contient des tours que la mesure écarte : sans eux, l'équivalence ne prouverait
    # rien sur les cas limites.
    assert any(not a["detailTours"] for a in corpus["attendus"].values())


@pytest.mark.parametrize("indice", range(35))
def test_meme_mesure_que_l_outil_du_labo(corpus, indice):
    run = corpus["runs"][indice]
    attendu = corpus["attendus"][str(run["id"])]
    assert _resume(mesurer_run(run)) == attendu


def test_mediane_basse_du_15_09():
    assert mediane_basse([]) is None
    assert mediane_basse([3.0]) == 3.0
    assert mediane_basse([4.0, 1.0, 3.0, 2.0]) == 2.0  # basse, pas 2,5
    assert mediane_basse([5.0, 1.0, 3.0]) == 3.0


def test_un_ecart_fabrique_est_vu(corpus):
    """R7 : sans ce test, une comparaison toujours vraie passerait inaperçue."""
    run = copy.deepcopy(next(r for r in corpus["runs"] if r["id"] == 967))
    attendu = corpus["attendus"]["967"]
    for evenement in run["logs"]["realtime_feedback_events"]:
        if evenement["type"] == "mark-latency-breakdown" and evenement["turn"] == 3:
            for ttfb in evenement["payload"]["ttfb"]:
                if "LLMService" in ttfb["processor"]:
                    ttfb["duration_secs"] += 0.001
                    break
    assert _resume(mesurer_run(run)) != attendu


def test_les_dates_se_lisent_comme_date_parse():
    """Le corpus n'a que des horodatages à la milliseconde : la troncature des microsecondes
    (``Date.parse``) n'y est pas exercée, d'où ce test (une mutation qui la retirait restait verte)."""
    from api.services.analyse_run.mesures import _ms

    assert _ms("2026-10-02T15:30:35.729364Z") == _ms("2026-10-02T15:30:35.729+00:00")
    assert _ms("2026-10-02T15:30:35.729999+00:00") % 1000 == 729
    assert math.isnan(_ms(None))
    assert math.isnan(_ms("pas une date"))
    assert math.isnan(_ms("2026-10-02T15:30:35"))  # sans fuseau : on ne devine pas
