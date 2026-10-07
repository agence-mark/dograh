"""[.mark] The client's Twilio, for the outage fallback (L7).

The account is the one of the run (« Telephony »); its token never appears in an error or a log.
``MARK_TWILIO_API_URL`` points the demonstration at a local stand-in; never set in production.

⛔ ``ecrire_adresse_de_secours`` writes on a real number when called with a real account: it is
a production gesture, called only from the screen, by hand, on Evan's go (A-VALIDER).
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx
from loguru import logger

VARIABLE_API = "MARK_TWILIO_API_URL"
DELAI_S = 6.0


class TwilioIndisponible(RuntimeError):
    pass


def api_twilio() -> str:
    return (os.environ.get(VARIABLE_API) or "https://api.twilio.com").rstrip("/")


def nouveau_client(**options) -> httpx.AsyncClient:
    """The HTTP client (a test gives its stand-in Twilio here)."""
    return httpx.AsyncClient(**options)


def _compte(sid: str) -> str:
    return f"{api_twilio()}/2010-04-01/Accounts/{sid}"


async def _requete(
    methode: str, url: str, sid: str, jeton: str, **options
) -> httpx.Response:
    try:
        async with nouveau_client(timeout=DELAI_S) as client:
            reponse = await client.request(methode, url, auth=(sid, jeton), **options)
    except httpx.HTTPError as erreur:
        raise TwilioIndisponible(
            f"Twilio does not answer ({type(erreur).__name__})."
        ) from None
    if reponse.status_code >= 400:
        raise TwilioIndisponible(f"Twilio answered HTTP {reponse.status_code}.")
    return reponse


async def mettre_a_jour_appel(sid: str, jeton: str, call_sid: str, twiml: str) -> None:
    """Replace what a live call does (same mechanism as the transfer, F4)."""
    await _requete(
        "POST",
        f"{_compte(sid)}/Calls/{call_sid}.json",
        sid,
        jeton,
        data={"Twiml": twiml},
    )


async def appels_entrants(
    sid: str, jeton: str, numero: str, depuis: datetime, maximum: int = 500
) -> list[dict[str, Any]]:
    """The calls made TO ``numero`` since ``depuis`` (call log), newest first, paginated."""
    url = f"{_compte(sid)}/Calls.json"
    params: dict[str, Any] | None = {
        "To": numero,
        "StartTime>": depuis.strftime("%Y-%m-%d"),
        "PageSize": 100,
    }
    appels: list[dict[str, Any]] = []
    while url and len(appels) < maximum:
        corps = (await _requete("GET", url, sid, jeton, params=params)).json()
        appels += corps.get("calls") or []
        suivante = corps.get("next_page_uri")
        url, params = (f"{api_twilio()}{suivante}" if suivante else None), None
    return appels[:maximum]


async def ecrire_adresse_de_secours(
    sid: str, jeton: str, numero: str, url: str | None
) -> bool:
    """PN5: the ``VoiceFallbackUrl`` of ``numero`` (None clears it). False if the number is not
    in this account."""
    corps = (
        await _requete(
            "GET",
            f"{_compte(sid)}/IncomingPhoneNumbers.json",
            sid,
            jeton,
            params={"PhoneNumber": numero},
        )
    ).json()
    numeros = corps.get("incoming_phone_numbers") or []
    if not numeros:
        logger.warning(
            "[.mark] Emergency address not written: the number is not in this Twilio account"
        )
        return False
    donnees = {"VoiceFallbackUrl": url or "", "VoiceFallbackMethod": "POST"}
    await _requete(
        "POST",
        f"{_compte(sid)}/IncomingPhoneNumbers/{numeros[0]['sid']}.json",
        sid,
        jeton,
        data=donnees,
    )
    return True
