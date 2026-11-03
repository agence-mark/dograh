"""[.mark] S1 / D189 : N sessions par heure, par jeton et par adresse, au moment de ``POST /init``.

Réutilise ``rate_limiter.acquire_token`` (fenêtre glissante dans Redis) avec une fenêtre d'une heure. L'adresse n'est
PAS gardée : seule son empreinte salée par le jeton entre dans la clé Redis, qui expire avec la fenêtre.
Redis injoignable : le limiteur refuse (comportement de l'amont, prudent) ; ``/init`` répond alors 429 propre.
"""

from __future__ import annotations

import hashlib

from api.services.call_concurrency.rate_limiter import rate_limiter

FENETRE_S = 3600.0


def _empreinte(embed_token_id: int, adresse: str | None) -> str:
    brut = f"{embed_token_id}|{adresse or 'inconnue'}".encode()
    return hashlib.sha256(brut).hexdigest()[:24]


async def autoriser_session(embed_token_id: int, adresse: str | None, par_heure: int) -> bool:
    return await rate_limiter.acquire_token(
        embed_token_id,
        par_heure,
        scope_key=f"public_embed:ip:{embed_token_id}:{_empreinte(embed_token_id, adresse)}",
        window_seconds=FENETRE_S,
    )


RAPPELS_PAR_HEURE_ET_IP = 5


async def autoriser_rappel(embed_token_id: int, adresse: str | None, par_heure: int = RAPPELS_PAR_HEURE_ET_IP) -> bool:
    """Lot S3 : au plus ``par_heure`` demandes de rappel par jeton et par adresse (autre seau que les sessions)."""
    return await rate_limiter.acquire_token(
        embed_token_id,
        par_heure,
        scope_key=f"public_embed:rappel:{embed_token_id}:{_empreinte(embed_token_id, adresse)}",
        window_seconds=FENETRE_S,
    )
