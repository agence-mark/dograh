"""[.mark] RA-B, R4 (d) : l'ordre d'injection est écrit, et la lecture avant l'appel ne remplace un objet que si on le demande."""

from api.services.workflow.initial_context import merge_external_initial_context
from api.services.workflow.ordre_d_injection import (
    CLE_TRACE,
    ORDRE_D_INJECTION,
    fusionner_la_lecture,
    noms_demandes,
)


def _contexte():
    return {
        "tarif": "Tarif de l'organisation",
        "prenom_client": "",
        "runtime_configuration": {"objets": {"etat": "lu", "poses": ["tarif"]}},
    }


def test_avant_le_correctif_la_fusion_de_l_amont_ecrase_un_objet():
    # Le comportement d'avant (event_handlers) : preuve que la lecture écrasait l'objet, sans trace.
    fusionne = merge_external_initial_context(_contexte(), {"tarif": "Valeur du CRM"})
    assert fusionne["tarif"] == "Valeur du CRM"
    assert "lecture_avant_l_appel" not in fusionne["runtime_configuration"]


def test_la_lecture_ne_remplace_pas_un_objet_non_demande_et_le_dit():
    fusionne, trace = fusionner_la_lecture(_contexte(), {"tarif": "Valeur du CRM", "prenom_client": "Léa"})
    assert fusionne["tarif"] == "Tarif de l'organisation"
    assert fusionne["prenom_client"] == "Léa"
    assert trace == [{"cle": "tarif", "couche": "objets", "decision": "refusee"}]
    assert fusionne["runtime_configuration"][CLE_TRACE] == trace
    assert "Valeur du CRM" not in str(trace)  # jamais la valeur dans la trace


def test_la_lecture_remplace_un_objet_quand_l_etape_le_demande_et_la_trace_le_garde():
    fusionne, trace = fusionner_la_lecture(_contexte(), {"tarif": "Valeur du CRM"}, noms_demandes(" tarif , autre"))
    assert fusionne["tarif"] == "Valeur du CRM"
    assert trace == [{"cle": "tarif", "couche": "objets", "decision": "remplacee"}]


def test_les_cles_du_run_restent_refusees_et_l_estampille_survit():
    fusionne, _ = fusionner_la_lecture(_contexte(), {"runtime_configuration": {"objets": None}, "workflow_run_id": 9})
    assert fusionne["runtime_configuration"]["objets"]["poses"] == ["tarif"]
    assert "workflow_run_id" not in fusionne


def test_sans_objet_la_lecture_passe_comme_avant():
    fusionne, trace = fusionner_la_lecture({"a": 1}, {"b": 2})
    assert fusionne == {"a": 1, "b": 2} and trace == []


def test_l_ordre_est_ecrit_du_plus_bas_au_plus_haut():
    assert [i for i, _, _ in ORDRE_D_INJECTION] == [
        "defaut", "organisation", "etablissement", "objets", "lecture", "appel",
    ]


def test_le_reglage_de_l_etape_de_depart_existe_et_se_saisit_dans_le_formulaire():
    """RA-C : il était caché du formulaire (RA-B) ; il est visible, donc plus dans les champs cachés repris à l'enregistrement."""
    from api.services.workflow.champs_caches import champs_caches
    from api.services.workflow.dto import StartCallNodeData

    assert "pre_call_fetch_remplace" in StartCallNodeData.model_fields
    assert "pre_call_fetch_remplace" not in champs_caches("startCall")
