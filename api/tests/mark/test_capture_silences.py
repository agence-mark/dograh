"""[.mark] Le silence réellement entendu par l'appelant (chantier langwatch-et-fenetre-du-run,
lot 2, étape 4, décision L4).

Questions :
1. Sur deux pistes alignées, l'agent répondant 0,9 s après la fin de la phrase de l'appelant,
   le calcul (vrai Silero, vraie parole) rend-il ≈ 0,9 s ?
2. Une réponse qui commence pendant que l'appelant parle encore est-elle écartée ?
3. Une piste illisible donne-t-elle « unavailable » au run, sans lever ?
4. Le calcul est-il lancé en fin d'appel, après l'envoi des pistes, avec les deux pistes ?

Les deux phrases sont fabriquées par la synthèse vocale de Windows (voix « Hortense », 16 kHz) :
aucune voix réelle, aucune donnée personnelle.
"""

import inspect
import io
import wave
from pathlib import Path
from unittest.mock import AsyncMock

import numpy as np
import pytest

from api.services.analyse_run.analyse import analyser_run
from api.services.analyse_run.silences import (
    CLE_SILENCES,
    _lire_wav,
    noter_les_silences,
    rapprocher,
    silences_percus,
)
from api.services.pipecat import event_handlers

DONNEES = Path(__file__).parent / "donnees"
TAUX = 16000


def _phrase(nom: str) -> np.ndarray:
    return _lire_wav((DONNEES / f"silences_{nom}_2026-10-05.wav").read_bytes())[0]


def _wav(echantillons: np.ndarray, taux: int = TAUX) -> bytes:
    sortie = io.BytesIO()
    with wave.open(sortie, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taux)
        w.writeframes(echantillons.astype(np.int16).tobytes())
    return sortie.getvalue()


def _pistes(decalage_agent_s: float) -> tuple[bytes, bytes]:
    """Piste appelant : 0,5 s de silence puis sa phrase. Piste agent : silence jusqu'à
    ``decalage_agent_s`` puis sa phrase. Même longueur, comme les pistes de l'enregistreur."""
    appelant = np.concatenate([np.zeros(int(0.5 * TAUX)), _phrase("appelant")])
    agent = np.concatenate([np.zeros(int(decalage_agent_s * TAUX)), _phrase("agent")])
    longueur = max(len(appelant), len(agent)) + TAUX
    appelant = np.pad(appelant, (0, longueur - len(appelant)))
    agent = np.pad(agent, (0, longueur - len(agent)))
    return _wav(appelant), _wav(agent)


def test_le_silence_entendu_est_mesure_sur_de_la_vraie_parole():
    # Mesuré sur ces phrases : l'appelant finit de parler à 0,5 + 2,848 s ; la parole de
    # l'agent commence 0,352 s après le début de sa phrase. Réponse voulue 0,9 s après.
    decalage = 0.5 + 2.848 + 0.9 - 0.352
    bilan = silences_percus(*_pistes(decalage))
    assert bilan["status"] == "ok"
    assert bilan["count"] == 1
    assert abs(bilan["median_secs"] - 0.9) <= 0.1, bilan


def test_une_reponse_par_dessus_l_appelant_est_ecartee():
    bilan = silences_percus(*_pistes(1.5))  # l'agent démarre en pleine phrase
    assert bilan["count"] == 0
    assert bilan["median_secs"] is None


def test_le_rapprochement_prend_la_derniere_fin_de_parole_avant_la_reponse():
    appelant = [(0.0, 1.0), (1.4, 2.0), (5.0, 6.0)]
    agent = [(2.7, 4.0), (6.5, 7.0)]
    assert [p["silence_secs"] for p in rapprocher(appelant, agent)] == [0.7, 0.5]


def test_un_taux_que_silero_ne_lit_pas_est_ramene_a_16_ou_8_khz():
    appelant, agent = _pistes(4.0)
    a48 = _wav(np.repeat(_lire_wav(appelant)[0], 3), 48000)
    g48 = _wav(np.repeat(_lire_wav(agent)[0], 3), 48000)
    assert silences_percus(a48, g48)["count"] == 1


@pytest.mark.asyncio
async def test_une_piste_illisible_donne_indisponible_sans_lever():
    base = AsyncMock()
    await noter_les_silences(7, b"pas un wav", b"pas un wav", base)
    ecrit = base.update_workflow_run.await_args.kwargs["gathered_context"][CLE_SILENCES]
    assert ecrit["status"] == "unavailable"


@pytest.mark.asyncio
async def test_le_bilan_est_ecrit_dans_le_contexte_du_run():
    base = AsyncMock()
    await noter_les_silences(7, *_pistes(4.0), base)
    appel = base.update_workflow_run.await_args.kwargs
    assert appel["run_id"] == 7
    assert appel["gathered_context"][CLE_SILENCES]["status"] == "ok"


def test_la_fenetre_montre_le_silence_entendu_ou_non_capte():
    run = {
        "id": 1,
        "logs": {
            "realtime_feedback_events": [
                {
                    "type": "rtf-bot-text",
                    "turn": 1,
                    "timestamp": "2026-10-05T10:00:00.000+00:00",
                    "payload": {},
                }
            ]
        },
    }
    assert analyser_run(run)["latency"]["perceived"] == {"status": "not_captured"}
    run["gathered_context"] = {CLE_SILENCES: {"status": "ok", "median_secs": 1.2}}
    assert analyser_run(run)["latency"]["perceived"]["median_secs"] == 1.2


def test_le_calcul_est_lance_apres_l_envoi_des_pistes():
    source = inspect.getsource(event_handlers)
    envoi = source.index("await upload_workflow_run_artifacts(")
    calcul = source.index("lancer_le_calcul_des_silences(")
    file = source.index("FunctionNames.PROCESS_WORKFLOW_COMPLETION")
    assert envoi < calcul < file
    assert "workflow_run_id, user_audio_wav, bot_audio_wav, db_client" in source


def test_l_appelant_qui_reparle_quand_l_agent_demarre_n_est_pas_un_silence():
    """R7 : le cas « par-dessus » ci-dessus n'exerçait pas cette règle (aucune fin de parole
    avant la réponse) ; une mutation qui la retirait restait verte."""
    appelant = [(0.0, 1.0), (1.5, 3.0)]
    agent = [(2.0, 4.0)]
    assert rapprocher(appelant, agent) == []
