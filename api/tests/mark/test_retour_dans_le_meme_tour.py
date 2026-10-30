"""agent-facon-tala, C3 : un retour au premier agent dans le tour même de la passation (le collègue
rend la main en ouvrant) ne rejoue jamais le cerveau déjà utilisé : il était arrêté avec le circuit du
premier passage, et le départ du circuit suivant ne sortait jamais (tour bloqué 25 s, erreur 500)."""

import re
from pathlib import Path

from api.services.workflow.text_chat_runner import _AgentDuTour, agent_a_cerveaux_neufs


class _Cerveau:
    def __init__(self, **options):
        self.options = options


def _premier() -> _AgentDuTour:
    cerveau = _Cerveau(prompt_cache_key="mark-wf-6")
    return _AgentDuTour(
        workflow_id=6,
        definition_id=12,
        nom="accueil",
        graphe=object(),
        llm=cerveau,
        inference_llm=cerveau,
        variable_extraction_llm=cerveau,
        reglages={"a": 1},
        visit_id="v1",
    )


def test_cerveaux_neufs_meme_agent():
    avant = _premier()
    apres = agent_a_cerveaux_neufs(
        avant, lambda **o: _Cerveau(**o), "mark-wf-6", avec_extraction=False
    )
    assert apres is not avant
    assert apres.llm is not avant.llm
    assert apres.llm.options == {"prompt_cache_key": "mark-wf-6"}
    assert apres.inference_llm is apres.llm and apres.variable_extraction_llm is apres.llm
    # Le reste est celui du premier agent : graphe, réglages, visite, définition.
    assert apres.graphe is avant.graphe
    assert apres.reglages == avant.reglages
    assert (apres.workflow_id, apres.definition_id, apres.visit_id) == (6, 12, "v1")
    # L'ancien agent n'est pas touché (le passage 1 garde son cerveau).
    assert avant.llm.options == {"prompt_cache_key": "mark-wf-6"}


def test_cerveau_d_extraction_a_part_quand_il_faut():
    apres = agent_a_cerveaux_neufs(
        _premier(), lambda **o: _Cerveau(**o), "mark-wf-6", avec_extraction=True
    )
    assert apres.variable_extraction_llm is not apres.llm
    assert apres.variable_extraction_llm.options == {"usage_context": "variable_extraction"}


def test_le_retour_du_clavier_passe_par_les_cerveaux_neufs():
    """Le chemin réel : ``charger_agent`` ne rend le premier agent tel quel que s'il n'a pas joué."""
    source = (Path(__file__).parents[2] / "services/workflow/text_chat_runner.py").read_text(
        encoding="utf-8"
    )
    assert re.search(r"if id\(premier_agent\) not in agents_joues:\s+return premier_agent", source)
    assert "return _premier_agent_a_neuf()" in source
    assert "agents_joues.add(id(agent_du_tour))" in source


# --------------------------------------------------------------------------- #
# Le chemin réel du clavier : vraies routes HTTP, modèles écrits d'avance
# --------------------------------------------------------------------------- #

import asyncio

import pytest

from api.tests.mark.test_passation_clavier import (
    _appel,
    _checkpoint,
    _dit,
    _groupe,
    _session,
    _texte,
    _vide,
)


@pytest.mark.asyncio
async def test_le_collegue_rend_la_main_en_ouvrant_et_l_accueil_repond_dans_le_meme_tour(
    db_session, async_session, test_client_factory
):
    """C3 (run local 174) : accueil -> collègue, et le collègue prend la porte de retour SANS rien dire à
    sa première ouverture. Avant : l'accueil reprenait le cerveau du premier passage (arrêté), le circuit ne
    démarrait pas, le tour restait bloqué puis le message revenait en erreur 500. Maintenant : le tour
    finit et l'accueil répond à la personne dans le même tour."""
    user, principal, _specialise = await _groupe(db_session, async_session)
    reponses = await asyncio.wait_for(
        _session(
            test_client_factory,
            user,
            principal,
            [
                _vide(),  # accueil (texte fixe)
                _dit([*_appel("passer_a_s", "p1")]),  # passage 1 : l'accueil passe la main
                _vide(),  # la fabrique construit le collègue
                _dit([*_appel("retour", "r1")]),  # passage 2 : le collègue rend la main, muet
                _vide(),  # la fabrique construit le principal (retour)
                _dit(_texte("Je vous écoute, dites-moi.")),  # passage 3 : l'accueil, cerveau neuf
            ],
            ["je veux parler à quelqu'un"],
        ),
        timeout=40,
    )
    tour = reponses[0]
    assert "Je vous écoute, dites-moi." in str(tour), tour
    point = _checkpoint(tour)
    assert "agent_actif" not in point, point  # l'accueil a la main
    assert point["current_node_id"] == "p_start", point
    passations = point["gathered_context"].get("passations") or []
    assert [e.get("raison") for e in passations] == ["Passer a S", "retour"], passations
