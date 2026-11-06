"""[.mark] C4 : la note du juge d'un appel, sur 5.

La note est la part des critères RÉUSSIS parmi ceux que le juge a pu vérifier, ramenée à 5 (un chiffre après la virgule). Un critère
« non vérifiable » n'est ni une réussite ni un échec : il sort du calcul (sa raison reste dans le verdict). Aucun critère vérifié : pas
de note (``None``), jamais un zéro qui ferait passer un appel non jugé pour un mauvais appel. Une seule fonction, utilisée par le juge
sur clé et par ``juge_ecrire`` (Claude Code) : même appel, même note.
"""

from __future__ import annotations

from typing import Any

NOTE_MAX = 5.0


def calculer(verdicts: list[dict[str, Any]] | None) -> float | None:
    verifies = [x for x in verdicts or [] if isinstance(x, dict) and x.get("verdict") in ("reussi", "rate")]
    if not verifies:
        return None
    reussis = sum(1 for x in verifies if x["verdict"] == "reussi")
    return round(NOTE_MAX * reussis / len(verifies), 1)


def de_un_resultat(resultat: dict[str, Any]) -> float | None:
    """La note d'un résultat écrit sous ``annotations['juge']`` : seul l'état « juge » en porte une."""
    if resultat.get("etat") != "juge":
        return None
    return calculer(resultat.get("verdicts"))
