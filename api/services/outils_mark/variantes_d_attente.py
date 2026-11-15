"""[.mark] Module Restauration, lot 7 (W20, E-37) : les variantes de la phrase d'attente d'un outil, jamais deux fois la même dans un appel.

La phrase d'attente est dite par le code, seulement si l'outil n'a pas fini au seuil réglable (``seuil_patience_ms``, par outil). Quand la fiche de
l'outil porte plusieurs variantes (``phrases_attente``), la première qui n'a pas encore été dite dans CET appel est choisie ; quand elles ont toutes
été dites, rien n'est redit. Sans variantes, le comportement d'avant : ``phrase_attente``, telle quelle, à chaque fois.

La mémoire d'un appel vit sur son moteur (comme les verrous d'outils) : un autre appel repart de zéro. ⛔ Ne lève jamais.
"""

from __future__ import annotations

from typing import Any

_ATTRIBUT = "_mark_phrases_d_attente_dites"
MAX_VARIANTES = 6


def les_variantes(config: dict[str, Any]) -> list[str]:
    brut = config.get("phrases_attente")
    if not isinstance(brut, (list, tuple)):
        return []
    vues: list[str] = []
    for texte in brut:
        propre = str(texte or "").strip()
        if propre and propre not in vues:
            vues.append(propre)
    return vues[:MAX_VARIANTES]


def a_une_attente(config: dict[str, Any]) -> bool:
    return bool(les_variantes(config) or str(config.get("phrase_attente") or "").strip())


def choisir(moteur: Any, config: dict[str, Any]) -> str | None:
    """La phrase à dire maintenant, ou ``None`` (rien à dire, ou toutes les variantes déjà dites dans cet appel)."""
    try:
        variantes = les_variantes(config)
        if not variantes:
            return str(config.get("phrase_attente") or "").strip() or None
        dites = getattr(moteur, _ATTRIBUT, None)
        if not isinstance(dites, set):
            dites = set()
            setattr(moteur, _ATTRIBUT, dites)
        for phrase in variantes:
            if phrase not in dites:
                dites.add(phrase)
                return phrase
        return None
    except Exception:  # noqa: BLE001
        return None
