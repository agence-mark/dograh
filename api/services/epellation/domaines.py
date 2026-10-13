"""[.mark] The common e-mail domains and how callers say them (plan courriel-dicte, D3).

ONE list for the whole fork, generic (it holds for every customer): the end-of-call
check (``fiche/controle.py``) imports it instead of keeping its own.

It serves three things, and never a fourth:
1. **read**: a domain said in several words is glued back before the address is
   written ("hot mail" -> ``hotmail``, "g mail" -> ``gmail``, "la poste" -> ``laposte``);
2. **flag**: a domain close to a known one but not it (``gmial.com``) is REPORTED so the
   agent has it confirmed;
3. **check**: the same flag at the end of the call (``courriel_domaine_douteux``).

⛔ It never corrects a domain in silence: the reader reports, the note says what to
have confirmed (the module's rule: it does not change the caller's words).

The spoken forms were written from the corpus of 2026-10-13 (lot 0, 1 142 runs): the
transcription wrote "arobase", "point f r" and "Gmail" cleanly; the split forms below
("g mail", "hot mail") are the plausible ones, not yet seen in a real call.
"""

from __future__ import annotations

# Domain -> the ways a caller says its name part, as the transcription writes them
# (lowercase, words separated by one space). The name itself is always understood.
DOMAINES: dict[str, tuple[str, ...]] = {
    "gmail.com": ("g mail", "gé mail", "gee mail", "ji mail", "j mail"),
    "googlemail.com": ("google mail",),
    "hotmail.fr": ("hot mail", "hotte mail"),
    "hotmail.com": ("hot mail", "hotte mail"),
    "outlook.fr": ("out look", "aout look"),
    "outlook.com": ("out look", "aout look"),
    "live.fr": (),
    "live.com": (),
    "msn.com": ("m s n",),
    "yahoo.fr": ("ya hoo", "yaou"),
    "yahoo.com": ("ya hoo", "yaou"),
    "ymail.com": ("y mail", "i grec mail"),
    "icloud.com": ("i cloud", "aïe cloud"),
    "me.com": (),
    "mac.com": (),
    "orange.fr": (),
    "wanadoo.fr": ("wana doo", "wanadou"),
    "free.fr": (),
    "sfr.fr": ("s f r",),
    "neuf.fr": (),
    "cegetel.net": (),
    "club-internet.fr": ("club internet",),
    "numericable.fr": ("numéricable", "numeri cable"),
    "bbox.fr": ("b box", "bé box"),
    "laposte.net": ("la poste",),
    "gmx.fr": ("g m x",),
    "gmx.com": ("g m x",),
    "aol.com": ("a o l",),
    "protonmail.com": ("proton mail",),
    "proton.me": (),
    "aliceadsl.fr": ("alice adsl", "alice a d s l"),
    # ⛔ No spoken form: "voilà" closes a sentence ("point f r, voilà"), it is never a domain.
    "voila.fr": (),
}

DOMAINES_COURANTS: tuple[str, ...] = tuple(DOMAINES)

# Same threshold as the end-of-call check (QD3): at or above, a domain is "close".
SEUIL_DOMAINE = 85.0


def formes_dites() -> dict[tuple[str, ...], str]:
    """Spoken form (as words) -> the name part to write. Longest forms first matter to
    the reader, which tries every length; ``"hot mail"`` and ``"hotmail"`` both give
    ``hotmail``."""
    formes: dict[tuple[str, ...], str] = {}
    for domaine, dites in DOMAINES.items():
        nom = domaine.split(".", 1)[0]
        for dite in dites:
            formes.setdefault(tuple(dite.split()), nom)
    return formes


def domaine_proche(domaine: str) -> str | None:
    """The known domain ``domaine`` probably meant, when it is close to one but not it.
    ``None`` for a known domain or one that resembles none. Never raises."""
    try:
        domaine = (domaine or "").strip().lower()
        if not domaine or domaine in DOMAINES:
            return None
        from rapidfuzz import fuzz

        proche = max(DOMAINES_COURANTS, key=lambda d: fuzz.ratio(domaine, d))
        return proche if fuzz.ratio(domaine, proche) >= SEUIL_DOMAINE else None
    except Exception:  # noqa: BLE001 -- a flag never costs the reading
        return None
