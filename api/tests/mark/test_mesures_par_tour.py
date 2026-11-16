"""[.mark] Lot 11 bis, T2 : les mesures par tour dans la fiche d'appel (``mark.appel.mesures.par_tour``).

| Test | Ce qu'il prouve |
|---|---|
| lecture | un tour porte ses phases, l'agrégation du texte et les fonctions appelées avec leur durée ; une valeur absente n'est jamais écrite à zéro |
| T3 fiche de fin | la fiche structurée d office (titre, résumé, sujet, priorité, rappel nécessaire, action suivante, numéro de rappel, faits clés) est rangée dans les mesures ; rien de noté : aucun rappel, jamais un texte inventé |
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


# --- T3 : la fiche de fin d'appel structurée d'office --------------------------------------------------------------------------


def test_t3_la_fiche_de_fin_est_structuree_d_office_et_ne_dit_que_ce_qui_a_ete_note():
    from api.services.apres_appel.envoi import fiche_de_fin

    envoi = {
        "motif": "devis cuisine", "numero_appelant": "+33612345678",
        "demande": {"type": "rappel", "sujet": "devis", "priorite": 1},
        "champs": [{"nom": "nom", "valeur": "Dupont"}, {"nom": "telephone", "valeur": " +33700000000 "}, {"nom": "vide", "valeur": "  "}],
    }
    f = fiche_de_fin(envoi)
    assert f == {
        "titre": "devis cuisine", "resume": None, "sujet": "devis", "priorite": "urgente", "rappel_necessaire": True,
        "action_suivante": "rappeler", "numero_de_rappel": "+33700000000",
        "faits_cles": [{"nom": "nom", "valeur": "Dupont"}, {"nom": "telephone", "valeur": "+33700000000"}],
    }
    # Rien de noté : aucun rappel, aucun numéro, jamais un texte inventé.
    vide = fiche_de_fin({"motif": None, "numero_appelant": "+33612345678", "demande": None, "champs": []})
    assert vide["rappel_necessaire"] is False and vide["action_suivante"] == "aucune" and vide["numero_de_rappel"] is None
    assert vide["titre"] is None and vide["priorite"] is None and vide["faits_cles"] == []
    # Une panne qui a perdu l'appel : rappel même sans rien noté, au numéro qui a appelé.
    panne = fiche_de_fin({"numero_appelant": "+33612345678", "panne": {"a_rappeler": True}, "champs": []})
    assert panne["rappel_necessaire"] is True and panne["numero_de_rappel"] == "+33612345678"
    assert len(fiche_de_fin({"champs": [{"nom": f"c{i}", "valeur": "x"} for i in range(40)]})["faits_cles"]) == 12


def test_t3_l_envoi_porte_la_fiche_de_fin_dans_les_mesures():
    run = SimpleNamespace(
        initial_context={}, gathered_context={}, logs={}, usage_info={}, cost_info={}, created_at=None, id=1, workflow_id=1,
        definition=None, definition_id=1, mode="twilio", annotations={}, call_type=None, name="x",
    )
    fiche = construire_envoi(run, {}, ApresAppelAgent())["mesures"]["fiche_de_fin"]
    assert set(fiche) == {"titre", "resume", "sujet", "priorite", "rappel_necessaire", "action_suivante", "numero_de_rappel", "faits_cles"}


def test_m24_la_fiche_de_fin_se_lit_sur_le_run_pour_l_ecran_de_l_appel():
    from api.services.apres_appel.envoi import fiche_de_fin_du_run

    definition = SimpleNamespace(workflow_configurations={})
    run = SimpleNamespace(
        initial_context={}, gathered_context={}, logs={}, usage_info={}, cost_info={}, created_at=None, id=1, workflow_id=1,
        definition=definition, definition_id=1, mode="twilio", annotations={}, call_type=None, name="x",
    )
    fiche = fiche_de_fin_du_run(run, {})
    assert fiche is not None and set(fiche) == {"titre", "resume", "sujet", "priorite", "rappel_necessaire", "action_suivante", "numero_de_rappel", "faits_cles"}
    assert fiche["resume"] is None  # le résumé vient de l'étape « synthèse », jamais inventé à la lecture
    # Sans définition, ou un run illisible : rien (l'écran dit « non disponible »), jamais une fiche inventée ni une erreur.
    run.definition = None
    assert fiche_de_fin_du_run(run, {}) is None
    assert fiche_de_fin_du_run(SimpleNamespace(definition=definition), {}) is None
