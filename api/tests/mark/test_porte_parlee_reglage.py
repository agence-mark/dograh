"""[.mark] Le réglage « porte dans la réponse » : données seules (plan porte-parlee, lot 1).

Plan `Labo-agent-vocal/plans/porte-parlee/`, D1 : une case par agent, éteinte par défaut, qui
n'existe qu'en mode Postscript. L'estampille du run ne la porte que jouée.

| Test | Ce qu'il prouve |
|---|---|
| défaut | un agent sans le réglage l'a éteint, au schéma comme à l'appel |
| route | allumée en Postscript : enregistrée ; allumée dans un autre mode : refusée (422) sans rien écrire |
| lecture | écrite à la main hors Postscript, ou avec autre chose que ``true`` : éteinte, jamais un appel perdu |
| estampille | le clavier, par ses vraies routes, l'écrit allumée ; éteinte : la clé n'apparaît pas (estampille d'avant à l'identique) |
"""

import pytest

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_MODE,
    CLE_PORTES_DANS_LA_REPONSE,
    MODE_GREFFIER,
    MODE_OUTIL,
    MODE_POST_SCRIPTUM,
    ReglagesFiche,
    estampiller_le_mode,
)
from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _converser, _monter
from api.tests.mark.test_horaires_ouverture_reglage import _enregistrer
from pipecat.tests import MockLLMService

POST_SCRIPTUM = {**FICHE, CLE_MODE: MODE_POST_SCRIPTUM}
ALLUMEE = {**POST_SCRIPTUM, CLE_PORTES_DANS_LA_REPONSE: True}

# --------------------------------------------------------------------------- #
# 1. Le défaut
# --------------------------------------------------------------------------- #


def test_le_defaut_est_eteint():
    assert WorkflowConfigurationDefaults().portes_dans_la_reponse is False


def test_une_configuration_sans_la_cle_est_lue_eteinte():
    assert ReglagesFiche.depuis(POST_SCRIPTUM).portes_dans_la_reponse is False


def test_allumee_en_post_scriptum_est_lue():
    assert ReglagesFiche.depuis(ALLUMEE).portes_dans_la_reponse is True


# --------------------------------------------------------------------------- #
# 2. L'enregistrement, par la vraie route
# --------------------------------------------------------------------------- #


def test_la_route_ecrit_la_case_en_post_scriptum():
    reponse, ecrit = _enregistrer(ALLUMEE)
    assert reponse.status_code == 200, reponse.text
    assert ecrit[CLE_PORTES_DANS_LA_REPONSE] is True


@pytest.mark.parametrize("mode", [MODE_OUTIL, MODE_GREFFIER, None])
def test_la_route_refuse_la_case_hors_post_scriptum(mode):
    configurations = {**FICHE, CLE_PORTES_DANS_LA_REPONSE: True}
    if mode is not None:
        configurations[CLE_MODE] = mode
    reponse, ecrit = _enregistrer(configurations)
    assert reponse.status_code == 422, reponse.text
    assert "Postscript" in reponse.text
    assert ecrit is None


def test_la_route_accepte_la_case_eteinte_dans_tout_mode():
    reponse, ecrit = _enregistrer(
        {**FICHE, CLE_MODE: MODE_OUTIL, CLE_PORTES_DANS_LA_REPONSE: False}
    )
    assert reponse.status_code == 200, reponse.text
    assert ecrit[CLE_PORTES_DANS_LA_REPONSE] is False


# --------------------------------------------------------------------------- #
# 3. À l'appel, une valeur écrite à la main ne coûte rien
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mode", [MODE_OUTIL, MODE_GREFFIER, "inconnu"])
def test_ecrite_a_la_main_hors_post_scriptum_est_eteinte(mode):
    reglages = ReglagesFiche.depuis(
        {**FICHE, CLE_MODE: mode, CLE_PORTES_DANS_LA_REPONSE: True}
    )
    assert reglages is not None
    assert reglages.portes_dans_la_reponse is False


@pytest.mark.parametrize("valeur", ["true", 1, "oui", None])
def test_autre_chose_que_true_est_eteinte(valeur):
    reglages = ReglagesFiche.depuis(
        {**POST_SCRIPTUM, CLE_PORTES_DANS_LA_REPONSE: valeur}
    )
    assert reglages.portes_dans_la_reponse is False


# --------------------------------------------------------------------------- #
# 4. L'estampille
# --------------------------------------------------------------------------- #


def test_l_estampille_porte_la_case_jouee():
    assert estampiller_le_mode({}, ReglagesFiche.depuis(ALLUMEE)) == {
        CLE_MODE: MODE_POST_SCRIPTUM,
        CLE_PORTES_DANS_LA_REPONSE: True,
    }


def test_eteinte_l_estampille_est_celle_d_avant():
    assert estampiller_le_mode({}, ReglagesFiche.depuis(POST_SCRIPTUM)) == {
        CLE_MODE: MODE_POST_SCRIPTUM
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("configurations", [ALLUMEE, POST_SCRIPTUM])
async def test_le_clavier_estampille_la_case(
    configurations, db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, configurations)
    _, run_id = await _converser(
        test_client_factory,
        user,
        workflow,
        [MockLLMService.create_text_chunks("Bien noté. ||| {}")],
        "bonjour",
    )
    run = await db_session.get_workflow_run_by_id(run_id)
    estampille = run.initial_context["runtime_configuration"]
    if configurations is ALLUMEE:
        assert estampille[CLE_PORTES_DANS_LA_REPONSE] is True
    else:
        assert CLE_PORTES_DANS_LA_REPONSE not in estampille
