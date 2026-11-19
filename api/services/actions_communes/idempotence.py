"""[.mark] L'idempotence d'une fiche (chantier Partie 1, lot 3 ; E11, M17, M37).

Une fiche rejouée à l'identique dans le même tour ne change rien (``deja_fait``) ; la même phrase dite à deux tours différents compte deux fois
(règle légitime « deux lignes identiques s'additionnent », ``moteur._fusionner``). La clé porte le tour, l'opération et les arguments, jamais la
phrase du modèle (``a_dire`` change d'une passe à l'autre sans changer la fiche).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

CLES_SANS_EFFET = ("a_dire",)


def cle_d_idempotence(tour: Any, operation: str, arguments: dict[str, Any]) -> str:
    utiles = {k: v for k, v in (arguments or {}).items() if k not in CLES_SANS_EFFET}
    contenu = json.dumps([tour, operation, utiles], sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(contenu.encode()).hexdigest()[:24]


def deja_executee(memoire: dict[str, Any], cle: str) -> bool:
    """Vrai si cette clé a déjà été exécutée ; sinon la retient (une seule mémoire par appel, dans le panier)."""
    vues = memoire.setdefault("fiches_executees", [])
    if cle in vues:
        return True
    vues.append(cle)
    del vues[:-20]
    return False
