"""[.mark] La porte parlée au clavier, par les vraies routes (plan porte-parlee, lot 5, R1).

Plan `Labo-agent-vocal/plans/porte-parlee/`. Le clavier monte le même processeur que le téléphone
(règle C8) : ce test traverse la vraie route (session, message, ``text_chat_runner`` réel, moteur
réel, base de test) ; seul le modèle est écrit d'avance. Il échoue si l'étape ne change pas, si la
fiche ne se remplit pas, ou si la ligne de porte ou le séparateur s'affichent.

| Test | Ce qu'il prouve |
|---|---|
| deux tours | « → porte » change d'étape sans appel de fonction ; la porte de l'étape d'arrivée est ensuite reconnue (l'étape en cours a bien changé ; le prompt envoyé, lui, est prouvé dans `test_porte_parlee_moteur.py`, le modèle simulé l'ignorant) ; la fiche se remplit ; rien de technique n'est affiché |
| case éteinte | la même réponse ne change pas d'étape : c'est bien la case qui fait le travail |
"""

import pytest

from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_MODE,
    CLE_PORTES_DANS_LA_REPONSE,
    MODE_POST_SCRIPTUM,
)
from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter
from api.tests.mark.test_porte_parlee_consigne import _definition
from api.tests.mark.test_portes_souples import _messages
from pipecat.tests import MockLLMService

POST_SCRIPTUM = {**FICHE, CLE_MODE: MODE_POST_SCRIPTUM}
ALLUMEE = {**POST_SCRIPTUM, CLE_PORTES_DANS_LA_REPONSE: True}

TOUR_1 = (
    "c'est pour une panne",
    [
        MockLLMService.create_text_chunks(
            '→ vers_etape\nQuelle marque ?\n|||\n{"motif": "panne"}'
        )
    ],
)
TOUR_2 = (
    "non c'est tout",
    [MockLLMService.create_text_chunks("→ vers_fin\nAu revoir. ||| {}")],
)


def _affiche(charge: dict) -> str:
    """Ce que l'écran du clavier montre de chaque tour : le texte et ses événements."""
    tours = charge["session_data"]["turns"]
    return repr(
        [
            ((t.get("assistant_message") or {}).get("text"), t.get("events"))
            for t in tours
        ]
    )


@pytest.mark.asyncio
async def test_au_clavier_la_porte_ecrite_change_d_etape(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, ALLUMEE, _definition())
    charge = await _messages(test_client_factory, user, workflow, [TOUR_1])
    point = charge["checkpoint"]
    assert point["current_node_id"] == "etape", point
    assert point["gathered_context"].get("motif") == "panne", point["gathered_context"]
    affiche = _affiche(charge)
    assert "Quelle marque ?" in affiche, affiche
    assert (
        "→" not in affiche and "|||" not in affiche and "vers_etape" not in affiche
    ), affiche
    assert "tool_call" not in affiche, affiche


@pytest.mark.asyncio
async def test_au_clavier_la_porte_de_l_etape_d_arrivee_est_reconnue(
    db_session, async_session, test_client_factory
):
    """« vers_fin » n'existe que depuis l'étape : si l'étape en cours n'avait pas changé,
    la porte serait inconnue et l'appel resterait. Le prompt envoyé au modèle est prouvé
    dans `test_porte_parlee_moteur.py` (le modèle simulé ici ne le lit pas)."""
    user, workflow = await _monter(db_session, async_session, ALLUMEE, _definition())
    charge = await _messages(test_client_factory, user, workflow, [TOUR_1, TOUR_2])
    assert charge["checkpoint"]["current_node_id"] == "end", charge["checkpoint"]
    assert "Au revoir." in _affiche(charge)


@pytest.mark.asyncio
async def test_au_clavier_case_eteinte_la_meme_reponse_ne_change_pas_d_etape(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(
        db_session, async_session, POST_SCRIPTUM, _definition()
    )
    charge = await _messages(test_client_factory, user, workflow, [TOUR_1])
    assert charge["checkpoint"]["current_node_id"] == "start", charge["checkpoint"]


@pytest.mark.asyncio
async def test_au_clavier_une_porte_seule_fait_reparler_le_modele_dans_l_etape_d_arrivee(
    db_session, async_session, test_client_factory
):
    """D17 : « → porte » sans phrase. La porte est prise et le modèle reparle dans l'étape
    d'arrivée, dans le même tour : l'écran affiche sa phrase, jamais un tour muet."""
    user, workflow = await _monter(db_session, async_session, ALLUMEE, _definition())
    tour = (
        "c'est pour une panne",
        [
            MockLLMService.create_text_chunks('→ vers_etape\n|||\n{"motif": "panne"}'),
            MockLLMService.create_text_chunks("Quelle marque ? ||| {}"),
        ],
    )
    charge = await _messages(test_client_factory, user, workflow, [tour])
    assert charge["checkpoint"]["current_node_id"] == "etape", charge["checkpoint"]
    affiche = _affiche(charge)
    assert "Quelle marque ?" in affiche, affiche
    assert "→" not in affiche and "|||" not in affiche, affiche
    assert charge["checkpoint"]["gathered_context"].get("motif") == "panne"
