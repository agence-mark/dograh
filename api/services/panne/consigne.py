"""[.mark] The Twilio instructions of the outage fallback (L7, PN1, PN4, PN5, P6).

Twilio speaks with its own French voice (P6): our voice provider may be the part that failed.
Every text is escaped: a sentence typed on screen never becomes an instruction.
"""

from __future__ import annotations

from urllib.parse import quote
from xml.sax.saxutils import escape, quoteattr

from api.schemas.panne import (
    DEFAUT_RAPPEL_SANS_DATE,
    DEFAUT_RENVOI,
    LANGUE_TWILIO,
    VOIX_TWILIO,
)

ENTETE = '<?xml version="1.0" encoding="UTF-8"?>'


def _dire(texte: str) -> str:
    return (
        f'<Say language="{LANGUE_TWILIO}" voice="{VOIX_TWILIO}">{escape(texte)}</Say>'
    )


def renvoi(phrase: str, numero: str, sonnerie_s: int, url_resultat: str) -> str:
    """PN1: say the hand-over sentence, ring the second number; Twilio then asks the result."""
    return (
        f"{ENTETE}<Response>{_dire(phrase)}"
        f'<Dial timeout="{int(sonnerie_s)}" action={quoteattr(url_resultat)} method="POST" answerOnBridge="true">'
        f"<Number>{escape(numero)}</Number></Dial></Response>"
    )


def rappel(phrase: str) -> str:
    """PN1: closed or no answer: the call-back promise, then hang up."""
    return f"{ENTETE}<Response>{_dire(phrase)}<Hangup/></Response>"


def raccrocher() -> str:
    return f"{ENTETE}<Response><Hangup/></Response>"


def redirection_de_secours(url_secours: str, numero: str | None) -> str:
    """PN5: what follows ``<Connect>`` when our server drops the stream: the TwiML Bin, with
    the second number in its address (``{{Renvoi}}``). Replaces the 40 s pause."""
    adresse = url_secours if not numero else f"{url_secours}?Renvoi={quote(numero)}"
    return f'<Redirect method="POST">{escape(adresse)}</Redirect>'


def adresse_de_secours(url_secours: str, numero: str | None) -> str:
    """The ``VoiceFallbackUrl`` of a number (PN5): the same Bin, the same parameter."""
    return url_secours if not numero else f"{url_secours}?Renvoi={quote(numero)}"


def texte_du_bin(
    phrase_renvoi: str = DEFAUT_RENVOI,
    phrase_rappel: str = DEFAUT_RAPPEL_SANS_DATE,
    sonnerie_s: int = 20,
) -> str:
    """The text to paste ONCE in the client's Twilio console (TwiML Bins). It knows no hours,
    so its promise has no date (PN5, limit 1)."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<Response>\n'
        f"  {_dire(phrase_renvoi)}\n"
        f'  <Dial timeout="{int(sonnerie_s)}">{{{{Renvoi}}}}</Dial>\n'
        f"  {_dire(phrase_rappel)}\n"
        "  <Hangup/>\n</Response>\n"
    )
