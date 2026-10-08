"""[.mark] Le réglage « mode de prise de notes » : données seules (plan mode-prise-de-notes, lot 1).

Plan `Labo-agent-vocal/plans/mode-prise-de-notes/`, D1 : un menu à trois valeurs par agent,
outil (défaut, le comportement d'avant), post-scriptum, greffier (partie 2, livrée sur la
branche `chantier/mode-prise-de-notes-2`). L'estampille du run dit le mode JOUÉ.

| Test | Ce qu'il prouve |
|---|---|
| défaut | un agent sans le réglage est en mode outil, au schéma comme à l'appel |
| route | le post-scriptum et le greffier s'enregistrent ; une valeur inconnue est refusée (422) sans rien écrire |
| lecture | une configuration écrite à la main avec une valeur injouable est lue « outil », jamais un appel perdu |
| estampille | le clavier, par ses vraies routes, écrit le mode joué dans `runtime_configuration` ; fiche éteinte : rien |
| deux chemins | le téléphone et le clavier appellent tous deux l'estampille |
"""

import inspect

import pytest
from pydantic import ValidationError

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_INDICES_DES_MODULES,
    CLE_MODE,
    CLE_ORDRE_DE_LA_REPONSE,
    MODE_GREFFIER,
    MODE_OUTIL,
    MODE_POST_SCRIPTUM,
    ORDRE_PHRASE_PUIS_NOTE,
    ReglagesFiche,
    estampiller_le_mode,
)
from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _converser, _monter
from api.tests.mark.test_horaires_ouverture_reglage import _enregistrer
from pipecat.tests import MockLLMService

# --------------------------------------------------------------------------- #
# 1. Le défaut
# --------------------------------------------------------------------------- #


def test_le_defaut_est_l_outil():
    assert WorkflowConfigurationDefaults().fiche_mode_de_note == MODE_OUTIL


def test_une_configuration_sans_la_cle_est_lue_outil():
    reglages = ReglagesFiche.depuis(FICHE)
    assert reglages is not None
    assert reglages.mode == MODE_OUTIL


def test_le_post_scriptum_est_lu():
    reglages = ReglagesFiche.depuis({**FICHE, CLE_MODE: MODE_POST_SCRIPTUM})
    assert reglages.mode == MODE_POST_SCRIPTUM


# --------------------------------------------------------------------------- #
# 2. L'enregistrement, par la vraie route
# --------------------------------------------------------------------------- #


def test_la_route_ecrit_le_post_scriptum():
    reponse, ecrit = _enregistrer({**FICHE, CLE_MODE: MODE_POST_SCRIPTUM})
    assert reponse.status_code == 200, reponse.text
    assert ecrit[CLE_MODE] == MODE_POST_SCRIPTUM


def test_la_route_ecrit_le_greffier():
    reponse, ecrit = _enregistrer({**FICHE, CLE_MODE: MODE_GREFFIER})
    assert reponse.status_code == 200, reponse.text
    assert ecrit[CLE_MODE] == MODE_GREFFIER


@pytest.mark.parametrize("refuse", ["clerk", "", "OUTIL"])
def test_la_route_refuse_un_mode_inconnu_et_n_ecrit_rien(refuse):
    reponse, ecrit = _enregistrer({**FICHE, CLE_MODE: refuse})
    assert reponse.status_code == 422, reponse.text
    assert ecrit is None


def test_une_valeur_inconnue_est_refusee_au_schema():
    with pytest.raises(ValidationError):
        WorkflowConfigurationDefaults(fiche_mode_de_note="clerk")


# --------------------------------------------------------------------------- #
# 3. À l'appel, une valeur injouable ne coûte rien
# --------------------------------------------------------------------------- #


def test_le_greffier_est_lu():
    reglages = ReglagesFiche.depuis({**FICHE, CLE_MODE: MODE_GREFFIER})
    assert reglages.mode == MODE_GREFFIER


@pytest.mark.parametrize("injouable", ["clerk", "n_importe_quoi", 3])
def test_une_valeur_injouable_ecrite_a_la_main_est_lue_outil(injouable):
    reglages = ReglagesFiche.depuis({**FICHE, CLE_MODE: injouable})
    assert reglages is not None
    assert reglages.mode == MODE_OUTIL


# --------------------------------------------------------------------------- #
# 4. L'estampille
# --------------------------------------------------------------------------- #


def test_l_estampille_dit_le_mode_joue():
    reglages = ReglagesFiche.depuis({**FICHE, CLE_MODE: MODE_POST_SCRIPTUM})
    assert estampiller_le_mode({}, reglages) == {
        CLE_MODE: MODE_POST_SCRIPTUM,
        # Plan postscriptum-note-d-abord : l'ordre et les indices joués en Postscript.
        CLE_ORDRE_DE_LA_REPONSE: ORDRE_PHRASE_PUIS_NOTE,
        CLE_INDICES_DES_MODULES: True,
    }


def test_fiche_eteinte_aucun_mode_n_est_estampille():
    assert estampiller_le_mode({"llm_model": "x"}, None) == {"llm_model": "x"}


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [MODE_OUTIL, MODE_POST_SCRIPTUM])
async def test_le_clavier_estampille_le_mode_joue(
    mode, db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, {**FICHE, CLE_MODE: mode})
    _, run_id = await _converser(
        test_client_factory,
        user,
        workflow,
        [MockLLMService.create_text_chunks("Bien noté.")],
        "bonjour",
    )
    run = await db_session.get_workflow_run_by_id(run_id)
    assert run.initial_context["runtime_configuration"][CLE_MODE] == mode


@pytest.mark.asyncio
async def test_le_clavier_fiche_eteinte_n_estampille_aucun_mode(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(
        db_session, async_session, {"fiche_au_fil_de_leau": False}
    )
    _, run_id = await _converser(
        test_client_factory,
        user,
        workflow,
        [MockLLMService.create_text_chunks("Bonjour.")],
        "bonjour",
    )
    run = await db_session.get_workflow_run_by_id(run_id)
    assert CLE_MODE not in run.initial_context["runtime_configuration"]


def test_les_deux_chemins_estampillent_le_mode():
    """Le téléphone n'a pas de route de test bon marché : on vérifie qu'il appelle
    l'estampille sur les réglages qu'il donne au moteur (patron de
    ``test_configuration_estampillee_sur_lappel``)."""
    from api.services.pipecat import run_pipeline
    from api.services.workflow import text_chat_runner

    for module in (run_pipeline, text_chat_runner):
        source = inspect.getsource(module)
        assert "estampiller_le_mode(" in source, module.__name__
        assert "fiche=reglages_fiche" in source, module.__name__
