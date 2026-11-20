"""[.mark] Chantier Partie 1, lot 6 (E22, A27, S02 ; D61 point 7) : la note de la commande, composée sans rien écraser.

Recopie de la règle prouvée au banc (``banc-b12/commande_b12.py`` ``composer_la_note_de_commande``) : les notes de la fiche (la note de toute la
commande, la consigne pour le livreur), puis l'allergie et la consigne notées par le greffier quand elles n'y sont pas déjà. Une allergie notée
n'est jamais perdue (n8). Propre à la commande : la réservation n'a pas de note de commande.
"""

from __future__ import annotations

from typing import Any

from api.services.actions_communes.forme import norm

AUCUNE = "aucune"
TAILLE = 300  # la taille de la note envoyée avec la commande
ENTETES = {"allergie": "Allergie : ", "consigne_livreur": "Pour le livreur : "}


def composer_la_note_de_commande(notes_fiche: list[dict[str, Any]], notes_greffier: dict[str, Any] | None) -> str | None:
    """E22 : l'allergie notée par le greffier OUVRE la note, toujours avec son en-tête, même si son mot figure déjà dans une autre note (« sans noix »
    est une préférence, pas une allergie) ; puis les notes de la fiche, puis la consigne du greffier si elle n'y est pas déjà. La coupe à la taille de
    la note (``TAILLE``) porte sur ce qui suit l'allergie, jamais sur elle (lot 19, D23, note de Pierre du 20/11). Rien n'est écrasé."""
    greffier = notes_greffier or {}
    allergie = str(greffier.get("allergie") or "").strip()
    tete = ENTETES["allergie"] + allergie if allergie and norm(allergie) != AUCUNE else None
    parts = [str(n["texte"]) for n in notes_fiche if str(n.get("texte") or "").strip()]
    consigne = str(greffier.get("consigne_livreur") or "").strip()
    if consigne and norm(consigne) != AUCUNE and not any(norm(consigne) in norm(p) for p in parts):
        parts.append(ENTETES["consigne_livreur"] + consigne)
    reste = " ; ".join(parts)
    if tete is None:
        return reste[:TAILLE] or None
    return (tete + (" ; " + reste if reste else ""))[: max(TAILLE, len(tete))]
