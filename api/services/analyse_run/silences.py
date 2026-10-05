"""Le silence RÉELLEMENT entendu par l'appelant (.mark, langwatch-et-fenetre-du-run, lot 2, étape 4).

Décision L4 (question n° 286 du labo) : on ne mesurait que « transcription finale → premier
texte de l'agent ». Ce que l'appelant vit, c'est autre chose : la fin de SA parole jusqu'au premier
SON de l'agent, attente de fin de tour, modèle et voix compris.

Calcul après l'appel, sur les deux pistes séparées (appelant, agent), alignées depuis le début de
l'enregistrement : la parole de chaque piste est repérée par Silero (le détecteur de voix que
Pipecat embarque déjà), puis chaque prise de parole de l'agent est rapprochée de la dernière fin de
parole de l'appelant qui la précède. Résultat dans ``gathered_context.mark_silences``.

⛔ Ne fait jamais tomber la fin d'un appel : lancé en tâche à part, toute erreur est écrite
(« unavailable ») et journalisée.
"""

from __future__ import annotations

import asyncio
import io
import wave
from collections.abc import Callable
from typing import Any

import numpy as np
from loguru import logger

CLE_SILENCES = "mark_silences"

SEUIL_PAROLE = (
    0.5  # confiance de Silero au-delà de laquelle une fenêtre est de la parole
)
PAUSE_MIN_S = 0.3  # deux paroles séparées de moins que ça n'en font qu'une
PAROLE_MIN_S = 0.12  # une « parole » plus courte est un bruit
TAUX_SILERO = (16000, 8000)

Confiance = Callable[[bytes], float]


def _lire_wav(octets: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(octets), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError("piste non PCM 16 bits")
        canaux = w.getnchannels()
        taux = w.getframerate()
        donnees = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    if canaux > 1:
        donnees = donnees.reshape(-1, canaux).mean(axis=1).astype(np.int16)
    return donnees, taux


def _au_taux_de_silero(echantillons: np.ndarray, taux: int) -> tuple[np.ndarray, int]:
    """Silero ne lit que 16 kHz ou 8 kHz : décimation entière, sinon refus explicite."""
    for cible in TAUX_SILERO:
        if taux % cible == 0:
            pas = taux // cible
            return echantillons[::pas].copy(), cible
    raise ValueError(f"taux d'échantillonnage {taux} Hz non pris en charge")


def _confiance_silero(taux: int) -> tuple[Confiance, int]:
    from pipecat.audio.vad.silero import SileroVADAnalyzer

    analyseur = SileroVADAnalyzer(sample_rate=taux)
    analyseur.set_sample_rate(taux)
    return analyseur.voice_confidence, analyseur.num_frames_required()


def segments_de_parole(
    echantillons: np.ndarray,
    taux: int,
    *,
    confiance: Confiance | None = None,
    fenetre: int | None = None,
) -> list[tuple[float, float]]:
    """Les moments de parole d'une piste, en secondes depuis son début."""
    if confiance is None:
        confiance, fenetre = _confiance_silero(taux)
    fenetre = fenetre or 512
    duree_fenetre = fenetre / taux
    segments: list[list[float]] = []
    for i in range(0, len(echantillons) - fenetre + 1, fenetre):
        if confiance(echantillons[i : i + fenetre].tobytes()) < SEUIL_PAROLE:
            continue
        debut = i / taux
        if segments and debut - segments[-1][1] < PAUSE_MIN_S:
            segments[-1][1] = debut + duree_fenetre
        else:
            segments.append([debut, debut + duree_fenetre])
    return [(round(d, 3), round(f, 3)) for d, f in segments if f - d >= PAROLE_MIN_S]


def rapprocher(
    appelant: list[tuple[float, float]], agent: list[tuple[float, float]]
) -> list[dict]:
    """Chaque prise de parole de l'agent qui répond à l'appelant : la dernière fin de parole de
    l'appelant avant elle, et après la parole précédente de l'agent. Une réponse qui commence
    pendant que l'appelant parle encore n'est pas un silence : elle est écartée."""
    paires = []
    fin_agent_precedente = 0.0
    for debut_agent, fin_agent in agent:
        fins = [
            fin for debut, fin in appelant if fin_agent_precedente <= fin <= debut_agent
        ]
        chevauche = any(debut < debut_agent < fin for debut, fin in appelant)
        if fins and not chevauche:
            paires.append(
                {
                    "caller_end_secs": fins[-1],
                    "agent_start_secs": debut_agent,
                    "silence_secs": round(debut_agent - fins[-1], 3),
                }
            )
        fin_agent_precedente = fin_agent
    return paires


def silences_percus(
    piste_appelant: bytes,
    piste_agent: bytes,
    *,
    confiance: Callable[[int], tuple[Confiance, int]] | None = None,
) -> dict:
    """Le bilan rangé dans ``mark_silences``."""
    pistes = []
    for octets in (piste_appelant, piste_agent):
        echantillons, taux = _au_taux_de_silero(*_lire_wav(octets))
        lecteur, fenetre = (confiance or _confiance_silero)(taux)
        pistes.append(
            segments_de_parole(echantillons, taux, confiance=lecteur, fenetre=fenetre)
        )
    paires = rapprocher(*pistes)
    valeurs = sorted(p["silence_secs"] for p in paires)
    return {
        "status": "ok",
        "method": "silero",
        "pairs": paires,
        "count": len(valeurs),
        "median_secs": valeurs[(len(valeurs) - 1) // 2] if valeurs else None,
        "worst_secs": valeurs[-1] if valeurs else None,
    }


async def noter_les_silences(
    workflow_run_id: int,
    piste_appelant: bytes | None,
    piste_agent: bytes | None,
    db: Any,
) -> None:
    """Calcule hors de la boucle (détection de voix = calcul) et écrit le bilan au run."""
    if not piste_appelant or not piste_agent:
        return
    try:
        bilan = await asyncio.to_thread(silences_percus, piste_appelant, piste_agent)
    except Exception as erreur:  # noqa: BLE001 — R1 : un calcul en échec se voit à l'écran
        logger.warning(
            f"[captures] silences du run {workflow_run_id} non calculés : {erreur!r}"
        )
        bilan = {"status": "unavailable", "reason": type(erreur).__name__}
    try:
        await db.update_workflow_run(
            run_id=workflow_run_id, gathered_context={CLE_SILENCES: bilan}
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(
            f"[captures] silences du run {workflow_run_id} non écrits : {erreur!r}"
        )


# Les calculs en cours : une tâche sans référence peut être ramassée avant sa fin.
_EN_COURS: set[asyncio.Task] = set()


def lancer_le_calcul_des_silences(
    workflow_run_id: int,
    piste_appelant: bytes | None,
    piste_agent: bytes | None,
    db: Any,
) -> asyncio.Task | None:
    """Appelée en fin d'appel, après l'envoi des pistes : ne retarde ni l'envoi ni la suite."""
    if not piste_appelant or not piste_agent:
        return None
    tache = asyncio.create_task(
        noter_les_silences(workflow_run_id, piste_appelant, piste_agent, db)
    )
    _EN_COURS.add(tache)
    tache.add_done_callback(_EN_COURS.discard)
    return tache
