"""[.mark] U11 : lire les réglages de publication d'un agent (clé ``publication`` de ``workflow_configurations``).

Jamais d'exception : un réglage illisible vaut les défauts du code, qui sont la garde d'avant.
"""

from __future__ import annotations

from typing import Any

from api.schemas.publication import Position, Publication

CLE = "publication"
CONTROLES = (
    "tests_obligatoires",
    "bilan_du_prompt",
    "liste_vocale",
    "attaques",
    "garde_fous",
    "variables",
    "briques",
    "outils",
    "sans_effet",
    "sortie_d_impasse",
    "deux_webhooks",
    # Clôture, lot B (D1, D2) : l'annonce « vous parlez à une IA » (éteinte, vide, ou voix temps réel sans accueil écrit) : éteint ou prévient.
    "annonce_ia",
    # Lot « façon Tala par motif » : les contrôles de rédaction (``controle/regles.CODES_DE_REDACTION``, même ordre).
    "valeur_en_dur",
    "verbe_ecran",
    "action_sans_outil",
    "sortie_non_citee",
    "poids_agent",
)
# Les contrôles de rédaction : jouent la même lecture du prompt (``controle/service``) ; K5 ne bloque jamais.
CONTROLES_DE_REDACTION = CONTROLES[-5:]


def lire(configurations: dict[str, Any] | None) -> Publication:
    brut = (configurations or {}).get(CLE)
    if not isinstance(brut, dict):
        return Publication()
    try:
        return Publication.model_validate(brut)
    except Exception:  # noqa: BLE001 -- un réglage illisible ne bloque pas une publication : les défauts du code
        return Publication()


def position(configurations: dict[str, Any] | None, controle: str) -> Position:
    return getattr(lire(configurations).controles, controle)


def deploiement_actif(configurations: dict[str, Any] | None) -> bool:
    """Lu sur un dictionnaire déjà en mémoire : éteint (défaut), aucune lecture de plus à la création d'un appel."""
    brut = (configurations or {}).get(CLE)
    if not isinstance(brut, dict):
        return False
    deploiement = brut.get("deploiement")
    return isinstance(deploiement, dict) and deploiement.get("actif") is True
