"""[.mark] Lire les réglages de sécurité d'un agent (clé ``securite_conversation``). Éteint par défaut ; ne lève jamais."""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.schemas.securite_conversation import SecuriteConversation

CLE = "securite_conversation"


def lire(brut: Any) -> SecuriteConversation:
    """Les réglages tels que l'agent les porte ; des réglages illisibles retombent sur « tout éteint » (journalisé)."""
    if isinstance(brut, SecuriteConversation):
        return brut
    if not brut:
        return SecuriteConversation()
    try:
        return SecuriteConversation.model_validate(brut)
    except Exception as erreur:  # noqa: BLE001 -- jamais à la place de l'appel
        logger.warning(f"[securite] réglages illisibles, tout reste éteint : {erreur!r}")
        return SecuriteConversation()


def de_l_agent(run_configs: dict[str, Any] | None) -> SecuriteConversation:
    return lire((run_configs or {}).get(CLE))


def garde_de_sortie_allumee(r: SecuriteConversation) -> bool:
    return bool(r.jamais.outils or r.jamais.recitation)
