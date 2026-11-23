"""[.mark] Module Restauration, lot 20 : le moteur de la caisse de démo VU COMME UN RÉSEAU (``httpx``), sans serveur.

Les tests (et un essai dans le même processus) branchent la prise HubRise sur ce transport : la requête de la prise, son jeton, ses délais, passent par le
MÊME moteur que la route servie sur le réseau, qui ne fait que l'enrober (``routes/restauration_caisse_demo.py``). Une caisse qui ne répond pas, ou qui met plus de temps
que le délai de la requête, se voit comme sur un vrai réseau : ``httpx.ReadTimeout`` (jamais une attente réelle de dix secondes dans un test).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

import httpx

from api.services.restauration.caisse.caisse_demo.adresse import CHEMIN_DE_LA_CAISSE
from api.services.restauration.caisse.caisse_demo.moteur import moteur

PREFIXE = CHEMIN_DE_LA_CAISSE


class TransportDeDemo(httpx.AsyncBaseTransport):
    def __init__(self, *, prefixe: str = PREFIXE, dormir: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self._prefixe, self._dormir = prefixe, dormir
        self.demandes: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.demandes.append(request)
        chemin = request.url.path
        if not chemin.startswith(self._prefixe + "/") and chemin != self._prefixe:
            return httpx.Response(404, json={"message": "Not found", "error_type": "not_found"}, request=request)
        try:
            corps = json.loads(request.content) if request.content else None
        except ValueError:
            return httpx.Response(400, json={"message": "Invalid JSON", "error_type": "bad_request"}, request=request)
        reponse = await moteur.servir(request.headers.get("x-access-token"), request.method, chemin[len(self._prefixe):] or "/", dict(request.url.params), corps)
        delai_max = (request.extensions.get("timeout") or {}).get("read")
        if reponse.silence or (delai_max is not None and reponse.delai_s >= delai_max):
            raise httpx.ReadTimeout("La caisse de démo ne répond pas.", request=request)
        if reponse.delai_s:
            await self._dormir(reponse.delai_s)
        if reponse.corps is None:
            return httpx.Response(reponse.code, headers=reponse.entetes, request=request)
        return httpx.Response(reponse.code, json=reponse.corps, headers=reponse.entetes, request=request)
