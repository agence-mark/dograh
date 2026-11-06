"""[.mark] Batterie du builder : les correcteurs. Chacun lit la TRACE (appels dans l'ordre, textes rendus) et rend (réussi, pourquoi)."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from api.services.builder.batterie.cas import Correcteur

# Un juge à rubrique : (rubrique, trace en texte) -> (réussi, pourquoi). Fourni par l'appelant ; sans juge, le correcteur n'est PAS jugé.
Juge = Callable[[str, str], Awaitable[tuple[bool, str]]]


@dataclass
class Trace:
    appels: list[dict[str, Any]] = field(default_factory=list)  # {"nom", "arguments", "resultat"}
    textes: list[str] = field(default_factory=list)

    @property
    def noms(self) -> list[str]:
        return [a["nom"] for a in self.appels]

    def en_texte(self) -> str:
        lignes = [f"> {a['nom']}({a['arguments']}) -> {a['resultat']}" for a in self.appels]
        return "\n".join([*lignes, *self.textes])


def _dans_l_ordre(attendu: list[str], vus: list[str]) -> bool:
    position = 0
    for nom in vus:
        if position < len(attendu) and nom == attendu[position]:
            position += 1
    return position == len(attendu)


async def corriger(correcteur: Correcteur, trace: Trace, juge: Juge | None = None) -> tuple[bool | None, str]:
    """``None`` : non jugé (pas de juge fourni). Jamais un succès par défaut."""
    if correcteur.genre == "appelee":
        manquantes = [a for a in correcteur.actions if a not in trace.noms]
        return (not manquantes, f"never called: {manquantes}" if manquantes else "")
    if correcteur.genre == "interdite":
        faites = [a for a in correcteur.actions if a in trace.noms]
        return (not faites, f"called but forbidden: {faites}" if faites else "")
    if correcteur.genre == "ordre":
        ok = _dans_l_ordre(correcteur.actions, trace.noms)
        return (ok, "" if ok else f"expected order {correcteur.actions}, got {trace.noms}")
    if correcteur.genre == "motif":
        ok = re.search(correcteur.motif, trace.en_texte(), re.IGNORECASE | re.DOTALL) is not None
        return (ok, "" if ok else f"pattern not found: {correcteur.motif}")
    if juge is None:
        return None, "no judge given: not judged"
    return await juge(correcteur.rubrique, trace.en_texte())
