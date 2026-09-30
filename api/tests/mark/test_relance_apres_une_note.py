"""[.mark] K1 : après une note seule, le modèle reprend la parole (jamais un tour muet).

Chantier correctifs-apres-figeage (30/09/2026), plan `Labo-agent-vocal/plans/correctifs-apres-figeage/`.
Run 914 (clavier, agent n° 34 v8) : à l'étape « autre chose ? », la personne donne une deuxième demande ; le
modèle répond par une note seule (`noter_information`, aucun texte, aucune porte) ; le tour se termine sans
réponse : un seul appel au modèle, pas de relance après le résultat de la note.

Par les VRAIES routes du clavier ; seul le modèle est écrit d'avance.

| Test | Ce qu'il prouve |
|---|---|
| run 914 | porte vers une étape, puis une note seule : le modèle est relancé et parle |
| note seule dès l'accueil | témoin : même réponse à la première étape |
"""

import copy
import uuid

import pytest

from api.tests.mark.test_clavier_porte_la_fiche import DEFINITION, _monter
from api.tests.mark.test_portes_souples import _messages
from pipecat.tests import MockLLMService

FICHE = {
    "fiche_au_fil_de_leau": True,
    "fiche_champs": [
        {"nom": "motif", "origine": "deduit", "description": "La raison de l'appel"},
        {"nom": "reference_commande", "origine": "dicte", "description": "Numéro de commande"},
    ],
}


def _definition_a_trois_etapes():
    """accueil → (porte) → autre_demande → (porte) → fin."""
    definition = copy.deepcopy(DEFINITION)
    debut, fin = definition["nodes"]
    milieu = {
        "id": "autre",
        "type": "agentNode",
        "position": {"x": 0, "y": 100},
        "data": {
            "name": "autre_demande",
            "prompt": "Tu vérifies qu'il ne reste rien.",
            "allow_interrupt": False,
            "add_global_prompt": False,
        },
    }
    definition["nodes"] = [debut, milieu, fin]
    definition["edges"] = [
        {"id": "start-autre", "source": "start", "target": "autre",
         "data": {"label": "coordonnees_notees", "condition": "Quand les coordonnées sont notées."}},
        {"id": "autre-end", "source": "autre", "target": "end",
         "data": {"label": "rien_d_autre", "condition": "Quand il ne reste rien."}},
    ]
    return definition


def _note(tool_call_id: str):
    return MockLLMService.create_function_call_chunks(
        "noter_information", {"reference_commande": "CM20931"}, tool_call_id=tool_call_id
    )


@pytest.mark.asyncio
async def test_run_914_apres_une_porte_une_note_seule_le_modele_reparle(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, FICHE, _definition_a_trois_etapes())
    appel = uuid.uuid4().hex[:6]
    charge = await _messages(
        test_client_factory,
        user,
        workflow,
        [
            (
                "c'est bon pour mes coordonnées",
                [
                    MockLLMService.create_function_call_chunks("coordonnees_notees", {}, tool_call_id=f"porte_{appel}"),
                    MockLLMService.create_text_chunks("Est-ce qu'il y a autre chose que je peux faire pour vous ?"),
                ],
            ),
            (
                "oui, j'ai aussi une commande, la CM20931",
                [
                    _note(f"note_{appel}"),
                    MockLLMService.create_text_chunks("C'est noté. Autre chose ?"),
                ],
            ),
        ],
    )
    dernier = charge["session_data"]["turns"][-1]
    assert (dernier.get("assistant_message") or {}).get("text"), dernier


@pytest.mark.asyncio
async def test_temoin_note_seule_a_l_accueil_le_modele_reparle(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, FICHE, _definition_a_trois_etapes())
    charge = await _messages(
        test_client_factory,
        user,
        workflow,
        [
            (
                "j'appelle pour ma commande CM20931",
                [_note(f"note_{uuid.uuid4().hex[:6]}"), MockLLMService.create_text_chunks("C'est noté.")],
            ),
        ],
    )
    dernier = charge["session_data"]["turns"][-1]
    assert (dernier.get("assistant_message") or {}).get("text"), dernier
