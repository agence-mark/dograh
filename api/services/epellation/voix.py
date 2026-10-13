"""[.mark] The voice says an e-mail address in words (plan courriel-dicte, lot 2).

Why
---
The agent writes an address three different ways (lot 0, runs 324, 330, 386):
``**Evan.vdk@outlook.fr**``, "G M A I L point C O M", "c-a-m-a-r-a @ g-m-a-i-l". The
address went to the voice as it was, and how Voxtral says "@" and "." could not be
heard (no audio is ever kept). Written in words before the voice, the read-back is the
same from one call to the next:

    evan.vdk@outlook.fr  ->  evan point v d k arobase outlook point f r

The rules, each one simple:
- "@" is "arobase", "." "point", "-" "tiret", "_" "tiret bas", "+" "plus";
- a piece of the address with no vowel, or of one or two letters, is spelled
  ("vdk" -> "v d k"); a piece that reads as a word stays a word ("jourde");
- a known domain's name stays a word ("gmail", "hotmail": ``domaines.py``);
- the extensions "com", "net", "org", "gouv", "info" are words, any other is spelled
  ("fr" -> "f r", "eu" -> "e u");
- digits stay digits: the numbers transform, which runs next, says them.

⛔ Only the text sent to the voice changes (a Pipecat text transform, like the
numbers): the conversation keeps what the model wrote. Never raises.
"""

from __future__ import annotations

import re

from api.services.epellation.domaines import DOMAINES

# An address, possibly wrapped in markdown (``**x@y.fr**``): the stars are left
# where they are, the markdown filter deals with them.
COURRIEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
SIGNES = {".": "point", "-": "tiret", "_": "tiret bas", "+": "plus", "%": "pourcent"}
EXTENSIONS_DITES = frozenset({"com", "net", "org", "gouv", "info"})
NOMS_CONNUS = frozenset(domaine.split(".", 1)[0] for domaine in DOMAINES)
VOYELLES = frozenset("aeiouy")


def _morceau(morceau: str, *, extension: bool = False) -> str:
    """One piece between two signs, as the voice says it."""
    if not morceau:
        return ""
    if morceau.isdigit():
        return morceau
    minuscule = morceau.lower()
    if extension:
        return minuscule if minuscule in EXTENSIONS_DITES else " ".join(minuscule)
    if minuscule in NOMS_CONNUS:
        return minuscule
    # Letters and digits mixed ("jean75"): the letters as below, the digits apart.
    parties = re.findall(r"[a-z]+|\d+", minuscule)
    dites = []
    for partie in parties:
        if partie.isdigit() or (len(partie) > 2 and VOYELLES & set(partie)):
            dites.append(partie)
        else:
            dites.append(" ".join(partie))
    return " ".join(dites)


def dire_courriel(adresse: str) -> str:
    """``evan.vdk@outlook.fr`` -> ``evan point v d k arobase outlook point f r``."""
    local, domaine = adresse.rsplit("@", 1)
    morceaux_domaine = domaine.split(".")

    def suite(texte: str, derniers_extensions: int = 0) -> list[str]:
        dits: list[str] = []
        pieces = re.split(r"([._%+-])", texte)
        rang_morceau = 0
        nombre = len([p for p in pieces if p and p not in SIGNES])
        for piece in pieces:
            if not piece:
                continue
            if piece in SIGNES:
                dits.append(SIGNES[piece])
                continue
            rang_morceau += 1
            extension = rang_morceau > nombre - derniers_extensions
            dits.append(_morceau(piece, extension=extension))
        return dits

    # Every piece after the first dot of the domain is an extension ("gouv.fr").
    extensions = max(len(morceaux_domaine) - 1, 1)
    return " ".join([*suite(local), "arobase", *suite(domaine, extensions)])


def courriels_pour_la_voix(texte: str) -> str:
    """``texte`` with every address written in words. Never raises."""
    if "@" not in texte:
        return texte
    try:
        return COURRIEL.sub(lambda m: dire_courriel(m.group()), texte)
    except Exception:  # noqa: BLE001 -- the voice must go on
        return texte
