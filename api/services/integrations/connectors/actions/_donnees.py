"""[.mark] Small shared pieces of the data connectors (Google Sheets, Airtable): not a connector."""

from __future__ import annotations


def colonne_index(lettres: str) -> int:
    """« A » is 0, « C » is 2, « AA » is 26. Anything else is refused."""
    texte = str(lettres).strip().upper()
    if not texte.isalpha() or not texte.isascii():
        raise ValueError(f"« {lettres} » is not a column letter.")
    n = 0
    for ch in texte:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def chiffres_finaux(texte: object, n: int = 9) -> str:
    """The last digits of a phone number, so that « +33 6 12 34 56 78 » and « 06 12 34 56 78 » match."""
    return "".join(ch for ch in str(texte or "") if ch.isdigit())[-n:]
