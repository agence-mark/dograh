"""[.mark] La clé du greffier se range comme une clé de Dograh (plan mode-prise-de-notes, lot 10).

Décision d'Evan du 04/10 (« comme Dograh ») : le bloc `greffier_llm` de la configuration de
l'agent porte le modèle du greffier au format d'une surcharge de modèle. Sa clé est en base
comme toutes les clés de Dograh, masquée dans toutes les réponses de l'API, remise à sa vraie
valeur quand l'écran renvoie le masque. Clé vide = clé de la conversation.

| Test | Ce qu'il prouve |
|---|---|
| masque | la réponse de l'API ne montre jamais la clé du greffier ; le reste du bloc reste lisible |
| aller-retour | un enregistrement qui renvoie le masque garde la vraie clé, SANS surcharge de modèle |
| nouvelle clé | une clé tapée remplace l'ancienne |
| masque orphelin | un masque sans clé à retrouver (rien en base, autre fournisseur) est refusé (422), jamais écrit |
| clé vide | pas de clé = pas de clé (la conversation prêtera la sienne), rien n'est recopié |
| forme | un bloc mal formé est refusé à l'enregistrement (422) |
"""

import pytest

from api.services.configuration.masking import (
    MASK_MARKER,
    mask_workflow_configurations,
)
from api.services.workflow.fiche_au_fil_de_leau import CLE_MODE, MODE_GREFFIER
from api.tests.mark.test_clavier_porte_la_fiche import FICHE
from api.tests.mark.test_horaires_ouverture_reglage import _enregistrer

CLE = "cle-de-test-du-greffier-0123456789"
BLOC = {"provider": "mistral", "model": "mistral-large-2512", "api_key": CLE}
EXISTANTES = {**FICHE, CLE_MODE: MODE_GREFFIER, "greffier_llm": BLOC}


def _masque() -> str:
    return mask_workflow_configurations(EXISTANTES)["greffier_llm"]["api_key"]


def test_la_reponse_masque_la_cle_du_greffier():
    masque = mask_workflow_configurations(EXISTANTES)
    assert MASK_MARKER in masque["greffier_llm"]["api_key"]
    assert CLE not in str(masque)
    assert masque["greffier_llm"]["model"] == "mistral-large-2512"
    # la configuration enregistrée n'est pas touchée par le masque
    assert EXISTANTES["greffier_llm"]["api_key"] == CLE


def test_le_masque_renvoye_garde_la_vraie_cle_sans_surcharge_de_modele():
    entrant = {**EXISTANTES, "greffier_llm": {**BLOC, "api_key": _masque()}}
    assert "model_overrides" not in entrant
    reponse, ecrit = _enregistrer(entrant, existantes=EXISTANTES)
    assert reponse.status_code == 200, reponse.text
    assert ecrit["greffier_llm"]["api_key"] == CLE


def test_une_cle_tapee_remplace_l_ancienne():
    nouvelle = "une-autre-cle-de-test-9876543210"
    entrant = {**EXISTANTES, "greffier_llm": {**BLOC, "api_key": nouvelle}}
    reponse, ecrit = _enregistrer(entrant, existantes=EXISTANTES)
    assert reponse.status_code == 200, reponse.text
    assert ecrit["greffier_llm"]["api_key"] == nouvelle


@pytest.mark.parametrize(
    "existantes",
    [
        {},
        {**EXISTANTES, "greffier_llm": {**BLOC, "provider": "openai"}},
    ],
    ids=["rien-en-base", "autre-fournisseur"],
)
def test_un_masque_orphelin_est_refuse_et_rien_n_est_ecrit(existantes):
    entrant = {**EXISTANTES, "greffier_llm": {**BLOC, "api_key": _masque()}}
    reponse, ecrit = _enregistrer(entrant, existantes=existantes)
    assert reponse.status_code == 422, reponse.text
    assert "clerk's API key is masked" in reponse.text
    assert ecrit is None


def test_une_cle_vide_reste_vide():
    sans_cle = {k: v for k, v in BLOC.items() if k != "api_key"}
    entrant = {**EXISTANTES, "greffier_llm": sans_cle}
    reponse, ecrit = _enregistrer(entrant, existantes=EXISTANTES)
    assert reponse.status_code == 200, reponse.text
    assert "api_key" not in ecrit["greffier_llm"]


@pytest.mark.parametrize(
    "bloc",
    [
        {"model": 12},
        {"provider": ["mistral"]},
        {"temperature": "chaud"},
        {"provider": "mistrall"},
    ],
)
def test_un_bloc_mal_forme_est_refuse(bloc):
    reponse, ecrit = _enregistrer({**EXISTANTES, "greffier_llm": bloc})
    assert reponse.status_code == 422, reponse.text
    assert ecrit is None
