"""[.mark] Lot 6 (G2) : ce que les portes de la commande et de la réservation font de la même façon, à côté de l'issue de l'appel (``issues``).

* ``resultat_public`` : un résultat du module tel que le modèle le reçoit (l'opération, son statut, ce qui manque, les faits sans ce que le métier garde pour lui) ;
* ``premier_cas`` : parmi les cas qu'un métier écrit dans l'ordre, le texte que le code dit lui-même au retour de la fiche.

Aucun mot de métier : les faits écartés, les mots du modèle et les cas viennent de la porte qui appelle.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from api.services.actions_communes.arguments import en_json
from api.services.actions_communes.resultat import Resultat


def faits_publics(r: Resultat, ecartes: Iterable[str]) -> dict[str, Any]:
    """Les faits d'un résultat sans ceux que le métier ne montre jamais au modèle."""
    gardes = set(ecartes)
    return en_json({k: v for k, v in (r.faits or {}).items() if k not in gardes})


def resultat_public(operation: str, r: Resultat, ecartes: Iterable[str], mots_du_modele: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Un résultat du module tel que le modèle le reçoit ; ``mots_du_modele`` traduit ce qui manque (les mots du classeur) à la source."""
    manque = (mots_du_modele or {}).get(r.manque, r.manque) if r.manque else None
    return {"operation": operation, "statut_du_module": r.statut, **({"manque": manque} if manque else {}), "faits": faits_publics(r, ecartes)}


def premier_cas(cas: Iterable[tuple[bool, Callable[[], str]]]) -> str | None:
    """Le texte du premier cas dont la condition est vraie (le texte n'est calculé que pour lui) ; ``None`` quand aucun ne l'est."""
    for condition, texte in cas:
        if condition:
            return texte()
    return None
