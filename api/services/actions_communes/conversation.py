"""[.mark] Lot 6 (G3) : deux objets, la commande (ou la réservation) et la conversation.

La conversation est ce que le code tient pour mener l'appel (le tour, le registre des questions et leurs numéros, la mémoire des fiches déjà jouées, l'allergie
donnée avant, le compteur des doutes) : elle bouge sans que rien ne change pour la personne. Elle vit sous UNE clé du dossier, jamais à plat à côté de la
commande : « ce que la personne vit » se lit donc sur le dossier sans elle, et un nouvel état de la conversation n'allonge aucune liste.

Aucun mot de métier.
"""

from __future__ import annotations

from typing import Any

CLE = "conversation"


def de(dossier: dict[str, Any]) -> dict[str, Any]:
    """La conversation de ce dossier, créée au premier besoin."""
    tenue = dossier.get(CLE)
    if not isinstance(tenue, dict):
        tenue = dossier[CLE] = {}
    return tenue


CLE_QUESTION = "question"  # la question posée à la personne, dans la conversation : une seule à la fois, ``None`` quand rien n'attend


def question_de(dossier: dict[str, Any] | None) -> dict[str, Any] | None:
    """La question posée à la personne dans ce dossier (commande ou réservation), ``None`` quand rien n'attend. Lecture seule : ne crée rien."""
    tenue = (dossier or {}).get(CLE)
    q = tenue.get(CLE_QUESTION) if isinstance(tenue, dict) else None
    return q if isinstance(q, dict) else None


def poser_question(dossier: dict[str, Any], question: dict[str, Any] | None) -> None:
    """Pose (ou retire, avec ``None``) la question de ce dossier : le seul geste qui l'écrit."""
    de(dossier)[CLE_QUESTION] = question
