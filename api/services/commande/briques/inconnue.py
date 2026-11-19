"""[.mark] Une règle inconnue ne bloque jamais (E29, chantier Partie 1, lot 8).

Ce que la brique ne sait pas exprimer (une règle de la carte qu'aucun modèle de caisse ne porte) : la ligne garde le produit vendable, la partie inconnue part
en note de ligne (``regle_inconnue_en_note``), et le portail la signale au restaurateur (``signaler_une_regle_inconnue``, ``GET .../signalements-de-carte``).
"""

from __future__ import annotations

from typing import Any

LONGUEUR_NOTE = 200


def ajouter_a_la_note(ligne: dict[str, Any], note: str) -> None:
    """La note de la ligne reçoit ``note`` (une fois), bornée en longueur."""
    if note and note not in (ligne.get("note") or ""):
        ligne["note"] = (f"{ligne['note']} ; {note}" if ligne.get("note") else note)[:LONGUEUR_NOTE]


def regle_inconnue_en_note(ligne: dict[str, Any], texte: str, notes_libres: bool = True) -> None:
    """Une règle que la carte ne sait pas exprimer : la ligne reste vendable, le texte est noté sur la ligne quand les notes libres sont permises, sinon ignoré ;
    dans les deux cas il est rendu dans ``regles_inconnues`` de la ligne (pour être signalé au portail)."""
    texte = " ".join((texte or "").split())
    if not texte:
        return
    if texte not in ligne.setdefault("regles_inconnues", []):
        ligne["regles_inconnues"].append(texte)
    if notes_libres:
        ajouter_a_la_note(ligne, texte)
