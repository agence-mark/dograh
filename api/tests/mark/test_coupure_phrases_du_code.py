"""[.mark] Chantier voix-soniox, D20 : les phrases du code coupées par l'appelant, comptées au mot près.

| Test | La garantie |
|---|---|
| part jouée | avant le premier mot, au milieu, après le dernier ; sans minutage : inconnue, jamais estimée au temps |
| minutage de la fabrique | un vrai circuit Pipecat isolé : la fabrique garde les mots de la voix (heure du mot moins heure du premier son) |
| ElevenLabs et Soniox | les mêmes trois coupures avec le minutage mot à mot d'ElevenLabs et celui, par caractère, du connecteur Soniox (``_to_word_times`` réel) |
| copie envoyée au modèle | la ligne « L'appelant a entendu » est réécrite (jamais retirée), la réplique de l'historique ramenée au dernier mot joué, l'original intact |
| ordre des messages | coupée juste derrière un résultat d'outil : jamais de message de l'appelant qui suive un résultat |
| rien ne change | sans coupure, phrase jouée en entier ou coupée après le dernier mot : la requête est le même objet |
| lecture | ``SpeechPlayback`` date le début de la lecture et sa coupure (route réelle du suivi de lecture) |
| branchement | la réécriture est posée sur le modèle de l'appel et de chaque agent appelé, avant la trace |
"""

