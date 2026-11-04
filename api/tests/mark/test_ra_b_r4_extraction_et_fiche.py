"""[.mark] RA-B, R4 (b) : l'extraction ne remplace jamais une valeur vérifiée de la fiche (audit 02 B1, 🔴 3).

Vrai moteur (banc fendu) : la fiche est portée par l'agent principal ; ici l'agent actif est un agent qui NE porte PAS la
fiche (spécialiste, agent reçu par transfert), donc l'extraction de l'amont reste en place et ne doit pas écraser une
valeur sûre."""

from unittest.mock import AsyncMock

import pytest

from api.services.workflow.dto import ExtractionVariableDTO
from api.tests.mark.test_passages_fiables_fiche import graphe, monter

pytestmark = pytest.mark.asyncio


def _variable(nom):
    return ExtractionVariableDTO(name=nom, type="string", prompt=f"Extrais {nom}")


async def _extraire(engine, rendu: dict):
    noeud = engine.active_agent.current_node
    noeud.extraction_enabled = True
    noeud.extraction_prompt = "Extrais."
    noeud.extraction_variables = [_variable(n) for n in rendu]
    # L'agent actif ne porte pas la fiche : l'extraction de l'amont s'exécute.
    engine._llm_de_la_fiche = None
    engine._porte_la_fiche = lambda agent: False
    engine._variable_extraction_manager = AsyncMock()
    engine._variable_extraction_manager._perform_extraction.return_value = rendu
    return await engine._perform_variable_extraction_if_needed(noeud, run_in_background=False)


async def test_l_extraction_n_ecrase_pas_une_valeur_sure_de_la_fiche():
    fiche = {"nom": "Lemaire", "objet": "une demande", "fiche_etat": {"objet": {"sure": True}}}
    harness = await monter(graphe(), fiche=fiche)
    try:
        engine = harness.engine
        await _extraire(engine, {"objet": "valeur douteuse", "ville": "Paris"})
        assert engine._gathered_context["objet"] == "une demande"
        assert engine._gathered_context["ville"] == "Paris"  # hors fiche : l'extraction écrit
        assert "objet" not in engine._gathered_context.get("extracted_variables", {})
    finally:
        await harness.stop()


async def test_l_extraction_remplace_une_valeur_non_sure_ou_vide():
    fiche = {"nom": "Lemaire", "fiche_etat": {"nom": {"sure": False}}}
    harness = await monter(graphe(), fiche=fiche)
    try:
        engine = harness.engine
        await _extraire(engine, {"nom": "Lemaire bis", "objet": "ma demande"})
        assert engine._gathered_context["nom"] == "Lemaire bis"
        assert engine._gathered_context["objet"] == "ma demande"
    finally:
        await harness.stop()
