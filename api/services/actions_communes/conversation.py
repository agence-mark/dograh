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


def identite_de_la_question(q: dict[str, Any] | None) -> tuple[Any, ...]:
    """Lot 7b-C5 n° 10 : l'identité d'une question par sa STRUCTURE, ``(id, type, objet)``, jamais par son texte (le texte de secours est retiré en C7, le modèle dit la question avec ses mots) :
    l'objet est ce dont elle parle, en faits bruts du dossier de la question (l'article, la proposition, l'heure, les candidats ou les choix). Même texte et autre objet : deux questions ;
    texte changé et même objet : la même. ``()`` sans question. C6 : la relecture, que le modèle dit, a pour objet son JETON (``jeton``, neuf à chaque relecture posée), jamais son texte ; une question que le code dit lui-même
    (``QUESTIONS_DITES_PAR_LE_CODE``) a pour objet SON texte, qui change avec la commande."""
    from api.services.actions_communes.enveloppe import QUESTIONS_DITES_PAR_LE_CODE

    if not isinstance(q, dict):
        return ()
    candidats = tuple(str(c.get("libelle")) if isinstance(c, dict) else str(c) for c in q.get("candidats_par_identifiant") or q.get("candidats_dits") or q.get("choix") or [])
    objet = (q.get("article_en_question"), q.get("article_propose"), q.get("heure_dite") or q.get("heure"), candidats, q.get("texte") if q.get("type") in QUESTIONS_DITES_PAR_LE_CODE else None, q.get("jeton"))
    return (q.get("id"), q.get("type"), objet)
