"""[.mark] SA-49 (M105) : la publication d'un agent refusée pour des variables que le code pose lui-même au décroché.

``groupe_publier(299)`` refusait l'agent 300 sous « Variables des prompts » : ``adresse_etablissement``, ``horaires_ouverture`` (posées par
l'établissement), ``commande_minimum``, ``commande_paiements_acceptes``, ``commande_types_ouverts``, ``livraison_phrase_des_zones`` (étiquettes du
module Restauration, déclarées dans ``modules/registre.py``). La ligne « variables » de la préparation (lue par le contrôle de publication) ne
connaissait que les valeurs d'essai et les extractions ; elle lit maintenant aussi le catalogue des variables (moteur, établissement, étiquettes des
modules ALLUMÉS), sans aucune liste en dur dans le contrôle.

| Test | Ce qu'il prouve |
|---|---|
| module allumé | les six variables du prompt de l'agent 300 ne manquent plus |
| inventée | ``{{variable_inventee}}`` bloque toujours |
| module éteint | ses étiquettes redeviennent inconnues ; celles de l'établissement restent connues |
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from api.services import preparation

PROMPT_300 = (
    "Casa Italia, {{adresse_etablissement}}. On commande {{commande_types_ouverts}}. Horaires : {{horaires_ouverture}}. "
    "{{livraison_phrase_des_zones}} Minimum : {{commande_minimum}}. On règle {{commande_paiements_acceptes}}. {{variable_extra}}"
)
DU_MODULE = ("commande_minimum", "commande_paiements_acceptes", "commande_types_ouverts", "livraison_phrase_des_zones")


def _graphe(prompt: str) -> dict:
    return {
        "nodes": [
            {
                "id": "1", "type": "startCall", "position": {"x": 0, "y": 0},
                "data": {"name": "Accueil", "prompt": prompt, "is_start": True, "allow_interrupt": False, "add_global_prompt": False},
            },
            {"id": "2", "type": "endCall", "position": {"x": 0, "y": 100}, "data": {"name": "Fin", "prompt": "Au revoir"}},
        ],
        "edges": [{"id": "e", "source": "1", "target": "2", "data": {"label": "fin", "condition": "toujours"}}],
    }


def _variables(prompt: str, configurations: dict):
    etapes = preparation.calculer(
        definition=json.loads(json.dumps(_graphe(prompt))),
        variables_du_modele={"variable_extra": "x"},
        configurations=configurations,
        effective=SimpleNamespace(llm=1, stt=1, tts=1, realtime=None, is_realtime=False),
        outils_actifs=set(),
        fiche=None,
        tests=[],
        problemes_tests_obligatoires=[],
    )
    return next(e for e in etapes if e.id == "variables")


def test_les_variables_posees_par_le_module_allume_et_l_etablissement_ne_manquent_pas():
    etape = _variables(PROMPT_300, {"commande_sur_catalogue": True})
    assert etape.etat == "fait" and etape.manquants == [], etape.manquants


def test_une_variable_inventee_bloque_toujours():
    etape = _variables(PROMPT_300 + " {{variable_inventee}}", {"commande_sur_catalogue": True})
    assert etape.etat == "a_faire" and etape.manquants == ["variable_inventee"]


def test_un_module_eteint_rend_ses_variables_inconnues():
    etape = _variables(PROMPT_300, {"commande_sur_catalogue": False})
    assert etape.manquants == sorted(DU_MODULE)  # l'adresse et les horaires de l'établissement restent connus


def test_un_specialise_recoit_les_variables_du_module_allume_sur_son_principal():
    """Au décroché, les étiquettes sont posées d'après les réglages du principal appelé ; le spécialisé les reçoit avec l'appel."""
    posees = preparation.variables_posees_par_le_code({"commande_sur_catalogue": False}) | preparation.variables_posees_par_le_code(
        {"commande_sur_catalogue": True}
    )
    etapes = preparation.calculer(
        definition=json.loads(json.dumps(_graphe(PROMPT_300))),
        variables_du_modele={"variable_extra": "x"},
        configurations={"commande_sur_catalogue": False},
        effective=SimpleNamespace(llm=1, stt=1, tts=1, realtime=None, is_realtime=False),
        outils_actifs=set(),
        fiche=None,
        tests=[],
        problemes_tests_obligatoires=[],
        posees_par_le_code=posees,
    )
    assert next(e for e in etapes if e.id == "variables").manquants == []
