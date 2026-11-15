"""[.mark] Module Restauration, lot 9 : le CLIENT HTTP de HubRise (l'unique endroit qui parle réseau à HubRise).

Règles du plan (bonnes pratiques du serveur) : chaque appel a un DÉLAI ; les nouvelles tentatives sont BORNÉES et seulement pour un geste rejouable
(lecture, ``PATCH``/``PUT`` d'un état) ; un ``POST`` de commande n'est JAMAIS rejoué ici (c'est l'envoi, avec sa recherche par notre numéro, qui reprend :
jamais deux commandes) ; une adresse sort seulement si elle est dans la LISTE FERMÉE de la fiche (``verifier_adresse``, D4).

Le jeton va dans l'en-tête ``X-Access-Token`` et n'est jamais écrit dans un message, un journal ni une erreur. Une erreur de HubRise devient un CODE de la liste
fermée (``ErreurHubrise.code``) : jamais le texte d'un fournisseur ni une pile à l'écran. Les tests branchent un transport enregistré (``httpx.MockTransport``) :
aucun appel réel. Limites documentées (general-concepts, lu le 15/11) : 500/min, 2 500/h, 10 000/jour, 10/min pour les lectures lourdes ; 429 au-delà.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from loguru import logger

from api.services.restauration.prises.adresses import verifier_adresse

BASE = "https://api.hubrise.com/v1"
BASE_AUTORISATION = "https://manager.hubrise.com/oauth2/v1"
DELAI_S = 10.0
TENTATIVES = 3
ATTENTE_MAX_S = 5.0  # une attente demandée par la caisse (429) plus longue n'est pas attendue : l'appelant reprendra
PAUSES_S = (0.5, 1.5)


class ErreurHubrise(Exception):
    """Une erreur de HubRise, réduite à un CODE fermé (``caisse_injoignable``, ``jeton_refuse``, ``limite_atteinte``, ``reponse_inattendue``) et au code HTTP."""

    def __init__(self, code: str, http: int | None = None, champ: str | None = None):
        super().__init__(f"HubRise : {code}" + (f" ({http})" if http else ""))
        self.code, self.http, self.champ = code, http, champ


class JetonRefuse(ErreurHubrise):
    """401 : le jeton est faux ou la connexion révoquée (la liaison passe à « rompue »)."""

    def __init__(self, http: int = 401):
        super().__init__("jeton_refuse", http)


async def _dormir(secondes: float) -> None:
    await asyncio.sleep(secondes)


class ClientHubrise:
    def __init__(
        self, jeton: str, *, point_de_vente: str | None = None, catalogue: str | None = None, liste_clients: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None, labo: bool = False, base: str = BASE,
        attendre: Callable[[float], Awaitable[None]] = _dormir,
    ):
        if not jeton:
            raise ValueError("Un jeton est nécessaire.")
        self._jeton = jeton
        self.point_de_vente, self.catalogue, self.liste_clients = point_de_vente, catalogue, liste_clients
        self._transport, self._labo, self._base, self._attendre = transport, labo, base, attendre

    def __repr__(self) -> str:  # jamais le jeton dans un message ni un journal
        return f"ClientHubrise(point_de_vente={self.point_de_vente!r})"

    async def requete(self, methode: str, chemin: str, *, corps: Any = None, params: dict[str, str] | None = None, rejouable: bool | None = None) -> Any:
        """Un appel. ``rejouable`` : par défaut tout sauf un ``POST``. Rend le JSON décodé (``None`` si le corps est vide)."""
        adresse = verifier_adresse("hubrise", self._base + chemin, labo=self._labo)
        permis = (rejouable if rejouable is not None else methode.upper() != "POST")
        essais = TENTATIVES if permis else 1
        derniere: ErreurHubrise | None = None
        attendu = False  # une attente demandée par la caisse (429) remplace la pause habituelle
        for numero in range(essais):
            if numero and not attendu:
                await self._attendre(PAUSES_S[min(numero - 1, len(PAUSES_S) - 1)])
            try:
                async with httpx.AsyncClient(transport=self._transport, timeout=DELAI_S) as http:
                    r = await http.request(methode, adresse, json=corps, params=params, headers={"X-Access-Token": self._jeton, "Accept": "application/json"})
            except (httpx.TimeoutException, httpx.TransportError) as erreur:
                logger.warning(f"[.mark] HubRise {methode} {chemin}: {type(erreur).__name__}")
                derniere = ErreurHubrise("caisse_injoignable")
                continue
            if r.status_code == 401:
                raise JetonRefuse()
            attendu = False
            if r.status_code == 429:
                derniere = ErreurHubrise("limite_atteinte", 429)
                attente = _attente_demandee(r)
                if attente is not None and attente <= ATTENTE_MAX_S and numero + 1 < essais:
                    await self._attendre(attente)
                    attendu = True
                    continue
                break  # le quota se vide à la minute : on n'insiste pas, on le dit
            if r.status_code >= 500:
                derniere = ErreurHubrise("caisse_injoignable", r.status_code)
                continue
            if r.status_code >= 400:
                raise ErreurHubrise("reponse_inattendue", r.status_code, champ=_premier_champ(r))
            if not r.content:
                return None
            try:
                return r.json()
            except ValueError:
                raise ErreurHubrise("reponse_inattendue", r.status_code) from None
        raise derniere or ErreurHubrise("caisse_injoignable")


def _attente_demandee(r: httpx.Response) -> float | None:
    try:
        return float(r.headers.get("retry-after", ""))
    except ValueError:
        return None


def _premier_champ(r: httpx.Response) -> str | None:
    """Le NOM du premier champ refusé (``/items/0/price``), jamais le message de HubRise."""
    try:
        erreurs = (r.json() or {}).get("errors") or []
        champ = erreurs[0].get("field") if erreurs else None
        return champ[:80] if isinstance(champ, str) else None
    except (ValueError, AttributeError, IndexError):
        return None


async def echanger_le_code(code: str, identifiant: str, secret: str, *, transport: httpx.AsyncBaseTransport | None = None, base: str = BASE_AUTORISATION) -> dict:
    """L'échange du code d'autorisation contre le jeton (serveur à serveur : le secret de notre application ne quitte jamais le serveur).
    Adresse en liste fermée ; un seul essai (le code est à usage unique)."""
    verifier_adresse("hubrise", base + "/token")
    try:
        async with httpx.AsyncClient(transport=transport, timeout=DELAI_S) as http:
            r = await http.post(base + "/token", data={"code": code}, auth=(identifiant, secret), headers={"Accept": "application/json"})
    except (httpx.TimeoutException, httpx.TransportError):
        raise ErreurHubrise("caisse_injoignable") from None
    if r.status_code in (400, 401):
        raise ErreurHubrise("jeton_refuse", r.status_code)
    if r.status_code >= 400:
        raise ErreurHubrise("reponse_inattendue", r.status_code)
    try:
        donnees = r.json()
    except ValueError:
        raise ErreurHubrise("reponse_inattendue", r.status_code) from None
    if not isinstance(donnees, dict) or not donnees.get("access_token") or not donnees.get("location_id"):
        raise ErreurHubrise("reponse_inattendue", r.status_code)
    return donnees
