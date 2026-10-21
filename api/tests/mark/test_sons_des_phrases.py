"""[.mark] Chantier fiabilite-orchestration, lot 4 ter (F22) : le son des phrases fabriqué au décroché.

| Test | La garantie |
|---|---|
| quels textes | les phrases allumées des agents de l'appel, sans variable, sans doublon ; éteintes : rien |
| fabrique | un vrai circuit Pipecat isolé (fausse voix de Pipecat) rend un son par phrase, rien ne sort vers l'appel |
| joué sans la voix | le diseur joue le son fabriqué (``audio=``, transcription jointe), sans demander la voix |
| repli | sans son (échec, phrase avec variable), la phrase est dite par la voix comme avant |
| voix de l'appel | la fabrique ne branche jamais la voix de l'appel ni une voix déjà reliée (CI du 19/10) |
"""

import asyncio
from types import SimpleNamespace

import pytest
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.tests import MockTTSService

from api.services.phrases.catalogue import OUTIL_ECHOUE, MOTIFS, REPONSE_PERDUE
from api.services.phrases.diseur import DiseurDePhrases
from api.services.phrases.sons import FabriqueDesSons, Son, textes_a_fabriquer
from api.services.pipecat.worker_runner import create_worker_runner, run_worker_runner
from api.tests.mark.test_attente_parlee import _FauxMoteur


def _defaut(motif):
    return MOTIFS[motif].variantes_defaut[0]


def test_les_textes_a_fabriquer():
    agent = {
        "phrases_regles": [
            {"motif": OUTIL_ECHOUE, "variantes": ["Bonjour {{nom}}."]},
            {"motif": "outil_tarde", "portee": "etape", "etape": "X", "variantes": ["Je regarde."]},
            {"motif": REPONSE_PERDUE, "variantes": [], "active": False},
        ]
    }
    textes = textes_a_fabriquer([agent, {}], {})
    assert "Bonjour {{nom}}." not in textes  # variable : fabriquée à la volée
    assert "Je regarde." in textes  # règle d'étape allumée
    assert _defaut(REPONSE_PERDUE) in textes  # l'autre agent garde le défaut allumé
    assert len(textes) == len(set(textes))
    seul = textes_a_fabriquer([agent], agent)
    assert _defaut(REPONSE_PERDUE) not in seul  # éteinte chez le seul agent


class _Sortie(FrameProcessor):
    def __init__(self):
        super().__init__()
        self.vus = []

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        self.vus.append(frame)
        await self.push_frame(frame, direction)


@pytest.mark.asyncio
async def test_la_fabrique_rend_un_son_par_phrase_sans_rien_envoyer_a_l_appel():
    sortie = _Sortie()
    appel = PipelineWorker(Pipeline([sortie]), name="call", enable_rtvi=False)
    runner = create_worker_runner()
    tache = asyncio.create_task(run_worker_runner(runner, appel))
    try:
        while appel.started_at is None:
            await asyncio.sleep(0.01)
        fabrique = FabriqueDesSons(
            creer_la_voix=lambda: MockTTSService(mock_audio_duration_ms=60, frame_delay=0),
            ajouter_le_circuit=appel.add_workers,
            taux_attendu=16000,
        )
        fabrique.lancer(["Un instant.", "Je vérifie."])
        await asyncio.wait_for(fabrique.attendre(), 30)
        assert set(fabrique.sons) == {"Un instant.", "Je vérifie."}, fabrique.echecs
        assert all(isinstance(s, Son) and s.audio and s.taux == 16000 for s in fabrique.sons.values())
        from pipecat.frames.frames import TTSAudioRawFrame

        assert not any(isinstance(f, TTSAudioRawFrame) for f in sortie.vus)
    finally:
        await appel.cancel()
        await asyncio.gather(tache, return_exceptions=True)


@pytest.mark.asyncio
async def test_le_diseur_joue_le_son_fabrique_sans_la_voix_sinon_la_voix():
    moteur = _FauxMoteur(lambda: 0.0)
    appels = []

    async def queue_speech(texte=None, **options):
        appels.append((texte, options))
        fin = asyncio.Event()
        fin.set()
        return SimpleNamespace(wait=fin.wait, text=texte or options.get("transcript"), outcome=None)

    moteur.queue_speech = queue_speech
    fabrique = FabriqueDesSons(creer_la_voix=lambda: None, ajouter_le_circuit=None, taux_attendu=16000)
    fabrique.sons[_defaut(OUTIL_ECHOUE)] = Son(audio=b"\x00\x01" * 10, taux=16000)
    moteur.fabrique_des_sons = fabrique
    diseur = DiseurDePhrases(moteur)
    parole = await diseur.dire_la_parole(OUTIL_ECHOUE)
    await diseur.attendre_la_fin()
    texte, options = appels[0]
    assert texte is None and options["audio"] == b"\x00\x01" * 10
    assert options["transcript"] == _defaut(OUTIL_ECHOUE) and options["append_to_context"] is True
    assert parole.text == _defaut(OUTIL_ECHOUE)
    # Une phrase sans son fabriqué (phrase propre d'un connecteur) : la voix, comme avant.
    await diseur.dire_la_parole(OUTIL_ECHOUE, texte="Autre phrase.")
    assert appels[1][0] == "Autre phrase." and "audio" not in appels[1][1]


@pytest.mark.asyncio
async def test_la_fabrique_ne_touche_jamais_la_voix_de_l_appel():
    """CI du 19/10 : une fabrique de voix qui rend la voix de l'appel (ou une voix déjà reliée à un
    circuit) ne fabrique rien ; la brancher ici la retirerait de l'appel, qui ne parlerait plus."""
    voix_de_l_appel = MockTTSService(mock_audio_duration_ms=60, frame_delay=0)
    ajouter = []

    async def ajouter_le_circuit(worker):
        ajouter.append(worker)

    fabrique = FabriqueDesSons(
        creer_la_voix=lambda: voix_de_l_appel,
        ajouter_le_circuit=ajouter_le_circuit,
        taux_attendu=16000,
        voix_de_l_appel=voix_de_l_appel,
    )
    await fabrique.fabriquer(["Un instant."])
    reliee = MockTTSService(mock_audio_duration_ms=60, frame_delay=0)
    Pipeline([reliee, _Sortie()])
    fabrique_reliee = FabriqueDesSons(
        creer_la_voix=lambda: reliee, ajouter_le_circuit=ajouter_le_circuit, taux_attendu=16000
    )
    await fabrique_reliee.fabriquer(["Un instant."])
    assert ajouter == [] and fabrique.sons == {} and fabrique_reliee.sons == {}
