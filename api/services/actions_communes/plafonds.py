"""[.mark] Les bornes des opérations (chantier Partie 1, lot 3 ; E30, E28).

- ``plafond_d_operations`` : au plus 6 articles par fiche et 20 par ligne (``banc-b7`` ``PLAFOND_ARTICLES``, ``QTE_MAX``) ; au-delà, la fiche est
  refusée avec la raison (une seule commande par appel : redemander les articles un par un). Défauts réglables par agent (badge « à rendre
  configurable ») ;
- ``deux_questions_au_plus`` : la clarification est bornée ; à la troisième précision sur un même point, le retour propose la sortie (un message à
  l'équipe ou une personne), jamais une quatrième question.
"""

from __future__ import annotations

from typing import Any

PLAFOND_ARTICLES = 6
QTE_MAX = 20
QUESTIONS_PAR_POINT = 2


def plafond_d_operations(fiche: dict[str, Any], plafond_articles: int = PLAFOND_ARTICLES, qte_max: int = QTE_MAX) -> dict | None:
    """Le refus (raison ``plafond_d_operations``) quand la fiche dépasse les bornes ; ``None`` sinon."""
    articles = fiche.get("ajouter") if isinstance(fiche.get("ajouter"), list) else []
    changes = fiche.get("changer_quantite") if isinstance(fiche.get("changer_quantite"), list) else []
    trop = len(articles) > plafond_articles or any(
        isinstance(x, dict) and isinstance(x.get("quantite"), int) and not isinstance(x.get("quantite"), bool) and x["quantite"] > qte_max for x in articles + changes
    )
    if not trop:
        return None
    return {"raison": "plafond_d_operations", "cases": ["ajouter", "changer_quantite"],
            "explication": f"au plus {plafond_articles} articles par phrase et {qte_max} par ligne", "a_faire": "redemande-lui les articles un par un"}


def deux_questions_au_plus(compteur: dict[str, int], point: str) -> bool:
    """Compte une question de plus sur ``point`` ; vrai tant qu'elle reste dans la borne (deux au plus), faux à la troisième."""
    compteur[point] = int(compteur.get(point) or 0) + 1
    return compteur[point] <= QUESTIONS_PAR_POINT
