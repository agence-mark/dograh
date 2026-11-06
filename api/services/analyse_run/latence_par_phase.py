"""[.mark] Builder partie 3, N3a : la latence par PHASE (transcription, modèle, outils, voix), par tour, par étape et par appel.

R9 (« ce que Pipecat fournit déjà ») : rien n'est mesuré ici. Pipecat mesure déjà, par tour, le premier octet de chaque service
(``UserBotLatencyObserver`` : ``ttfb`` de la transcription, du modèle et de la voix) et le temps de chaque appel d'outil
(``function_calls``) ; le fork en écrit déjà chaque tour dans le journal du run (``mark-latency-breakdown``, ``run_pipeline.py``), avec
l'étape en cours. Ce module LIT ce journal : il ne branche aucun observateur de plus et n'ajoute rien au chemin de l'appel. La famille d'un
service se décide par ``ttfb_kind`` (celui de l'amont, qui connaît le piège « STTService contient TTS »), jamais par une sous-chaîne.

| Phase | Ce qui la mesure | Un tour sans cette mesure |
|---|---|---|
| transcription | le plus long premier octet d'un service de transcription du tour | phase absente (pas de zéro inventé) |
| modèle | le plus long premier octet du modèle (la passe la plus lente d'un tour à outils) | absente |
| outils | la SOMME des durées d'appels d'outils du tour | absente quand aucun outil n'a tourné |
| voix | le plus long premier octet du service de voix | absente |

Un appel sans aucun tour mesuré (ancien appel, appel écrit, panne de l'observateur) rend ``None`` : l'écran dit « non mesuré ».
"""

from __future__ import annotations

import statistics
from typing import Any

from api.services.observability.call_events.metrics import ttfb_kind

PHASES = ("transcription", "modele", "outils", "voix")
_FAMILLE_DU_SERVICE = {"stt": "transcription", "llm": "modele", "tts": "voix"}
TYPE_DU_JOURNAL = "mark-latency-breakdown"


def _ms(secondes: Any) -> float | None:
    if isinstance(secondes, bool) or not isinstance(secondes, (int, float)) or secondes < 0:
        return None
    return round(float(secondes) * 1000.0, 1)


def phases_du_tour(detail: dict[str, Any]) -> dict[str, float]:
    """Les phases mesurées d'un tour, en millisecondes ; une phase sans mesure n'y figure pas."""
    pires: dict[str, float] = {}
    for mesure in detail.get("ttfb") or []:
        if not isinstance(mesure, dict):
            continue
        phase = _FAMILLE_DU_SERVICE.get(ttfb_kind(str(mesure.get("processor") or "")) or "")
        valeur = _ms(mesure.get("duration_secs"))
        if phase and valeur is not None and valeur > pires.get(phase, -1.0):
            pires[phase] = valeur
    outils = [_ms(f.get("duration_secs")) for f in detail.get("function_calls") or [] if isinstance(f, dict)]
    outils = [v for v in outils if v is not None]
    if outils:
        pires["outils"] = round(sum(outils), 1)
    return pires


def latence_des_tours(evenements: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Une ligne par tour mesuré : étape, phases, total (la somme des phases mesurées)."""
    tours: list[dict[str, Any]] = []
    for e in evenements or []:
        if not isinstance(e, dict) or e.get("type") != TYPE_DU_JOURNAL:
            continue
        phases = phases_du_tour(e.get("payload") if isinstance(e.get("payload"), dict) else {})
        if not phases:
            continue
        tours.append(
            {
                "tour": e.get("turn"),
                "etape": str(e.get("node_name") or ""),
                "phases": phases,
                "total_ms": round(sum(phases.values()), 1),
            }
        )
    return tours


def _stats(valeurs: list[float]) -> dict[str, float]:
    return {"moyenne_ms": round(statistics.fmean(valeurs), 1), "pire_ms": round(max(valeurs), 1)}


def _bloc(tours: list[dict[str, Any]]) -> dict[str, Any]:
    phases = {}
    for phase in PHASES:
        valeurs = [t["phases"][phase] for t in tours if phase in t["phases"]]
        if valeurs:
            phases[phase] = {**_stats(valeurs), "tours": len(valeurs)}
    return {"tours": len(tours), "total": _stats([t["total_ms"] for t in tours]), "phases": phases}


def resume_de_latence(evenements: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Moyenne et pire cas, par appel et par étape. ``None`` : rien n'a été mesuré (« non mesuré », jamais zéro)."""
    tours = latence_des_tours(evenements)
    if not tours:
        return None
    par_etape: dict[str, list[dict[str, Any]]] = {}
    for t in tours:
        par_etape.setdefault(t["etape"], []).append(t)
    return {**_bloc(tours), "par_etape": {nom: _bloc(ts) for nom, ts in par_etape.items() if nom}}


def champs(annotations: Any) -> dict[str, Any]:
    """Pour une ligne de la liste des appels : la latence rangée à la fin de l'appel (annotation ``latence``), ou ``None``."""
    brut = annotations.get("latence") if isinstance(annotations, dict) else None
    total = brut.get("total") if isinstance(brut, dict) else None
    if not isinstance(total, dict) or not isinstance(total.get("moyenne_ms"), (int, float)):
        return {"latence": None}
    return {"latence": {"moyenne_ms": total["moyenne_ms"], "pire_ms": total.get("pire_ms"), "tours": brut.get("tours")}}
