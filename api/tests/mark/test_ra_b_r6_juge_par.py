"""[.mark] RA-B, R6 : « Jugé par [modèle] » en colonne de la liste des appels (05 § 9)."""

import pytest

from api.db.appels_liste import juge_par
from api.db.organization_usage_client import OrganizationUsageClient  # noqa: F401 -- la liste s'appuie sur ce client
from api.routes.organization_usage import WorkflowRunUsageResponse


def test_juge_par_lit_le_modele_ou_claude_code_dans_l_annotation_du_juge():
    assert juge_par({"juge": {"etat": "juge", "source": "cle_api", "modele": "openai/gpt-x"}}) == "openai/gpt-x"
    assert juge_par({"juge": {"etat": "a_juger", "source": "claude_code"}}) == "Claude Code"
    assert juge_par({"juge": {"etat": "juge", "source": "claude_code", "modele": "ignoré"}}) == "Claude Code"


@pytest.mark.parametrize("annotations", [None, {}, {"juge": None}, {"juge": {"etat": "non_regle"}}, {"juge": "x"}, {"juge": {"modele": 3}}])
def test_juge_par_est_vide_quand_rien_n_a_juge(annotations):
    assert juge_par(annotations) is None


def test_la_ligne_de_la_liste_porte_le_champ():
    assert "juge_par" in WorkflowRunUsageResponse.model_fields
