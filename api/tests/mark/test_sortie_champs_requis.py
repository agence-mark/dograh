"""[.mark] C6 : une sortie qui déclare ses champs requis, et le nom épelé connu de la fiche.

Chantier correctifs-banc-34 (29/09/2026), décision D-C6 (loi de placement : le 100 % passe par
le code). Run 882 : fiche pleine, la sortie « nom, numéro et adresse notés » prise sans que le
nom ait été épelé (l'outil le tenait pour sûr d'office). Run 884 : la même sortie prise alors
que la fiche n'avait ni commune ni rue.

⛔ Aucun champ en dur : la sortie DÉCLARE ses champs requis (`champs_requis`, à l'écran de la
sortie). Vide = aucune vérification, comportement d'avant.

| Test | Ce qu'il prouve |
|---|---|
| nom épelé | un nom écrit depuis l'épellation lue par le module est marqué épelé dans la fiche |
| nom non épelé | écrit, mais pas épelé |
| champs manquants | vide, à confirmer, nom non épelé : chacun manque, avec sa raison ; un champ inconnu est ignoré |
| clavier : refus | la sortie déclarée n'est pas prise, l'agent reste à l'étape et reçoit la consigne |
| clavier : passage | le champ noté (et sûr) dans le même tour, la sortie est prise |
| clavier : rien déclaré | témoin, la sortie est prise comme avant |
"""

import copy

import pytest

from api.services.workflow.fiche_au_fil_de_leau import CLE_ETAT, champs_manquants
from api.tests.mark.test_clavier_porte_la_fiche import (
    DEFINITION,
    _converser,
    _monter,
)
from api.tests.mark.test_fiche_correctifs_modules import Appel, _reglages
from pipecat.tests import MockLLMService

NOM = {"nom": "nom", "origine": "dicte", "description": "Nom de famille"}
NUMERO = {"nom": "numero_rappel", "origine": "dicte"}
COMMUNE = {"nom": "commune", "origine": "dicte"}


@pytest.mark.asyncio
async def test_C6_un_nom_ecrit_depuis_l_epellation_est_marque_epele():
    appel = Appel(_reglages(NOM))
    appel.dit("C'est mercier, m e r c i e r.")
    appel.trace("epellations_lues", entendu="m e r c i e r", epele="MERCIER")
    await appel.note(nom="MERCIER")
    assert appel.fiche[CLE_ETAT]["nom"].get("epele") is True, appel.fiche[CLE_ETAT]


@pytest.mark.asyncio
async def test_C6_run_882_un_nom_dit_sans_epeler_n_est_pas_epele():
    appel = Appel(_reglages(NOM))
    appel.dit("Je m'appelle Bertin.")
    await appel.note(nom="Bertin")
    assert appel.fiche["nom"] == "Bertin"
    assert not appel.fiche[CLE_ETAT]["nom"].get("epele")


@pytest.mark.asyncio
async def test_C6_les_champs_manquants_et_leur_raison():
    appel = Appel(_reglages(NOM, NUMERO, COMMUNE))
    appel.dit("Je m'appelle Bertin, c'est le 06 45 21 78 90.")
    await appel.note(nom="Bertin", numero_rappel="0645217890")
    reglages = _reglages(NOM, NUMERO, COMMUNE)
    assert champs_manquants(reglages, appel.fiche, ["nom", "numero_rappel", "commune", "inconnu"]) == [
        ("nom", "non_epele"),
        ("commune", "vide"),
    ]
    appel.fiche[CLE_ETAT]["numero_rappel"]["sure"] = False
    assert ("numero_rappel", "a_confirmer") in champs_manquants(reglages, appel.fiche, ["numero_rappel"])
    assert champs_manquants(reglages, appel.fiche, []) == []


def _definition_avec_requis(requis):
    definition = copy.deepcopy(DEFINITION)
    if requis is not None:
        definition["edges"][0]["data"]["champs_requis"] = requis
    return definition


FICHE = {"fiche_au_fil_de_leau": True, "fiche_champs": [NUMERO]}


@pytest.mark.asyncio
async def test_C6_au_clavier_la_sortie_n_est_pas_prise_tant_qu_un_champ_requis_manque(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, FICHE, _definition_avec_requis(["numero_rappel"]))
    charge, _ = await _converser(
        test_client_factory,
        user,
        workflow,
        [
            MockLLMService.create_function_call_chunks("fin", {}, tool_call_id="porte_1"),
            MockLLMService.create_text_chunks("Sur quel numéro pouvons-nous vous rappeler ?"),
        ],
        "c'est tout pour moi",
    )
    assert charge["checkpoint"]["current_node_id"] == "start", charge["checkpoint"]
    resultats = [
        e["payload"]
        for tour in charge["session_data"]["turns"]
        for e in tour.get("events") or []
        if e["type"] == "tool_call_result" and e["payload"].get("function_name") == "fin"
    ]
    assert resultats and "numero_rappel" in str(resultats[-1]), charge["session_data"]["turns"]


@pytest.mark.asyncio
async def test_C6_au_clavier_le_champ_note_la_sortie_est_prise(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, FICHE, _definition_avec_requis(["numero_rappel"]))
    charge, _ = await _converser(
        test_client_factory,
        user,
        workflow,
        [
            MockLLMService.create_multiple_function_call_chunks(
                [
                    {"name": "noter_information", "arguments": {"numero_rappel": "0645217890"}, "tool_call_id": "note_1"},
                    {"name": "fin", "arguments": {}, "tool_call_id": "porte_1"},
                ]
            ),
            MockLLMService.create_text_chunks("Merci, au revoir."),
        ],
        "c'est le 0645217890",
    )
    assert charge["checkpoint"]["current_node_id"] == "end", charge["checkpoint"]


@pytest.mark.asyncio
async def test_C6_au_clavier_rien_de_declare_la_sortie_est_prise_comme_avant(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, FICHE, _definition_avec_requis(None))
    charge, _ = await _converser(
        test_client_factory,
        user,
        workflow,
        [
            MockLLMService.create_function_call_chunks("fin", {}, tool_call_id="porte_1"),
            MockLLMService.create_text_chunks("Au revoir."),
        ],
        "c'est tout pour moi",
    )
    assert charge["checkpoint"]["current_node_id"] == "end", charge["checkpoint"]


@pytest.mark.asyncio
async def test_C6_secours_une_sortie_refusee_deux_fois_passe_a_la_troisieme(
    db_session, async_session, test_client_factory
):
    """D-C6-secours (Evan, 29/09) : un appelant qui ne sait pas épeler n'est jamais
    bloqué en boucle. Deux refus, puis la sortie passe, notée au journal."""
    user, workflow = await _monter(db_session, async_session, FICHE, _definition_avec_requis(["numero_rappel"]))
    charge, _ = await _converser(
        test_client_factory,
        user,
        workflow,
        [
            MockLLMService.create_function_call_chunks("fin", {}, tool_call_id="porte_1"),
            MockLLMService.create_function_call_chunks("fin", {}, tool_call_id="porte_2"),
            MockLLMService.create_function_call_chunks("fin", {}, tool_call_id="porte_3"),
            MockLLMService.create_text_chunks("Au revoir."),
        ],
        "je ne veux pas donner mon numéro",
    )
    assert charge["checkpoint"]["current_node_id"] == "end", charge["checkpoint"]
    sorties = [
        e["statut"] for e in charge["checkpoint"]["gathered_context"]["fiche_journal"] if e.get("sortie") == "fin"
    ]
    assert sorties == ["sortie_refusee", "sortie_refusee", "sortie_forcee"], sorties
