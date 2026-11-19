"""[.mark] Chantier Partie 1, lot 6 (E22, A27, S02 ; D61 point 7) : la note de la commande, composée sans rien écraser.

Recopie de la règle prouvée au banc (``banc-b12/commande_b12.py`` ``composer_la_note_de_commande``) : les notes de la fiche (la note de toute la
commande, la consigne pour le livreur), puis l'allergie et la consigne notées par le greffier quand elles n'y sont pas déjà. Une allergie notée
n'est jamais perdue (n8). Propre à la commande : la réservation n'a pas de note de commande.
"""

from __future__ import annotations

from typing import Any

from api.services.actions_communes.forme import norm

AUCUNE = "aucune"
CHAMPS_DU_GREFFIER = ("allergie", "consigne_livreur")
ENTETES = {"allergie": "Allergie : ", "consigne_livreur": "Pour le livreur : "}


def composer_la_note_de_commande(notes_fiche: list[dict[str, Any]], notes_greffier: dict[str, Any] | None) -> str | None:
    """E22 : les notes de la fiche, puis l'allergie et la consigne du greffier si elles n'y sont pas déjà. Rien n'est écrasé."""
    parts = [str(n["texte"]) for n in notes_fiche if str(n.get("texte") or "").strip()]
    for champ in CHAMPS_DU_GREFFIER:
        v = str((notes_greffier or {}).get(champ) or "").strip()
        if v and norm(v) != AUCUNE and not any(norm(v) in norm(p) for p in parts):
            parts.append(ENTETES[champ] + v)
    return " ; ".join(parts) or None
