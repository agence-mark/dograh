"""[.mark] Builder, U6 puis RA-B (R6, décision d'Evan du 04/11 soir) : la traçabilité du juge, sans aucune restriction.

Choisir pour le juge (et l'appelant simulé) un modèle différent de l'agent et du builder est un bon principe, mais
**une discipline qu'on s'impose à la main, pas une règle du code** : le code ne refuse plus rien (ni le même modèle que
l'agent jugé, ni le même que le builder, ni la même clé), tout se configure. Ce qui reste : la MENTION « Jugé par [modèle] »
portée par chaque verdict (traçabilité), sans avertissement ni blocage ; l'écran rappelle le principe dans une bulle.

Pur : aucune lecture de base ici.
"""

from __future__ import annotations

from dataclasses import dataclass

MENTION_CLAUDE_CODE = "Jugé par Claude Code"


@dataclass(frozen=True)
class Independance:
    mention: str | None = None


def controler(
    *, source_juge: str, modele_juge: str, modele_builder: str | None = None, modele_agent: str | None = None
) -> Independance:
    """La mention du verdict. ``modele_builder`` et ``modele_agent`` sont gardés pour les appelants : ils ne servent plus."""
    if source_juge == "claude_code":
        return Independance(mention=MENTION_CLAUDE_CODE)
    modele = (modele_juge or "").strip()
    return Independance(mention=f"Jugé par {modele}" if modele else None)
