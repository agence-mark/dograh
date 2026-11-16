"""[.mark] Module Restauration, lot 2 (D6) : la SOURCE D'HEURE de l'organisation.

Tout le code du module (couche d'accès, tâches de fond : purge, rattrapage, libération avant l'heure) lit
l'heure ICI, jamais directement. Une seule ligne de ce fichier lit l'heure réelle (``_horloge_reelle``) ; un test
(``test_restauration_horloge.py``) balaie les fichiers du module et échoue si l'un d'eux la lit autrement.

- ``horloge(org)`` rend la source d'heure d'une organisation (``org`` : son identifiant ou le nom de sa base ; la
  base du client est une par organisation). L'heure rendue est TOUJOURS aware (UTC) ; le jour et l'heure de fin
  d'un établissement se calculent dans son fuseau, par le code, jamais par le modèle.
- ``remplacer(org, source)`` : une source de remplacement, **pour les tests seulement** (refusée hors pytest).
  Plus d'horloge simulée à l'écran depuis E-45 : la simulation passe par de vrais appels, à l'heure réelle.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Hashable

# Les remplacements posés par les tests, par organisation (ou par nom de base).
_remplacements: dict[Hashable, Callable[[], datetime]] = {}


def _horloge_reelle() -> datetime:
    """LE seul endroit du module qui lit l'heure réelle."""
    return datetime.now(UTC)


class Horloge:
    """La source d'heure d'une organisation."""

    def __init__(self, org: Hashable):
        self.org = org

    def maintenant(self) -> datetime:
        source = _remplacements.get(self.org, _horloge_reelle)
        valeur = source()
        if valeur.tzinfo is None:
            raise ValueError("La source d'heure doit rendre une heure avec fuseau (aware).")
        return valeur.astimezone(UTC)


def horloge(org: Hashable) -> Horloge:
    return Horloge(org)


@contextmanager
def remplacer(org: Hashable, source: Callable[[], datetime] | datetime) -> Iterator[None]:
    """Pour les TESTS seulement : l'heure de ``org`` devient ``source`` (une heure fixe, ou une fonction)."""
    if "pytest" not in sys.modules:
        raise RuntimeError("La source d'heure ne se remplace que dans les tests.")
    fonction = (lambda: source) if isinstance(source, datetime) else source
    precedente = _remplacements.get(org)
    _remplacements[org] = fonction
    try:
        yield
    finally:
        if precedente is None:
            _remplacements.pop(org, None)
        else:
            _remplacements[org] = precedente
