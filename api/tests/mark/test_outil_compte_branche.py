"""[.mark] K5 (E77): the connected account an integration tool follows.

An organization may connect two accounts of one software (two Google calendars). The tool window of the screen lets a person
choose the account; the choice must survive the definition's validation (``IntegrationToolConfig``) and reach the execution
(``execution.executer`` reads ``config["compte"]``), otherwise the tool silently follows another account.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.schemas.tool import IntegrationToolDefinition


def _definition(**config):
    return {"schema_version": 1, "type": "integration", "config": {"connecteur": "hubspot", "action": "find_contact", **config}}


def test_le_compte_choisi_traverse_la_validation_de_la_definition():
    definition = IntegrationToolDefinition.model_validate(_definition(compte="CRM des commerciaux"))
    assert definition.config.compte == "CRM des commerciaux"
    assert definition.model_dump()["config"]["compte"] == "CRM des commerciaux"


def test_sans_compte_l_outil_suit_le_compte_unique_de_l_organisation():
    definition = IntegrationToolDefinition.model_validate(_definition())
    assert definition.config.compte is None


def test_un_nom_de_compte_trop_long_est_refuse():
    with pytest.raises(ValidationError):
        IntegrationToolDefinition.model_validate(_definition(compte="x" * 256))
