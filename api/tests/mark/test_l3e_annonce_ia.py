"""[.mark] builder partie 3, L3e sous-lot 2 : l'annonce « vous parlez à une IA » (allumée par défaut, activable et modifiable, D1). Réflexe R1 : tout traverse le VRAI moteur
(``PipecatEngine.queue_node_opening``, par où passe l'ouverture de tout appel : téléphone, widget, campagne, passation, répondeur).

| Test | La garantie |
|---|---|
| accueil en texte | la phrase précède l'accueil dans la même parole |
| ouverture par le modèle / accueil enregistré | la phrase est dite à part, avant ; le modèle part ensuite |
| déjà annoncé | un accueil qui dit déjà « assistant virtuel » ne l'entend pas deux fois |
| une fois par appel | l'ouverture d'un agent reçu par passation ne la redit pas |
| D1 | règle éteinte ou vidée : l'annonce n'est pas dite ; sans règle elle est dite avec le texte du catalogue ; le texte d'une règle est dit à sa place |
| catalogue | le motif est verrouillé, sans délai ; la ligne de la carte des phrases existe |
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pipecat.processors.aggregators.llm_context import LLMContext

from api.services.phrases.carte import INVENTAIRE_DU_CODE
from api.services.phrases.catalogue import ANNONCE_IA, MOTIFS
from api.services.pipecat.speech_playback import PlaybackOutcome
from api.services.securite import annonce_ia
from api.services.workflow.pipecat_engine import PipecatEngine

DEFAUT = MOTIFS[ANNONCE_IA].variantes_defaut[0]


def _moteur(workflow, *, accueil=None, type_accueil="text", reglages=None):
    noeud = workflow.nodes[workflow.start_node_id]
    noeud.greeting_type = type_accueil
    noeud.greeting = accueil if type_accueil == "text" else None
    noeud.greeting_recording_id = "9" if type_accueil == "audio" else None
    moteur = PipecatEngine(workflow=workflow, llm=SimpleNamespace(queue_frame=AsyncMock()), context=LLMContext(), call_context_vars={})
    moteur.call_worker = SimpleNamespace(queue_frame=AsyncMock())
    moteur.set_transport_output(SimpleNamespace(queue_frame=AsyncMock()))
    moteur.set_fetch_recording_audio(AsyncMock(return_value=SimpleNamespace(audio=b"\x01\x00" * 160, transcript="Accueil enregistré.")))
    moteur.active_agent.reglages = reglages
    moteur.active_agent.worker = moteur.active_agent.worker or SimpleNamespace()
    dites: list[dict] = []

    async def parole(texte=None, **options):
        dites.append({"texte": texte, **options})
        lecture = SimpleNamespace(outcome=PlaybackOutcome.PLAYED, text=texte, wait=AsyncMock(), done=True)
        return lecture

    moteur.queue_speech = parole
    moteur.active_agent.run_llm = AsyncMock()
    moteur.active_agent.llm = moteur.active_agent.llm or SimpleNamespace()
    return moteur, dites


async def _ouvrir(moteur, workflow, *, avant=None, genere=True):
    return await moteur.queue_node_opening(node_id=workflow.start_node_id, previous_node_id=avant, generate_if_no_greeting=genere)


@pytest.mark.asyncio
async def test_un_accueil_en_texte_est_precede_de_l_annonce_dans_la_meme_parole(simple_workflow):
    moteur, dites = _moteur(simple_workflow, accueil="Bonjour, que puis-je faire ?")
    await _ouvrir(moteur, simple_workflow)
    assert [d["texte"] for d in dites] == [f"{DEFAUT} Bonjour, que puis-je faire ?"]


@pytest.mark.asyncio
async def test_une_ouverture_par_le_modele_est_precedee_de_l_annonce_dite_a_part_hors_historique(simple_workflow):
    moteur, dites = _moteur(simple_workflow, accueil=None)
    await _ouvrir(moteur, simple_workflow)
    assert [d["texte"] for d in dites] == [DEFAUT]
    assert dites[0]["append_to_context"] is False and dites[0]["persist_to_logs"] is True  # l'ouverture ne part pas sur un message de l'assistant
    moteur.active_agent.run_llm.assert_awaited_once()


@pytest.mark.asyncio
async def test_un_accueil_enregistre_est_precede_de_l_annonce_dite_a_part(simple_workflow):
    moteur, dites = _moteur(simple_workflow, type_accueil="audio")
    await _ouvrir(moteur, simple_workflow)
    assert dites[0]["texte"] == DEFAUT and dites[1].get("recording_pk") == 9


@pytest.mark.asyncio
@pytest.mark.parametrize("accueil", ["Bonjour, je suis l'assistante virtuelle de la maison.", "Bonjour, vous parlez à une intelligence artificielle.", "Hello, I am an AI assistant."])
async def test_un_agent_qui_annonce_deja_ne_l_entend_pas_deux_fois(simple_workflow, accueil):
    moteur, dites = _moteur(simple_workflow, accueil=accueil)
    await _ouvrir(moteur, simple_workflow)
    assert [d["texte"] for d in dites] == [accueil]


@pytest.mark.asyncio
async def test_un_accueil_ordinaire_avec_le_verbe_avoir_n_est_pas_pris_pour_une_annonce(simple_workflow):
    moteur, dites = _moteur(simple_workflow, accueil="Bonjour, j'ai bien reçu votre appel.")
    await _ouvrir(moteur, simple_workflow)
    assert dites[0]["texte"].startswith(DEFAUT)


@pytest.mark.asyncio
async def test_l_ouverture_d_un_agent_recu_par_passation_ne_redit_pas_l_annonce(simple_workflow):
    moteur, dites = _moteur(simple_workflow, accueil="Bonjour.")
    await _ouvrir(moteur, simple_workflow)
    await _ouvrir(moteur, simple_workflow)  # la passation rouvre l'étape de départ de l'agent appelé
    assert [d["texte"] for d in dites] == [f"{DEFAUT} Bonjour.", "Bonjour."]


@pytest.mark.asyncio
async def test_reprendre_une_etape_en_cours_n_est_pas_une_ouverture_d_appel(simple_workflow):
    moteur, dites = _moteur(simple_workflow, accueil="Bonjour.")
    await _ouvrir(moteur, simple_workflow, avant=simple_workflow.start_node_id)
    assert dites == []


@pytest.mark.asyncio
async def test_d1_une_regle_eteinte_ou_videe_n_est_pas_dite(simple_workflow):
    """Clôture, lot B (D1) : plus de verrou. L'annonce éteinte ou vidée par une règle de l'agent n'est pas dite ; l'accueil part seul."""
    for regle in (
        {"motif": ANNONCE_IA, "portee": "agent", "variantes": [" "], "active": False},
        {"motif": ANNONCE_IA, "portee": "agent", "variantes": ["Texte."], "active": False},
    ):
        moteur, dites = _moteur(simple_workflow, accueil="Bonjour.", reglages={"phrases_regles": [regle]})
        await _ouvrir(moteur, simple_workflow)
        assert dites[0]["texte"] == "Bonjour."


@pytest.mark.asyncio
async def test_d1_le_texte_se_change_et_l_annonce_est_allumee_par_defaut(simple_workflow):
    regle = {"motif": ANNONCE_IA, "portee": "agent", "variantes": ["Cet appel est tenu par une IA de la maison."], "active": True}
    moteur, dites = _moteur(simple_workflow, accueil="Bonjour.", reglages={"phrases_regles": [regle]})
    await _ouvrir(moteur, simple_workflow)
    assert dites[0]["texte"] == "Cet appel est tenu par une IA de la maison. Bonjour."
    moteur, dites = _moteur(simple_workflow, accueil="Bonjour.")  # aucune règle : allumée avec le texte du catalogue
    await _ouvrir(moteur, simple_workflow)
    assert dites[0]["texte"] == f"{DEFAUT} Bonjour."


def test_d1_le_motif_n_est_plus_verrouille_et_sa_ligne_est_dans_la_carte_des_phrases():
    motif = MOTIFS[ANNONCE_IA]
    assert motif.verrouille is False and motif.actif_par_defaut is True and motif.a_un_delai is False
    assert "securite/annonce_ia.py" in INVENTAIRE_DU_CODE
    assert annonce_ia.texte_de_l_annonce(None) == DEFAUT
    assert annonce_ia.texte_de_l_annonce({"phrases_regles": [{"motif": ANNONCE_IA, "portee": "agent", "variantes": ["x"], "active": False}]}) == ""
