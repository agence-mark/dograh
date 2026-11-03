"""[.mark] U10 / S5 : le champ de saisie pendant l'appel du widget de site.

Le visiteur qui parle à l'agent peut aussi écrire (un nom, un numéro, une adresse mail qu'on dicte mal). Son texte
entre dans la conversation **comme un tour de l'utilisateur**, sur le modèle de ``_handle_send_text`` de Pipecat
(``interrompre la parole de l'agent, vider le circuit, ajouter le message, relancer le modèle``) : l'agent y répond à la
voix et le texte est gardé dans le verbatim comme un tour écrit (``ecrit: true``).

Bornes (tout est refusé proprement, jamais d'exception vers le visiteur) : longueur, fréquence, nombre par conversation,
rien après la fin de l'appel. Le texte est nettoyé (caractères de contrôle écartés).

La porte vit par conversation, dans la mémoire du processus qui porte l'appel (comme l'expéditeur du flux).
"""

from __future__ import annotations

import time
import unicodedata
from datetime import UTC, datetime
from typing import Awaitable, Callable

from loguru import logger

MAX_CARACTERES = 500
INTERVALLE_MINIMAL_S = 1.0
MAX_PAR_MINUTE = 6
MAX_PAR_CONVERSATION = 100

OK = "ok"
VIDE = "vide"
TROP_LONG = "trop_long"
TROP_RAPIDE = "trop_rapide"
PLAFOND = "plafond_atteint"
TERMINE = "termine"
INVALIDE = "invalide"

Injecteur = Callable[[str], Awaitable[bool]]


def nettoyer(brut: object) -> str | None:
    """Le texte propre, ou ``None`` si ce n'est pas du texte. Caractères de contrôle écartés, espaces resserrés."""
    if not isinstance(brut, str):
        return None
    sans_controle = "".join(
        c if (c in "\n\t" or unicodedata.category(c)[0] != "C") else " " for c in brut
    )
    return " ".join(sans_controle.split())


class PorteTexte:
    """Reçoit les textes d'UNE conversation et les passe à ``injecter`` si les bornes le permettent."""

    def __init__(self, injecter: Injecteur, horloge: Callable[[], float] = time.monotonic):
        self._injecter = injecter
        self._horloge = horloge
        self._instants: list[float] = []
        self._total = 0
        self._ferme = False

    def fermer(self) -> None:
        self._ferme = True

    async def recevoir(self, brut: object) -> str:
        if self._ferme:
            return TERMINE
        texte = nettoyer(brut)
        if texte is None:
            return INVALIDE
        if not texte:
            return VIDE
        if len(texte) > MAX_CARACTERES:
            return TROP_LONG
        if self._total >= MAX_PAR_CONVERSATION:
            return PLAFOND
        maintenant = self._horloge()
        self._instants = [t for t in self._instants if maintenant - t < 60.0]
        if self._instants and maintenant - self._instants[-1] < INTERVALLE_MINIMAL_S:
            return TROP_RAPIDE
        if len(self._instants) >= MAX_PAR_MINUTE:
            return TROP_RAPIDE
        self._instants.append(maintenant)
        self._total += 1
        try:
            reussi = await self._injecter(texte)
        except Exception as erreur:  # noqa: BLE001 -- un texte refusé ne coûte jamais l'appel
            logger.warning(f"[site] Texte du visiteur non injecté : {erreur!r}")
            return TERMINE
        return OK if reussi else TERMINE


_portes: dict[int, PorteTexte] = {}


def enregistrer_porte(workflow_run_id: int, porte: PorteTexte) -> None:
    _portes[workflow_run_id] = porte


def retirer_porte(workflow_run_id: int) -> None:
    porte = _portes.pop(workflow_run_id, None)
    if porte is not None:
        porte.fermer()


def porte_de(workflow_run_id: int) -> PorteTexte | None:
    return _portes.get(workflow_run_id)


def fabriquer_injecteur(engine, logs_buffer) -> Injecteur:
    """L'injecteur d'une conversation : le moteur ajoute le tour, le verbatim le garde (tour écrit)."""
    from api.services.pipecat.realtime_feedback_events import build_user_transcription_event

    async def injecter(texte: str) -> bool:
        if not await engine.injecter_texte_visiteur(texte):
            return False
        evenement = build_user_transcription_event(
            text=texte, final=True, timestamp=datetime.now(UTC).isoformat(timespec="milliseconds")
        )
        evenement["payload"]["ecrit"] = True
        await logs_buffer.append(evenement)
        return True

    return injecter
