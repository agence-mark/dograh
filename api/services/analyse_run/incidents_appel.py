"""Coupures, interruptions et relances d'un appel (.mark, langwatch-et-fenetre-du-run, lot 2, étape 3).

Trois choses que le run ne gardait pas :

- les **coupures** de la transcription et de la voix : Pipecat annonce chaque connexion, déconnexion
  et erreur de connexion d'un service (``on_connected``, ``on_disconnected``,
  ``on_connection_error``) ; ``brancher_les_connexions`` les écoute et les écrit au journal du run
  (``mark-provider-connection``). La première connexion et la dernière déconnexion d'un appel sont
  normales : c'est l'analyse qui les écarte ;
- les **interruptions** : l'appelant parle pendant que l'agent parle et Pipecat coupe l'agent.
  ``ObservateurDesInterruptions`` voit passer les trames et note chaque interruption faite
  PENDANT que l'agent parle ET que l'appelant parle (``mark-caller-interrupted``), pas celles que le
  moteur provoque lui-même hors de toute parole ;
- les **relances d'inactivité** : ``noter_la_relance`` est appelée par ``handle_user_idle``
  (``mark-user-idle``, numéro de la relance, raccrochage ou non).

⛔ Rien ici ne fait tomber un appel : chaque écriture est gardée, un échec va au journal.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    InterruptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed

TYPE_CONNEXION = "mark-provider-connection"
TYPE_INTERRUPTION = "mark-caller-interrupted"
TYPE_RELANCE = "mark-user-idle"

EVENEMENTS_DE_CONNEXION = {
    "on_connected": "connected",
    "on_disconnected": "disconnected",
    "on_connection_error": "error",
}

# Le nom de l'attribut du moteur qui porte le journal du run (posé par ``run_pipeline``).
ATTRIBUT_JOURNAL = "journal_du_run"


async def _ecrire(journal: Any, evenement: dict) -> None:
    if journal is None:
        return
    try:
        await journal.append(evenement)
    except Exception as erreur:  # noqa: BLE001 — une mesure n'emporte pas l'appel
        logger.warning(
            f"[captures] événement {evenement.get('type')} non noté : {erreur!r}"
        )


def brancher_les_connexions(services: dict[str, Any], journal: Any) -> list[str]:
    """Écoute les connexions de chaque service (``{"transcription": stt, "voice": tts}``) ;
    rend les briques effectivement écoutées."""
    ecoutes = []
    for brique, service in services.items():
        if service is None:
            continue
        gestionnaires = getattr(service, "_event_handlers", None)
        for evenement, nom in EVENEMENTS_DE_CONNEXION.items():
            if not isinstance(gestionnaires, dict) or evenement not in gestionnaires:
                continue

            async def ecouter(_service, *args, _nom=nom, _brique=brique):
                await _ecrire(
                    journal,
                    {
                        "type": TYPE_CONNEXION,
                        "payload": {
                            "component": _brique,
                            "service": type(_service).__name__,
                            "event": _nom,
                            "error": str(args[0]) if args else None,
                        },
                    },
                )

            service.add_event_handler(evenement, ecouter)
            if brique not in ecoutes:
                ecoutes.append(brique)
        if brique not in ecoutes:
            logger.warning(
                f"[captures] coupures de {brique} non captées : "
                f"{type(service).__name__} n'annonce pas ses connexions"
            )
    return ecoutes


class ObservateurDesInterruptions(BaseObserver):
    """Note chaque interruption de l'agent par l'appelant."""

    def __init__(self, journal: Any):
        super().__init__()
        self._journal = journal
        self._vues: set[int] = set()
        self._agent_parle = False
        self._appelant_parle = False

    async def on_push_frame(self, data: FramePushed):
        trame = data.frame
        # Une trame passe par chaque processeur : on ne la compte qu'une fois.
        if trame.id in self._vues:
            return
        self._vues.add(trame.id)
        if isinstance(trame, BotStartedSpeakingFrame):
            self._agent_parle = True
        elif isinstance(trame, BotStoppedSpeakingFrame):
            self._agent_parle = False
        elif isinstance(trame, UserStartedSpeakingFrame):
            self._appelant_parle = True
        elif isinstance(trame, UserStoppedSpeakingFrame):
            self._appelant_parle = False
        elif isinstance(trame, InterruptionFrame):
            if self._agent_parle and self._appelant_parle:
                await _ecrire(self._journal, {"type": TYPE_INTERRUPTION, "payload": {}})


async def noter_la_relance(engine: Any, numero: int, raccroche: bool) -> None:
    """Appelée par ``handle_user_idle`` : une relance de l'appelant silencieux."""
    await _ecrire(
        getattr(engine, ATTRIBUT_JOURNAL, None),
        {"type": TYPE_RELANCE, "payload": {"attempt": numero, "hang_up": raccroche}},
    )