import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pipecat.frames.frames import (
    InterruptionFrame,
    SpeechBoundaryFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    TTSTextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker
from pipecat.processors.frame_processor import FrameProcessor

from api.services.phrases.catalogue import MOTIFS, OUTIL_ECHOUE
from api.services.phrases.compte_rendu import compte_rendu, ligne_entendue
from api.services.phrases.coupures import (
    ETAT_DEBUT,
    ETAT_INCONNU,
    ETAT_RIEN,
    ETAT_TOUT,
    LIGNE_RIEN,
    REPLIQUE_RIEN,
    Partie,
    RegistreDesCoupures,
    brancher_les_coupures,
    partie_jouee,
    reecrire_les_coupures,
)
from api.services.phrases.diseur import DiseurDePhrases
from api.services.phrases.sons import FabriqueDesSons, Son, mots_depuis_le_son
from api.services.pipecat.speech_playback import PlaybackOutcome, SpeechPlaybackTracker
from api.services.pipecat.worker_runner import create_worker_runner, run_worker_runner
from api.tests.mark.test_attente_parlee import _FauxMoteur
from api.tests.mark.test_sons_des_phrases import _Sortie

TEXTE = MOTIFS[OUTIL_ECHOUE].variantes_defaut[0]
RACINE = Path(__file__).resolve().parents[2]


def _mots_elevenlabs(texte: str) -> list[tuple[str, float]]:
    """Le minutage d'ElevenLabs : un début par mot (ponctuation collée au mot)."""
    return [(mot, round(0.1 + 0.25 * i, 3)) for i, mot in enumerate(texte.split())]


def _mots_soniox(texte: str) -> list[tuple[str, float]]:
    """Le minutage de Soniox : un début PAR CARACTÈRE, que le connecteur (réel) transforme en mots."""
    from api.services.pipecat.soniox_cle_en_entete import MarkSonioxTTSService

    service = MarkSonioxTTSService(api_key="cle-de-test", sample_rate=24000)
    caracteres, debuts = [], []
    for i, mot in enumerate(texte.split()):
        for k, c in enumerate(mot + " "):
            caracteres.append(c)
            debuts.append(round(0.1 + 0.25 * i + 0.01 * k, 3))
    return service._to_word_times("flux", {"characters": caracteres, "character_start_times_seconds": debuts})


VOIX = {"elevenlabs": _mots_elevenlabs, "soniox": _mots_soniox}


# --------------------------------------------------------------------------- #
# La part jouée
# --------------------------------------------------------------------------- #

PHRASE = "Je transmets votre demande, on vous rappelle pour la confirmer."


@pytest.mark.parametrize("voix", sorted(VOIX))
def test_la_part_jouee_avant_au_milieu_apres(voix):
    mots = tuple(VOIX[voix](PHRASE))
    assert [m for m, _ in mots][:4] == ["Je", "transmets", "votre", "demande,"], mots
    debut_du_milieu = mots[4][1]  # « on » : le cinquième mot
    # Avant le premier mot : rien entendu.
    assert partie_jouee(PHRASE, mots, mots[0][1] - 0.05) == Partie(ETAT_RIEN)
    assert partie_jouee(PHRASE, mots, None).etat == ETAT_RIEN  # la lecture n'a pas commencé
    # Au milieu : jusqu'au dernier mot commencé, pas un caractère de plus.
    milieu = partie_jouee(PHRASE, mots, debut_du_milieu + 0.001)
    assert milieu.etat == ETAT_DEBUT
    assert milieu.joue == "Je transmets votre demande, on"
    avant = partie_jouee(PHRASE, mots, debut_du_milieu - 0.001)
    assert avant.joue == "Je transmets votre demande,"
    # Après le dernier mot (même juste après son début) : tout est entendu.
    assert partie_jouee(PHRASE, mots, mots[-1][1]).etat == ETAT_TOUT
    assert partie_jouee(PHRASE, mots, 60.0).etat == ETAT_TOUT


def test_sans_minutage_la_part_jouee_est_inconnue_jamais_estimee_au_temps():
    assert partie_jouee(PHRASE, (), 1.0).etat == ETAT_INCONNU
    assert partie_jouee(PHRASE, (), 600.0).etat == ETAT_INCONNU
    # La lecture n'ayant pas commencé, on le sait même sans minutage.
    assert partie_jouee(PHRASE, (), None).etat == ETAT_RIEN


def test_un_mot_que_la_voix_a_dit_autrement_ne_fait_pas_perdre_la_part_jouee():
    mots = (("Bonjour", 0.1), ("monsieur", 0.5), ("Durand", 0.9))
    partie = partie_jouee("Bonjour M. Durand", mots, 0.6)
    assert partie.etat == ETAT_DEBUT and partie.joue == "Bonjour monsieur"


def test_les_mots_se_datent_depuis_le_premier_son():
    assert mots_depuis_le_son([("Un", 5_100_000_000), ("instant.", 5_600_000_000)], 5_000_000_000) == (
        ("Un", 0.1),
        ("instant.", 0.6),
    )
    assert mots_depuis_le_son([("Un", 5_100_000_000)], None) == ()
    assert mots_depuis_le_son([("Un", 4_000_000_000)], 5_000_000_000) == (("Un", 0.0),)


# --------------------------------------------------------------------------- #
# La fabrique garde le minutage (vrai circuit Pipecat isolé)
# --------------------------------------------------------------------------- #


class _VoixMinutee(FrameProcessor):
    """Une voix qui fait comme celles de Pipecat à minutage de mots : un ``TTSTextFrame`` par mot, daté
    (``pts``) sur l'horloge du circuit à partir de l'heure du premier son, puis le son."""

    def __init__(self, mots_de: dict):
        super().__init__()
        self._mots_de = mots_de

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSSpeakFrame):
            await self.push_frame(TTSStartedFrame(context_id="c"))
            origine = self.get_clock().get_time()
            for mot, debut in self._mots_de[frame.text]:
                trame = TTSTextFrame(text=mot, aggregated_by="word")
                trame.pts = origine + int(debut * 1_000_000_000)
                await self.push_frame(trame)
            await self.push_frame(
                TTSAudioRawFrame(audio=b"\x00\x01" * 1600, sample_rate=16000, num_channels=1, context_id="c")
            )
            await self.push_frame(TTSStoppedFrame(context_id="c"))
        else:
            await self.push_frame(frame, direction)


