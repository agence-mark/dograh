"""[.mark] Lot 11 bis, T2 : les mesures par tour dans la fiche d'appel (``mark.appel.mesures.par_tour``).

| Test | Ce qu'il prouve |
|---|---|
| lecture | un tour porte ses phases, l'agrégation du texte et les fonctions appelées avec leur durée ; une valeur absente n'est jamais écrite à zéro |
| envoi | l'envoi de fin d'appel verse ``par_tour`` à côté de ``analyse_version`` ; sans mesure, la clé n'existe pas |
"""

from __future__ import annotations

from types import SimpleNamespace

from api.schemas.apres_appel import ApresAppelAgent
from api.services.analyse_run.latence_par_phase import detail_du_tour, latence_des_tours
from api.services.apres_appel.envoi import construire_envoi, mesures_par_tour

EVENEMENT = {
    "type": "mark-latency-breakdown",
    "turn": 2,
    "node_name": "Accueil",
    "payload": {
        "ttfb": [{"processor": "OpenAILLMService#0", "duration_secs": 0.4}],
        "text_aggregation": {"start_time": 1.0, "duration_secs": 0.15},
        "function_calls": [{"function_name": "ajouter", "start_time": 1.0, "duration_secs": 0.3}, {"function_name": "", "duration_secs": 1}],
    },
}


def test_un_tour_porte_agregation_et_fonctions_sans_zero_invente():
    d = detail_du_tour(EVENEMENT["payload"])
    assert d == {"agregation_ms": 150.0, "fonctions": [{"nom": "ajouter", "duree_ms": 300.0}]}
    assert detail_du_tour({"text_aggregation": None, "function_calls": []}) == {}
    assert detail_du_tour({"text_aggregation": {"duration_secs": -1}}) == {}
    tours = latence_des_tours([EVENEMENT, {"type": "autre"}])
    assert tours[0]["agregation_ms"] == 150.0 and tours[0]["fonctions"][0]["nom"] == "ajouter" and "modele" in tours[0]["phases"]


def test_l_envoi_verse_les_mesures_par_tour_et_se_tait_sans_mesure():
    run = SimpleNamespace(
        initial_context={}, gathered_context={}, logs={"realtime_feedback_events": [EVENEMENT]}, usage_info={}, cost_info={},
        created_at=None, id=1, workflow_id=1, definition=None, definition_id=1, mode="twilio", annotations={}, call_type=None, name="x",
    )
    envoi = construire_envoi(run, {}, ApresAppelAgent())
    assert envoi["mesures"]["par_tour"][0]["tour"] == 2 and "analyse_version" in envoi["mesures"]
    run.logs = {}
    assert "par_tour" not in construire_envoi(run, {}, ApresAppelAgent())["mesures"]
    assert mesures_par_tour(SimpleNamespace(logs=None)) == []
    assert mesures_par_tour(object()) == []
