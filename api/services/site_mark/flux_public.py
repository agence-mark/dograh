"""[.mark] S1 / D164 / D174 : le flux temps réel d'une session PUBLIQUE ne laisse passer qu'une liste blanche.

Constat du 27/10 : la signalisation publique appelait le même gestionnaire que l'écran de test, qui envoie au
navigateur TOUT ce que l'observateur produit : transcriptions, texte de l'agent, appels d'outils avec leurs
arguments et leurs résultats, nom des étapes, erreurs détaillées, mesures. Pour un visiteur c'est une fuite.

Règle : **refus par défaut**. Un type d'événement qui n'est pas dans la liste blanche (y compris un type
qui n'existe pas encore) n'arrive JAMAIS au visiteur. Les événements retenus sont reconstruits (seul leur type
passe, jamais leur contenu), et l'erreur du pipeline est remplacée par une erreur générique sans détail.
L'écran de test garde son flux complet : ce module n'est branché que sur la signalisation publique.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from pipecat.utils.enums import RealtimeFeedbackType

Sender = Callable[[dict], Awaitable[None]]

# Ce que le widget a besoin de savoir pour animer l'orbe et signaler une panne : rien d'autre.
TYPES_SANS_CONTENU = frozenset(
    {
        RealtimeFeedbackType.BOT_STARTED_SPEAKING.value,
        RealtimeFeedbackType.BOT_STOPPED_SPEAKING.value,
        RealtimeFeedbackType.USER_MUTE_STARTED.value,
        RealtimeFeedbackType.USER_MUTE_STOPPED.value,
    }
)
TYPE_ERREUR = RealtimeFeedbackType.PIPELINE_ERROR.value
LISTE_BLANCHE = TYPES_SANS_CONTENU | {TYPE_ERREUR}

MESSAGE_ERREUR_GENERIQUE = "service_unavailable"


def projeter(message: Any) -> dict | None:
    """Le message tel que le visiteur peut le recevoir, ou ``None`` (retenu côté serveur)."""
    if not isinstance(message, dict):
        return None
    type_ = message.get("type")
    if type_ in TYPES_SANS_CONTENU:
        return {"type": type_, "payload": {}}
    if type_ == TYPE_ERREUR:
        payload = message.get("payload")
        fatale = bool(payload.get("fatal")) if isinstance(payload, dict) else False
        return {"type": type_, "payload": {"fatal": fatale, "message": MESSAGE_ERREUR_GENERIQUE}}
    return None


def expediteur_public(envoyer: Sender) -> Sender:
    """Enveloppe un expéditeur de navigateur : seul ce que ``projeter`` rend est envoyé."""

    async def filtre(message: dict) -> None:
        projete = projeter(message)
        if projete is not None:
            await envoyer(projete)

    return filtre
