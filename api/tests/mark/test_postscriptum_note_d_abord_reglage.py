"""[.mark] Le Postscript, note d'abord : les réglages, par la vraie route et au clavier.

Plan `Labo-agent-vocal/plans/postscriptum-note-d-abord/`, lot 2 (Q1, Q2, Q2 bis, Q3).

| Test | Ce qu'il prouve |
|---|---|
| défauts | sans les clés : l'ordre d'avant, les indices allumés (Postscript seul) |
| route | « note d'abord » écrit en Postscript, refusé hors Postscript ; l'ordre d'avant accepté partout |
| clavier | une réponse « note, séparateur, phrase » : la phrase est dite, jamais la note ; la note est dans la fiche ; l'estampille dit l'ordre joué |
"""

import pytest

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.pipecat.post_scriptum import PRESENT, TRACE_POST_SCRIPTUM
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_INDICES_DES_MODULES,
    CLE_MODE,
    CLE_ORDRE_DE_LA_REPONSE,
    MODE_GREFFIER,
    MODE_OUTIL,
    MODE_POST_SCRIPTUM,
    ORDRE_NOTE_PUIS_PHRASE,
    ORDRE_PHRASE_PUIS_NOTE,
    ReglagesFiche,
)
from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _converser, _monter
from api.tests.mark.test_horaires_ouverture_reglage import _enregistrer
from api.tests.mark.test_mode_prise_de_notes_clavier import _dits_par_l_agent
from pipecat.tests import MockLLMService

POST_SCRIPTUM = {**FICHE, CLE_MODE: MODE_POST_SCRIPTUM}
NOTE_D_ABORD = {**POST_SCRIPTUM, CLE_ORDRE_DE_LA_REPONSE: ORDRE_NOTE_PUIS_PHRASE}


def test_les_defauts():
    assert WorkflowConfigurationDefaults().ordre_de_la_reponse is None
    assert WorkflowConfigurationDefaults().indices_des_modules is None
    reglages = ReglagesFiche.depuis(POST_SCRIPTUM)
    assert reglages.ordre == ORDRE_PHRASE_PUIS_NOTE
    assert reglages.indices_des_modules is True


def test_les_indices_eteints_et_hors_postscript():
    assert (
        ReglagesFiche.depuis(
            {**POST_SCRIPTUM, CLE_INDICES_DES_MODULES: False}
        ).indices_des_modules
        is False
    )
    assert (
        ReglagesFiche.depuis({**FICHE, CLE_MODE: MODE_OUTIL}).indices_des_modules
        is False
    )


def test_la_route_ecrit_la_note_d_abord_en_postscript():
    reponse, ecrit = _enregistrer({**NOTE_D_ABORD, CLE_INDICES_DES_MODULES: False})
    assert reponse.status_code == 200, reponse.text
    assert ecrit[CLE_ORDRE_DE_LA_REPONSE] == ORDRE_NOTE_PUIS_PHRASE
    assert ecrit[CLE_INDICES_DES_MODULES] is False


@pytest.mark.parametrize("mode", [MODE_OUTIL, MODE_GREFFIER, None])
def test_la_route_refuse_la_note_d_abord_hors_postscript(mode):
    configurations = {**FICHE, CLE_ORDRE_DE_LA_REPONSE: ORDRE_NOTE_PUIS_PHRASE}
    if mode is not None:
        configurations[CLE_MODE] = mode
    reponse, ecrit = _enregistrer(configurations)
    assert reponse.status_code == 422, reponse.text
    assert "Postscript" in reponse.text
    assert ecrit is None


def test_la_route_accepte_l_ordre_d_avant_dans_tout_mode():
    reponse, ecrit = _enregistrer(
        {**FICHE, CLE_MODE: MODE_OUTIL, CLE_ORDRE_DE_LA_REPONSE: ORDRE_PHRASE_PUIS_NOTE}
    )
    assert reponse.status_code == 200, reponse.text


@pytest.mark.asyncio
async def test_au_clavier_la_note_d_abord_n_est_jamais_dite(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, NOTE_D_ABORD)
    charge, run_id = await _converser(
        test_client_factory,
        user,
        workflow,
        [
            MockLLMService.create_text_chunks(
                '{"nom": "Lemaire"}\n|||\nTrès bien, et votre numéro ?'
            )
        ],
        "je m'appelle Lemaire",
    )
    dits = _dits_par_l_agent(charge)
    assert any("votre numéro" in d for d in dits), charge
    for dit in dits:
        assert "|||" not in dit and "{" not in dit and '"nom"' not in dit, dit
    fiche = charge["checkpoint"]["gathered_context"]
    assert fiche.get("nom") == "Lemaire", fiche
    assert [t["etat"] for t in fiche.get(TRACE_POST_SCRIPTUM) or []] == [PRESENT]
    run = await db_session.get_workflow_run_by_id(run_id)
    estampille = run.initial_context["runtime_configuration"]
    assert estampille[CLE_ORDRE_DE_LA_REPONSE] == ORDRE_NOTE_PUIS_PHRASE
    assert estampille[CLE_INDICES_DES_MODULES] is True