async def _fabriquer(voix: str, texte: str = TEXTE) -> FabriqueDesSons:
    mots = {texte: VOIX[voix](texte)}
    appel = PipelineWorker(Pipeline([_Sortie()]), name="call", enable_rtvi=False)
    runner = create_worker_runner()
    tache = asyncio.create_task(run_worker_runner(runner, appel))
    try:
        while appel.started_at is None:
            await asyncio.sleep(0.01)
        fabrique = FabriqueDesSons(
            creer_la_voix=lambda: _VoixMinutee(mots), ajouter_le_circuit=appel.add_workers, taux_attendu=16000
        )
        fabrique.lancer([texte])
        await asyncio.wait_for(fabrique.attendre(), 30)
        assert texte in fabrique.sons, fabrique.echecs
        return fabrique
    finally:
        await appel.cancel()
        await asyncio.gather(tache, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("voix", sorted(VOIX))
async def test_la_fabrique_garde_le_minutage_des_mots(voix):
    fabrique = await _fabriquer(voix)
    attendu = VOIX[voix](TEXTE)
    mots = fabrique.sons[TEXTE].mots
    assert [m for m, _ in mots] == [m for m, _ in attendu]
    # L'origine est l'heure du premier son vue par le collecteur, quelques millisecondes après celle de la voix.
    assert all(abs(d - a) < 0.25 for (_, d), (_, a) in zip(mots, attendu)), (mots, attendu)
    assert [d for _, d in mots] == sorted(d for _, d in mots)
    assert fabrique.sons[TEXTE].audio  # le son, lui, n'a pas bougé


@pytest.mark.asyncio
async def test_une_voix_sans_minutage_donne_un_son_sans_mots():
    class _VoixMuette(_VoixMinutee):
        async def process_frame(self, frame, direction):
            if isinstance(frame, TTSSpeakFrame):
                await FrameProcessor.process_frame(self, frame, direction)
                await self.push_frame(TTSStartedFrame(context_id="c"))
                await self.push_frame(
                    TTSAudioRawFrame(audio=b"\x00\x01" * 1600, sample_rate=16000, num_channels=1, context_id="c")
                )
                await self.push_frame(TTSStoppedFrame(context_id="c"))
            else:
                await super().process_frame(frame, direction)

    appel = PipelineWorker(Pipeline([_Sortie()]), name="call", enable_rtvi=False)
    runner = create_worker_runner()
    tache = asyncio.create_task(run_worker_runner(runner, appel))
    try:
        while appel.started_at is None:
            await asyncio.sleep(0.01)
        fabrique = FabriqueDesSons(
            creer_la_voix=lambda: _VoixMuette({}), ajouter_le_circuit=appel.add_workers, taux_attendu=16000
        )
        fabrique.lancer(["Un instant."])
        await asyncio.wait_for(fabrique.attendre(), 30)
        assert fabrique.sons["Un instant."].mots == ()
    finally:
        await appel.cancel()
        await asyncio.gather(tache, return_exceptions=True)


# --------------------------------------------------------------------------- #
# De la phrase dite à la copie envoyée au modèle
# --------------------------------------------------------------------------- #


class _Parole:
    """Une lecture : ``ecoule`` secondes jouées avant la coupure (``None`` : jouée jusqu'au bout)."""

    def __init__(self, texte, ecoule):
        self.text = texte
        interrompue = ecoule is not None
        self.outcome = SimpleNamespace(name="INTERRUPTED" if interrompue else "PLAYED")
        self.started_at = 100.0
        self.ended_at = 100.0 + (ecoule if interrompue else 30.0)

    async def wait(self):
        return True


def _messages(texte: str = TEXTE) -> list[dict]:
    resultat = {"status": "echec", "compte_rendu": compte_rendu("un outil a échoué", dit=texte)}
    return [
        {"role": "system", "content": "Tu es l'agent."},
        {"role": "user", "content": "Prenez un rendez-vous."},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function"}]},
        {"role": "tool", "tool_call_id": "c1", "content": json.dumps(resultat, ensure_ascii=False)},
        {"role": "assistant", "content": texte},
        {"role": "user", "content": "D'accord, mais c'est urgent !"},
    ]


async def _dire(voix: str, ecoule: float | None, *, avec_minutage: bool = True):
    """La phrase passe par la VRAIE route : fabrique (circuit Pipecat), diseur, registre, modèle branché.
    Rend (moteur, requête reçue par le service, messages d'origine)."""
    fabrique = await _fabriquer(voix)
    if not avec_minutage:
        fabrique.sons[TEXTE] = Son(audio=fabrique.sons[TEXTE].audio, taux=16000)
    moteur = _FauxMoteur(lambda: 0.0)

    async def queue_speech(texte=None, **options):
        return _Parole(texte or options.get("transcript"), ecoule)

    moteur.queue_speech = queue_speech
    moteur.fabrique_des_sons = fabrique
    moteur.phrases = DiseurDePhrases(moteur)
    parole = await moteur.phrases.dire_la_parole(OUTIL_ECHOUE)
    assert parole is not None
    moteur.phrases.coupures.marquer_compte_rendu(parole)  # comme `signaler_un_probleme`
    await moteur.phrases.attendre_la_fin()
    origine = _messages()
    recus = []

    class _Modele:
        def build_chat_completion_params(self, params_from_context):
            recus.append(params_from_context)
            return {"model": "m", "messages": copy.deepcopy(origine)}

    llm = _Modele()
    assert brancher_les_coupures(moteur, llm) is True
    return moteur, llm.build_chat_completion_params(object()), origine


def _le_resultat(params) -> dict:
    return json.loads(next(m for m in params["messages"] if m.get("role") == "tool")["content"])


@pytest.mark.asyncio
@pytest.mark.parametrize("voix", sorted(VOIX))
async def test_coupee_avant_le_premier_mot_l_appelant_n_a_rien_entendu(voix):
    _, params, origine = await _dire(voix, ecoule=0.02)
    compte = _le_resultat(params)["compte_rendu"]
    assert LIGNE_RIEN in compte
    assert "L'appelant a entendu" not in compte and TEXTE not in compte
    # La ligne n'est pas retirée : elle dit autre chose, et le reste du compte rendu est intact.
    assert compte.startswith("[Ce qui vient de se passer : un outil a échoué.")
    # La réplique de l'agent, juste derrière le résultat : une ligne, jamais un message de l'appelant après un résultat.
    roles = [m["role"] for m in params["messages"]]
    assert roles == ["system", "user", "assistant", "tool", "assistant", "user"]
    assert params["messages"][4]["content"] == REPLIQUE_RIEN
    assert params["messages"][5] == origine[5]


@pytest.mark.asyncio
@pytest.mark.parametrize("voix", sorted(VOIX))
async def test_coupee_au_milieu_le_modele_lit_la_part_jouee(voix):
    # 0,1 + 0,25 * i : le quatrième mot (« demande, ») commence à 0,85 s, le cinquième (« on ») à 1,10 s.
    _, params, origine = await _dire(voix, ecoule=0.9)
    attendu = " ".join(TEXTE.split()[:4])
    resultat = _le_resultat(params)
    assert f"« {attendu} »" in resultat["compte_rendu"]
    assert "Ne la répète pas" not in resultat["compte_rendu"]
    assert params["messages"][4]["content"] == attendu  # l'historique ramené au dernier mot joué
    assert TEXTE not in json.dumps(params["messages"], ensure_ascii=False)
    # Le reste de la requête, et l'original, sont intacts.
    assert params["messages"][:3] == origine[:3] and params["messages"][5] == origine[5]


@pytest.mark.asyncio
@pytest.mark.parametrize("voix", sorted(VOIX))
async def test_coupee_apres_le_dernier_mot_rien_ne_change(voix):
    _, params, origine = await _dire(voix, ecoule=60.0)
    assert params["messages"] == origine
    assert ligne_entendue(TEXTE) in _le_resultat(params)["compte_rendu"]


@pytest.mark.asyncio
async def test_jouee_en_entier_rien_ne_change():
    _, params, origine = await _dire("elevenlabs", ecoule=None)
    assert params["messages"] == origine


@pytest.mark.asyncio
async def test_coupee_sans_minutage_la_copie_dit_qu_on_ne_sait_pas_jusqu_ou():
    _, params, origine = await _dire("elevenlabs", ecoule=1.0, avec_minutage=False)
    compte = _le_resultat(params)["compte_rendu"]
    assert "On ne sait pas jusqu'où il l'a entendue." in compte and TEXTE in compte
    assert "Ne la répète pas" not in compte
    # L'historique est celui que Pipecat a écrit : on n'y touche pas sans savoir.
    assert params["messages"][4] == origine[4]


@pytest.mark.asyncio
async def test_l_original_n_est_jamais_modifie_et_la_ligne_n_est_jamais_retiree():
    registre = RegistreDesCoupures()
    parole = _Parole(TEXTE, 0.02)
    registre.noter(TEXTE, tuple(_mots_elevenlabs(TEXTE)), parole)
    registre.marquer_compte_rendu(parole)
    origine = _messages()
    figee = copy.deepcopy(origine)
    params = reecrire_les_coupures({"messages": origine}, registre)
    assert origine == figee  # aucun message de l'historique modifié
    assert any("L'appelant" in m.get("content", "") for m in params["messages"] if m.get("role") == "tool")


def test_coupee_hors_d_un_resultat_la_replique_disparait_comme_pour_la_voix_normale():
    registre = RegistreDesCoupures()
    registre.noter(TEXTE, tuple(_mots_elevenlabs(TEXTE)), _Parole(TEXTE, 0.02))
    messages = [
        {"role": "user", "content": "Bonjour."},
        {"role": "assistant", "content": TEXTE},
        {"role": "user", "content": "Attendez !"},
    ]
    params = reecrire_les_coupures({"messages": messages}, registre)
    assert [m["role"] for m in params["messages"]] == ["user", "user"]


def test_le_format_responses_est_couvert():
    registre = RegistreDesCoupures()
    parole = _Parole(TEXTE, 0.9)
    registre.noter(TEXTE, tuple(_mots_elevenlabs(TEXTE)), parole)
    registre.marquer_compte_rendu(parole)
    attendu = " ".join(TEXTE.split()[:4])
    sortie = json.dumps({"compte_rendu": compte_rendu("un fait", dit=TEXTE)}, ensure_ascii=False)
    entree = [
        {"type": "function_call_output", "call_id": "c1", "output": sortie},
        {"role": "assistant", "content": [{"type": "output_text", "text": TEXTE}]},
        {"role": "user", "content": [{"type": "input_text", "text": "Attendez."}]},
    ]
    params = reecrire_les_coupures({"input": entree}, registre)
    assert f"« {attendu} »" in params["input"][0]["output"]
    assert params["input"][1]["content"][0]["text"] == attendu
    assert params["input"][2] == entree[2]


def test_sans_phrase_coupee_la_requete_part_comme_avant():
    registre = RegistreDesCoupures()
    params = {"messages": _messages()}
    assert reecrire_les_coupures(params, registre) is params
    assert reecrire_les_coupures(params, None) is params
    registre.noter(TEXTE, tuple(_mots_elevenlabs(TEXTE)), _Parole(TEXTE, None))  # jouée en entier
    messages = params["messages"]
    assert reecrire_les_coupures(params, registre)["messages"] is messages
    # Coupée après le dernier mot : « tout », même objet.
    registre.noter(TEXTE, tuple(_mots_elevenlabs(TEXTE)), _Parole(TEXTE, 99.0))
    assert reecrire_les_coupures(params, registre)["messages"] is messages


# --------------------------------------------------------------------------- #
# La lecture est datée (suivi réel des lectures) et le branchement est posé
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_le_suivi_des_lectures_date_le_debut_et_la_coupure():
    suivi = SpeechPlaybackTracker()
    parole = suivi.create()
    assert parole.started_at is None and parole.ended_at is None
    suivi.after_output(None, SpeechBoundaryFrame(parole.id, beginning=True))
    assert parole.started_at is not None
    await suivi.before_output(None, InterruptionFrame())
    assert parole.outcome is PlaybackOutcome.INTERRUPTED
    assert parole.ended_at is not None and parole.ended_at >= parole.started_at
    # Le registre lit cette vraie lecture : le premier mot à 0 s est joué, le second à 30 s ne l'est pas.
    registre = RegistreDesCoupures()
    registre.noter("Un instant, s'il vous plaît.", (("Un", 0.0), ("instant,", 30.0)), parole)
    (coupure,) = registre.coupees()
    assert coupure.partie.etat == ETAT_DEBUT and coupure.partie.joue == "Un"


@pytest.mark.asyncio
async def test_coupee_avant_le_debut_de_la_lecture_rien_n_est_entendu():
    suivi = SpeechPlaybackTracker()
    parole = suivi.create()
    await suivi.before_output(None, InterruptionFrame())  # la sortie n'a jamais laissé passer le début
    assert parole.started_at is None
    registre = RegistreDesCoupures()
    registre.noter(TEXTE, tuple(_mots_elevenlabs(TEXTE)), parole)
    assert [c.partie.etat for c in registre.coupees()] == [ETAT_RIEN]


def test_la_reecriture_est_posee_sur_chaque_modele_avant_la_trace():
    """R1 : un branchement perdu éteindrait D20 en silence (l'appel continuerait normalement)."""
    for chemin, appel_trace in (
        ("services/pipecat/run_pipeline.py", "brancher_la_trace(engine, llm"),
        ("services/pipecat/agent_runtime_factory.py", "brancher_la_trace(self._moteur_de_l_appel(), llm"),
    ):
        source = (RACINE / chemin).read_text(encoding="utf-8")
        assert "brancher_les_coupures(" in source, chemin
        assert source.index("brancher_les_coupures(") < source.index(appel_trace), chemin


def test_le_branchement_ne_se_pose_qu_une_fois_et_sans_diseur_il_ne_fait_rien():
    moteur = SimpleNamespace(phrases=DiseurDePhrases(_FauxMoteur(lambda: 0.0)))
    appels = []

    class _Modele:
        def build_chat_completion_params(self, params):
            appels.append(params)
            return {"messages": []}

    llm = _Modele()
    assert brancher_les_coupures(moteur, llm) is True
    assert brancher_les_coupures(moteur, llm) is False
    llm.build_chat_completion_params("x")
    assert appels == ["x"]  # une seule couche
    assert brancher_les_coupures(SimpleNamespace(), _Modele()) is False
    assert brancher_les_coupures(moteur, None) is False


# --------------------------------------------------------------------------- #
# Revue M2 : la même phrase dite deux fois, une seule coupure
# --------------------------------------------------------------------------- #


def _messages_deux_fois(texte: str = TEXTE) -> list[dict]:
    """Deux tours qui portent la même phrase : un résultat d'outil avec son compte rendu, puis la réplique."""
    tours = []
    for k in (1, 2):
        resultat = {"status": "echec", "compte_rendu": compte_rendu(f"fait {k}", dit=texte)}
        tours += [
            {"role": "assistant", "content": None, "tool_calls": [{"id": f"c{k}", "type": "function"}]},
            {"role": "tool", "tool_call_id": f"c{k}", "content": json.dumps(resultat, ensure_ascii=False)},
            {"role": "assistant", "content": texte},
            {"role": "user", "content": f"Réponse {k}"},
        ]
    return [{"role": "system", "content": "Tu es l'agent."}, *tours]


async def _dire_deux_fois(voix: str, ecoules: list):
    """La même phrase dite deux fois par la vraie route (fabrique, diseur, registre), la n-ième lecture coupée
    après ``ecoules[n]`` secondes (``None`` : entendue en entier). Rend la requête reçue par le service."""
    fabrique = await _fabriquer(voix)
    moteur = _FauxMoteur(lambda: 0.0)
    lectures = iter(ecoules)

    async def queue_speech(texte=None, **options):
        return _Parole(texte or options.get("transcript"), next(lectures))

    moteur.queue_speech = queue_speech
    moteur.fabrique_des_sons = fabrique
    moteur.phrases = DiseurDePhrases(moteur)
    for _ in ecoules:
        parole = await moteur.phrases.dire_la_parole(OUTIL_ECHOUE)
        assert parole is not None
        moteur.phrases.coupures.marquer_compte_rendu(parole)
        await moteur.phrases.attendre_la_fin()
    origine = _messages_deux_fois()

    class _Modele:
        def build_chat_completion_params(self, params_from_context):
            return {"model": "m", "messages": copy.deepcopy(origine)}

    llm = _Modele()
    assert brancher_les_coupures(moteur, llm) is True
    return llm.build_chat_completion_params(object())["messages"], origine


def _compte(messages, rang):
    """Le compte rendu du ``rang``-ième résultat d'outil (0 ou 1)."""
    resultats = [m for m in messages if m.get("role") == "tool"]
    return json.loads(resultats[rang]["content"])["compte_rendu"]


@pytest.mark.asyncio
@pytest.mark.parametrize("voix", sorted(VOIX))
async def test_deux_fois_la_meme_phrase_seule_la_seconde_coupee(voix):
    messages, origine = await _dire_deux_fois(voix, [None, 0.02])
    # Le tour 1, entendu en entier, est à l'octet ce qu'il était : ligne, réplique, tout.
    assert messages[1:5] == origine[1:5]
    assert ligne_entendue(TEXTE) in _compte(messages, 0)
    # Le tour 2, coupé avant le premier mot : ligne réécrite, réplique remplacée derrière le résultat.
    assert LIGNE_RIEN in _compte(messages, 1) and "L'appelant a entendu" not in _compte(messages, 1)
    assert messages[7]["content"] == REPLIQUE_RIEN
    assert messages[8] == origine[8]


@pytest.mark.asyncio
@pytest.mark.parametrize("voix", sorted(VOIX))
async def test_deux_fois_la_meme_phrase_seule_la_premiere_coupee(voix):
    messages, origine = await _dire_deux_fois(voix, [0.9, None])
    attendu = " ".join(TEXTE.split()[:4])
    assert f"« {attendu} »" in _compte(messages, 0)
    assert messages[3]["content"] == attendu
    # Le tour 2, entendu en entier, reste intact.
    assert messages[5:9] == origine[5:9]
    assert ligne_entendue(TEXTE) in _compte(messages, 1)


@pytest.mark.asyncio
async def test_deux_fois_la_meme_phrase_les_deux_coupees_chacune_a_sa_part():
    messages, _ = await _dire_deux_fois("elevenlabs", [0.9, 0.02])
    attendu = " ".join(TEXTE.split()[:4])
    assert f"« {attendu} »" in _compte(messages, 0) and messages[3]["content"] == attendu
    assert LIGNE_RIEN in _compte(messages, 1) and messages[7]["content"] == REPLIQUE_RIEN


@pytest.mark.asyncio
async def test_une_phrase_sans_ligne_de_compte_rendu_ne_decale_pas_les_autres():
    """Une lecture qui n'a pas de ligne dans un résultat (phrase d'attente) ne prend pas la place d'une ligne."""
    registre = RegistreDesCoupures()
    attente = _Parole(TEXTE, None)  # entendue, sans ligne de compte rendu
    registre.noter(TEXTE, tuple(_mots_elevenlabs(TEXTE)), attente)
    coupee = _Parole(TEXTE, 0.02)
    registre.noter(TEXTE, tuple(_mots_elevenlabs(TEXTE)), coupee)
    registre.marquer_compte_rendu(coupee)
    resultat = {"compte_rendu": compte_rendu("un fait", dit=TEXTE)}
    messages = [
        {"role": "tool", "tool_call_id": "c", "content": json.dumps(resultat, ensure_ascii=False)},
        {"role": "assistant", "content": TEXTE},
        {"role": "user", "content": "Attendez."},
    ]
    sortie = reecrire_les_coupures({"messages": messages}, registre)["messages"]
    assert LIGNE_RIEN in json.loads(sortie[0]["content"])["compte_rendu"]
