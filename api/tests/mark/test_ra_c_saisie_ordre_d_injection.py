"""[.mark] RA-C, sous-lot 2 : la saisie visible de l'ordre d'injection (``pre_call_fetch_remplace``).

RA-B avait caché le réglage du formulaire : un champ visible déplace la spec servie, le SDK typé et le JSON des specs. Ici le champ
est visible dans la section « avant » de l'étape de départ (après l'authentification, seulement quand la lecture avant l'appel est
allumée), et la spec servie, le SDK Python, le SDK TypeScript et la fixture de l'écran le portent tous (``test_sdk_sync`` et le miroir
de ``test_porte_parlee_premiere_replique`` gardent l'accord).
"""

from __future__ import annotations

from pathlib import Path

from api.services.workflow.dto import ReactFlowDTO, sanitize_workflow_definition
from api.services.workflow.node_specs import all_specs
from api.services.workflow.ordre_d_injection import noms_demandes

CHAMP = "pre_call_fetch_remplace"
RACINE = Path(__file__).resolve().parents[3]


def _depart():
    return next(s for s in all_specs() if s.name == "startCall")


def test_le_champ_est_dans_la_spec_servie_apres_l_authentification_de_la_lecture():
    ordre = [p.name for p in _depart().properties]
    assert CHAMP in ordre
    assert ordre.index(CHAMP) == ordre.index("pre_call_fetch_credential_uuid") + 1


def test_le_champ_ne_se_montre_que_si_la_lecture_avant_l_appel_est_allumee():
    champ = next(p for p in _depart().properties if p.name == CHAMP)
    assert champ.type.value == "string"
    assert champ.display_options is not None
    assert champ.display_options.show == {"pre_call_fetch_mode": ["always", "inbound", "outbound"]}
    assert champ.description and "name" in champ.description.lower()  # dit qu'on liste des noms


def test_le_champ_n_existe_que_sur_l_etape_de_depart():
    for spec in all_specs():
        if spec.name != "startCall":
            assert CHAMP not in [p.name for p in spec.properties], spec.name


def test_le_champ_survit_a_l_enregistrement_et_se_lit_comme_avant():
    definition = {
        "nodes": [{"id": "start", "type": "startCall", "position": {"x": 0, "y": 0}, "data": {"name": "Accueil", "prompt": "p", CHAMP: "marques, horaires"}}],
        "edges": [],
    }
    propre = sanitize_workflow_definition(definition)
    assert propre["nodes"][0]["data"][CHAMP] == "marques, horaires"
    noeud = ReactFlowDTO.model_validate(propre).nodes[0]
    assert noms_demandes(noeud.data.pre_call_fetch_remplace) == {"marques", "horaires"}


def test_les_deux_sdk_portent_le_champ():
    assert f"{CHAMP}: Optional[str] = None" in (RACINE / "sdk/python/src/dograh_sdk/typed/start_call.py").read_text(encoding="utf-8")
    assert f"{CHAMP}?: string;" in (RACINE / "sdk/typescript/src/typed/start-call.ts").read_text(encoding="utf-8")
