"""[.mark] Chaque essai dit QUEL code et QUELLE version de l'agent l'ont joué
(chantier langwatch-et-fenetre-du-run, lot 2, étape 1).

Question : un run porte-t-il, dans son estampille, la version de l'application, le commit déployé
et la définition jouée, sur les deux chemins (appel et clavier) ?

Le chemin du clavier est JOUÉ jusqu'au moteur (harnais de ``test_adresse_etablissement.py``) ; le
chemin de l'appel ne se joue pas dans une suite de tests (appel payant) : sa source est lue, avec
l'ordre qui compte (après le mode, avant l'enregistrement de l'estampille).
"""

import inspect
import re
from types import SimpleNamespace

import pytest

from api.constants import APP_VERSION
from api.services.analyse_run.captures import (
    CLE_VERSION,
    VARIABLE_DU_COMMIT,
    estampiller_la_version,
)
from api.services.organization_preferences import OrganizationPreferences
from api.services.pipecat import run_pipeline
from api.tests.mark.test_adresse_etablissement import _jouer_au_clavier


def test_la_version_est_estampillee(monkeypatch):
    monkeypatch.setenv(VARIABLE_DU_COMMIT, "c3ac9aa65c0e")
    definition = SimpleNamespace(
        id=144, version_number=10, status=SimpleNamespace(value="published")
    )
    estampille = estampiller_la_version({"llm_model": "x"}, definition)
    assert estampille["llm_model"] == "x"
    assert estampille[CLE_VERSION] == {
        "app_version": APP_VERSION,
        "commit": "c3ac9aa65c0e",
        "definition_id": 144,
        "version_number": 10,
        "definition_status": "published",
    }


def test_hors_de_railway_le_commit_est_dit_absent(monkeypatch):
    monkeypatch.delenv(VARIABLE_DU_COMMIT, raising=False)
    assert estampiller_la_version({}, None)[CLE_VERSION]["commit"] is None


def test_une_estampille_qui_echoue_n_emporte_pas_l_appel():
    class Casse(dict):
        def __setitem__(self, cle, valeur):
            raise RuntimeError("base indisponible")

    estampiller_la_version(Casse(), None)  # ne lève pas


@pytest.mark.asyncio
async def test_le_clavier_porte_la_version(monkeypatch):
    monkeypatch.setenv(VARIABLE_DU_COMMIT, "abc123")
    persiste = await _jouer_au_clavier(
        {}, {"direction": "inbound"}, OrganizationPreferences()
    )
    assert persiste["runtime_configuration"][CLE_VERSION]["commit"] == "abc123"
    assert persiste["runtime_configuration"][CLE_VERSION]["app_version"] == APP_VERSION


def test_l_appel_estampille_la_version_avant_d_enregistrer_l_estampille():
    source = inspect.getsource(run_pipeline)
    mode = source.index("estampiller_le_mode(runtime_configuration, reglages_fiche)")
    version = source.index(
        "estampiller_la_version(runtime_configuration, run_definition)"
    )
    persistance = re.search(
        r"update_workflow_run\(\s*workflow_run_id, initial_context=merged_call_context_vars",
        source,
    ).start()
    assert mode < version < persistance
    assert source.count("estampiller_la_version(") == 1
