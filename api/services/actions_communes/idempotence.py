"""[.mark] L'idempotence d'une fiche (chantier Partie 1, lot 3 ; E11, M17, M37).

Une fiche rejouée à l'identique dans le même tour ne change rien (``deja_fait``) ; la même phrase dite à deux tours différents compte deux fois
(règle légitime « deux lignes identiques s'additionnent », ``moteur._fusionner``). La clé porte le tour, l'opération et les arguments, jamais la
phrase du modèle (``a_dire`` change d'une passe à l'autre sans changer la fiche).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from api.services.actions_communes import conversation as CONV

CLES_SANS_EFFET = ("a_dire",)


def cle_d_idempotence(tour: Any, operation: str, arguments: dict[str, Any]) -> str:
    utiles = {k: v for k, v in (arguments or {}).items() if k not in CLES_SANS_EFFET}
    contenu = json.dumps([tour, operation, utiles], sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(contenu.encode()).hexdigest()[:24]


def deja_executee(memoire: dict[str, Any], cle: str) -> bool:
    """Vrai si cette clé a déjà été exécutée ; sinon la retient (une seule mémoire par appel, dans le panier)."""
    vues = CONV.de(memoire).setdefault("fiches_executees", [])
    if cle in vues:
        return True
    vues.append(cle)
    del vues[:-60]
    return False


def _cle_de_la_case(tour: Any, case: str, valeur: Any) -> str:
    return cle_d_idempotence(tour, f"case:{case}", {case: valeur})


def case_deja_faite(memoire: dict[str, Any], tour: Any, case: str, valeur: Any) -> bool:
    """Clôture, lot B4 (M6, point 3) : la mémoire « déjà exécutée » tenue PAR CASE dans le tour. Après un refus partiel, la fiche refaite est
    différente (la case refusée en moins) : ses cases déjà faites ne sont pas refaites (avant : l'article ajouté deux fois, RC2 G33)."""
    return _cle_de_la_case(tour, case, valeur) in (CONV.de(memoire).get("fiches_executees") or [])


def noter_les_cases(memoire: dict[str, Any], tour: Any, cases: dict[str, Any]) -> None:
    """Les cases exécutées de la fiche entrent à la mémoire du tour."""
    vues = CONV.de(memoire).setdefault("fiches_executees", [])
    for case, valeur in cases.items():
        cle = _cle_de_la_case(tour, case, valeur)
        if cle not in vues:
            vues.append(cle)
    del vues[:-60]
