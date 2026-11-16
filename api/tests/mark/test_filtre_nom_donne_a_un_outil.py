"""[.mark] SA-33, défaut 5 (appel 2559) : le prénom donné à un outil dans le tour en cours n'est jamais redit.

Constat : « Merci Paul, quel est votre numéro ? » alors que ``interdire_nom_appelant`` est allumé. Le filtre couvre le prénom de la fiche
(``_prenom_de_lappelant``), mais « Paul » est dit AVANT que le greffier écrive ``prenom`` dans la fiche (écriture asynchrone, après le tour).
Le prénom (et le nom) passés en argument d'un outil dans le tour en cours (``finaliser`` avec ``{"prenom": "Paul"}``) partent aussi.

| Test | Ce qu'il prouve |
|---|---|
| tour en cours | le prénom passé à un outil dans ce tour part, fiche encore vide (la vraie chaîne, coupé en morceaux) |
| nom aussi | le nom passé à un outil part de même |
| autre tour | un argument d'un tour d'avant n'est pas lu (le filtre ne lit que le tour en cours ; la fiche prend le relais) |
| case éteinte | rien ne part : le comportement d'avant |
| tour noté | le moteur note le tour de la personne sur chaque résultat d'outil gardé |
"""

import pytest

from api.services.pipecat.filtre_nom_civilite import FiltreNomCiviliteProcessor
from api.services.workflow.fiche_au_fil_de_leau import CLE_TOUR
from api.tests.mark.test_agent_facon_tala_lot_4_prenom import _jouer


def _filtre(contexte: dict, retirer_nom: bool = True):
    return FiltreNomCiviliteProcessor(
        retirer_nom=retirer_nom,
        retirer_civilite=False,
        variables=lambda: {},
        contexte=lambda: contexte,
        mode_envoi="sentence",
    )


def _contexte(arguments: dict, tour_de_l_outil: int = 5, tour: int = 5) -> dict:
    return {
        CLE_TOUR: tour,
        "tool_results": [{"function_name": "finaliser", "arguments": arguments, "status": "completed", "result": {}, "tour": tour_de_l_outil}],
    }


@pytest.mark.asyncio
async def test_le_prenom_donne_a_un_outil_dans_ce_tour_n_est_pas_redit():
    sortie = await _jouer(_filtre(_contexte({"prenom": "Paul"})), ["Merci Pa", "ul, quel est", " votre numéro ?"])
    assert "Paul" not in sortie
    assert sortie.strip() == "Merci, quel est votre numéro ?" or sortie.strip() == "Merci quel est votre numéro ?", sortie


@pytest.mark.asyncio
async def test_le_nom_donne_a_un_outil_part_aussi():
    sortie = await _jouer(_filtre(_contexte({"nom": "Garnier", "personnes": 4})), ["C'est noté pour Garnier, à quelle heure ?"])
    assert "Garnier" not in sortie


@pytest.mark.asyncio
async def test_un_argument_d_un_autre_tour_n_est_pas_lu():
    sortie = await _jouer(_filtre(_contexte({"prenom": "Paul"}, tour_de_l_outil=3, tour=5)), ["Je note pour Paul."])
    assert "Paul" in sortie


@pytest.mark.asyncio
async def test_case_eteinte_le_prenom_reste_dit():
    sortie = await _jouer(_filtre(_contexte({"prenom": "Paul"}), retirer_nom=False), ["Merci Paul, quel est votre numéro ?"])
    assert "Paul" in sortie


def test_le_moteur_note_le_tour_sur_chaque_resultat_d_outil():
    from api.services.workflow.pipecat_engine import PipecatEngine

    moteur = PipecatEngine.__new__(PipecatEngine)
    moteur._gathered_context = {CLE_TOUR: 7}
    PipecatEngine.record_tool_result(moteur, {"function_name": "finaliser", "arguments": {"prenom": "Paul"}})
    assert moteur._gathered_context["tool_results"][-1]["tour"] == 7
