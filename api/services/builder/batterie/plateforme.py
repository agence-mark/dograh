"""[.mark] Batterie du builder : la plateforme SIMULÉE. Aucune base, aucun fournisseur : chaque action répond ce que le cas impose."""

from __future__ import annotations

from typing import Any

from api.services.builder.batterie.cas import Cas


class Plateforme:
    def __init__(self, cas: Cas):
        self._reponses = cas.plateforme

    async def executer(self, nom: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return dict(self._reponses.get(nom, {"ok": True}))
