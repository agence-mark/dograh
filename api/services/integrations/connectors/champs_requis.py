"""[.mark] Les champs dont une action a besoin, résolus par le code (lot D d'agent-leger-greffier).

En mode greffier, le modèle de parole ne note rien et la fiche a un tour de retard. Une action
qui lit la fiche (le planificateur lit l'adresse) risquait de partir sans ce que la personne
vient de dire. Avant l'action, le code cherche chaque champ requis, dans cet ordre :

1. la **fiche** telle qu'elle est ;
2. les **traces** des modules de lecture, écrites au tour même (``fiche/traces.py``) : une
   valeur sûre y est prise pour l'action, sans être écrite dans la fiche (le greffier l'écrira,
   avec ses contrôles) ;
3. le **greffier**, à qui une passe est demandée et attendue, au plus ``attente_max_ms``.

Ce qui manque encore revient au modèle (« il manque X »), qui le demande à la personne.

La **phrase de patience** (D6) : celle de l'outil, vide par défaut ; dite par le code, derrière
le texte du modèle, seulement si l'outil n'a pas fini au bout de ``seuil_patience_ms`` (la
résolution et l'action comprises). Une seule fois.

Tout se règle sur l'outil (écran « Outils »), rien n'est écrit pour un métier : la preuve est
une fiche d'un autre métier, par simple réglage (``test_champs_requis_et_traces.py``).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from loguru import logger

from api.services.fiche.traces import valeurs_des_traces

ATTENTE_MAX_DEFAUT_MS = 2500
SEUIL_PATIENCE_DEFAUT_MS = 1200
SOURCES = ("fiche", "traces", "greffier")


def _vide(valeur: Any) -> bool:
    return valeur is None or valeur == "" or valeur == [] or valeur == {}


def _borne_ms(valeur: Any, defaut: int, plafond: int = 15000) -> float:
    try:
        ms = int(valeur) if valeur not in (None, "") else defaut
    except (TypeError, ValueError):
        ms = defaut
    return max(0, min(ms, plafond)) / 1000


@dataclass(frozen=True)
class Resolution:
    champs: tuple[str, ...]
    attente_max_s: float
    sources: tuple[str, ...]

    @classmethod
    def depuis(cls, config: dict) -> "Resolution":
        champs = config.get("champs_requis") or ()
        sources = tuple(
            s for s in (config.get("sources_champs") or SOURCES) if s in SOURCES
        )
        return cls(
            champs=tuple(str(c).strip() for c in champs if str(c).strip()),
            attente_max_s=_borne_ms(
                config.get("attente_max_ms"), ATTENTE_MAX_DEFAUT_MS
            ),
            sources=sources or SOURCES,
        )


def _manquants(
    resolution: Resolution, fiche: dict, complements: dict[str, str]
) -> list[str]:
    return [
        c for c in resolution.champs if _vide(fiche.get(c)) and c not in complements
    ]


def _des_traces(resolution: Resolution, reglages: Any, fiche: dict) -> dict[str, str]:
    if "traces" not in resolution.sources:
        return {}
    lues = valeurs_des_traces(reglages, fiche)
    return {c: lues[c] for c in resolution.champs if c in lues and _vide(fiche.get(c))}


async def resoudre(engine: Any, config: dict) -> tuple[dict[str, str], list[str]]:
    """(valeurs prises dans les traces pour l'action, champs encore manquants).
    Sans champ requis déclaré : ``({}, [])``, l'outil se joue comme avant. Ne lève jamais."""
    resolution = Resolution.depuis(config)
    fiche = getattr(engine, "_gathered_context", None)
    if not resolution.champs or not isinstance(fiche, dict):
        return {}, []
    reglages = getattr(engine, "fiche", None)
    try:
        complements = _des_traces(resolution, reglages, fiche)
        restants = _manquants(resolution, fiche, complements)
        greffier = getattr(engine, "greffier", None)
        if restants and "greffier" in resolution.sources and greffier is not None:
            await greffier.rattraper(resolution.attente_max_s)
            complements = _des_traces(resolution, reglages, fiche)
            restants = _manquants(resolution, fiche, complements)
        return complements, restants
    except Exception as erreur:  # noqa: BLE001 -- R1 : dit au journal, l'outil continue
        logger.error(f"[.mark] Required fields not resolved: {erreur!r}")
        return {}, list(resolution.champs)


class Patience:
    """La phrase de patience d'un outil (D6) : dite une fois, par le code, seulement si
    l'outil n'a pas fini au bout du seuil. Vide : rien n'est jamais dit."""

    def __init__(self, engine: Any, config: dict):
        self._engine = engine
        self._phrase = str(config.get("phrase_attente") or "").strip()
        self._seuil_s = _borne_ms(
            config.get("seuil_patience_ms"), SEUIL_PATIENCE_DEFAUT_MS
        )
        self._tache: asyncio.Task | None = None
        self.dite = False

    def demarrer(self) -> None:
        if self._phrase:
            self._tache = asyncio.get_running_loop().create_task(self._attendre())

    async def _attendre(self) -> None:
        await asyncio.sleep(self._seuil_s)
        self.dite = True
        await self._engine.queue_text_message(self._phrase, mute_user=True)

    def arreter(self) -> None:
        if self._tache is not None and not self._tache.done():
            self._tache.cancel()
