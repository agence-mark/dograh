"""[.mark] Partie 3, SA-L3b : la branche d'agent ouverte par la requête (le builder et l'éditeur écrivent dans SON brouillon).

Un seul point d'entrée : l'en-tête ``X-Mark-Branche`` (l'identifiant de la branche, lu par ``get_user``). Sans en-tête, ou pour la
branche principale, rien ne change : le brouillon unique de l'agent, comme avant. Avec une branche, les fonctions de brouillon de
``workflow_client`` lisent et écrivent le brouillon DE CETTE PERSONNE sur CETTE branche (un brouillon par personne et par branche).

La valeur ne porte que deux entiers. Une branche qui n'appartient pas à l'agent visé ne trouve aucun brouillon et ne peut pas en
créer (le client de base la contrôle avec l'agent et l'organisation), donc un en-tête forgé ne donne accès à rien.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import NamedTuple


class Cible(NamedTuple):
    branch_id: int | None  # None : la branche principale
    user_id: int | None


_OUVERTE: ContextVar[Cible | None] = ContextVar("mark_branche_ouverte", default=None)


def ouvrir(branch_id: int | None, user_id: int | None) -> None:
    _OUVERTE.set(Cible(branch_id, user_id) if branch_id else None)


def courante() -> Cible:
    return _OUVERTE.get() or Cible(None, None)


ENTETE = "x-mark-branche"


def depuis_l_entete(connexion, user) -> None:
    """Lit ``X-Mark-Branche`` de la requête (appelée par ``get_user`` à chaque requête, dans les deux sens). Absent, illisible ou
    trop long : la principale, comme avant."""
    brut = (connexion.headers.get(ENTETE) or "").strip()
    ouvrir(int(brut) if brut.isdigit() and len(brut) < 10 else None, getattr(user, "id", None))
