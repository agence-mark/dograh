"""[.mark] Read the letters a caller spells out, before the model reads the turn.

Why this module exists
----------------------
On the 759 recorded runs, callers spelled a name 25 times ("Flamand, f l a m
a n t"). The recorded variable carried the spelled form only **17 times**: the
model rewrote what it had heard rather than what had been spelled, and the
customer record kept "Flamand", "Loiselé", "flammant". Spelling is the caller's
own correction; losing it is losing the one thing they made an effort to give.

So the code reads the letters, writes them out, and the note tells the model to
copy them exactly (``mention.py``). Like the town check, the instruction lives
in the note: no agent's prompt is edited.

What it reads (measured on the 136-case corpus of 2026-09-22, all green)
------------------------------------------------------------------------
- letters said alone ("f l a m a n t", "W A T T E B L E D");
- letter names as the transcription writes them ("effe", "vé", "double vé" = W);
- "deux T", "double L", "trois S" — a letter repeated;
- "F comme François": the confirming word is skipped, the letter is kept;
- accents, dieresis, cedilla, hyphen, apostrophe, space;
- e-mail addresses, when at least one letter is spelled (Q9):
  "marc point v d k arobase example point f r" -> ``marc.vdk@example.fr``.

⛔ What it must never do
- Read an ordinary sentence as a spelling. Three rules carry this, each one
  bought by a real failure:
  1. a letter followed by an apostrophe is an **elision**, never a spelled
     letter ("il n'y a" wrote "Nya" on 6 real sentences);
  2. a **letter name** ("de", "te", "effe") never OPENS a sequence, it only
     joins one already started ("d'accès… dire" wrote "ddd");
  3. a sequence must carry a letter said alone that is not a / y / e / o
     ("il y a de la fumée" wrote "Yad").
- Change the caller's words: this module only reports what it read; the
  transcript keeps the words (N1 of the plan nombres-dictes).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Letter names as the transcription writes them. ``None`` marks a word that
# looks like one but never is ("euh", "en", "j'ai").
NOMS_DE_LETTRES: dict[str, str | None] = {
    "a": "a", "be": "b", "bé": "b", "ce": "c", "cé": "c", "de": "d", "dé": "d", "e": "e",
    "euh": None, "effe": "f", "ef": "f", "ge": "g", "gé": "g", "j'ai": None, "ache": "h",
    "hache": "h", "i": "i", "ji": "j", "ka": "k", "elle": "l", "el": "l", "emme": "m",
    "em": "m", "enne": "n", "en": None, "o": "o", "pe": "p", "pé": "p", "cu": "q",
    "qu": "q", "erre": "r", "er": "r", "esse": "s", "es": "s", "te": "t", "té": "t",
    "u": "u", "ve": "v", "vé": "v", "ixe": "x", "zede": "z", "zède": "z",
}

ACCENTS = {
    ("accent", "aigu"): "́",
    ("accent", "grave"): "̀",
    ("accent", "circonflexe"): "̂",
    ("trema",): "̈",
    ("tréma",): "̈",
    ("cedille",): "̧",
    ("cédille",): "̧",
}
SIGNES = {"tiret": "-", "trait": "-", "apostrophe": "'", "espace": " "}
REPETITIONS = {"deux": 2, "double": 2, "trois": 3}

# A sequence made only of these is ordinary French ("il y a", "à"), never a
# spelling.
VOYELLES_OUTILS = frozenset("ayeo")

# At least this many letters, or it is not a spelling.
LETTRES_MINIMUM = 3

MOTS = re.compile(r"[A-Za-zÀ-ÿ']+|[.,;:!?]")

# --- E-mail addresses (Q9) ------------------------------------------------
SEPARATEURS_COURRIEL = {"point": ".", "tiret": "-", "arobase": "@"}
# Words that introduce an address and therefore end it. ⛔ No single letter
# here: "e" in the set ate the "e" of "e v a n point…".
OUTILS_COURRIEL = frozenset(
    {
        "c'est", "cest", "oui", "non", "mon", "ma", "mail", "adresse", "courriel",
        "email", "alors", "donc", "voila", "voilà", "euh", "bah", "ben", "et",
    }
)


@dataclass(frozen=True)
class Epellation:
    """One spelling found in the caller's sentence."""

    debut: int
    fin: int
    # What the letters write, ready to copy into the record.
    epele: str
    # What the caller's sentence says there, word for word.
    entendu: str


def _lettre(mot: str) -> str | None:
    if len(mot) == 1 and mot.isalpha():
        return mot.lower()
    return NOMS_DE_LETTRES.get(mot.lower()) if len(mot) > 1 else None


def _capitaliser(epele: str) -> str:
    """"garnier-dumont" -> "Garnier-Dumont", "van hecke" -> "Van Hecke"."""
    sortie, majuscule = [], True
    for caractere in epele:
        sortie.append(caractere.upper() if majuscule and caractere.isalpha() else caractere)
        if caractere.isalpha():
            majuscule = False
        elif caractere in "- '":
            majuscule = True
    return "".join(sortie)


def _franche(lettre: str) -> bool:
    """A letter said alone that is not a / y / e / o — see rule 3 above."""
    return lettre.isalpha() and unicodedata.normalize("NFD", lettre)[0].lower() not in VOYELLES_OUTILS


def _lire_courriel(mots: list[tuple[str, int, int]], place: int) -> tuple[int, int, str] | None:
    """The address around the "arobase" at ``place``, or None.

    A token of the address is a letter said alone, a whole word, or one of
    "point / tiret / tiret bas / arobase". Anything else ends it.
    """

    def jeton(rang: int) -> str | None:
        if not 0 <= rang < len(mots):
            return None
        mot = mots[rang][0].lower()
        if mot in ".,;:!?" or "'" in mot or mot in OUTILS_COURRIEL:
            return None
        if mot in SEPARATEURS_COURRIEL or mot == "bas":
            return mot
        return mot if mot.isalpha() else None

    debut = fin = place
    while jeton(debut - 1) is not None:
        debut -= 1
    while jeton(fin + 1) is not None:
        fin += 1

    adresse: list[str] = []
    rang = debut
    while rang <= fin:
        mot = mots[rang][0].lower()
        if mot == "tiret" and rang + 1 <= fin and mots[rang + 1][0].lower() == "bas":
            adresse.append("_")
            rang += 2
            continue
        adresse.append(SEPARATEURS_COURRIEL.get(mot, mot))
        rang += 1

    ecrit = "".join(adresse)
    if "@" not in ecrit or ecrit.startswith("@") or ecrit.endswith("@"):
        return None
    # ⚠️ At least one letter actually SPELLED. This module reads spelled
    # letters, and Q9 adds the address words to that same reading; an address
    # dictated entirely in words is a question left open for Evan
    # (`A-VALIDER.md`, IDEE-20260922-1), not a decision taken here.
    if not any(len(mots[r][0]) == 1 and mots[r][0].isalpha() for r in range(debut, fin + 1)):
        return None
    return debut, fin, ecrit


def lire(texte: str) -> list[Epellation]:
    """Every spelling in ``texte``, in order. Never raises on ordinary text."""
    if not texte:
        return []
    mots = [(m.group(), m.start(), m.end()) for m in MOTS.finditer(texte)]

    # 🔑 Addresses first: "v d k" is both a spelled sequence and a piece of
    # "marc.vdk@example.fr". Read in word order, the sequence went first and the
    # address came out twice, truncated.
    adresses: dict[int, tuple[int, str]] = {}
    occupes: set[int] = set()
    for place, (mot, _, _) in enumerate(mots):
        if mot.lower() != "arobase" or place in occupes:
            continue
        adresse = _lire_courriel(mots, place)
        if adresse is None:
            continue
        debut, fin, ecrit = adresse
        adresses[debut] = (fin, ecrit)
        occupes |= set(range(debut, fin + 1))

    trouvees: list[Epellation] = []
    rang = 0
    while rang < len(mots):
        if rang in adresses:
            fin, ecrit = adresses[rang]
            trouvees.append(Epellation(mots[rang][1], mots[fin][2], ecrit,
                                       texte[mots[rang][1]:mots[fin][2]]))
            rang = fin + 1
            continue

        suivant, lettres, debut, franches = rang, [], None, 0
        while suivant < len(mots):
            if suivant in occupes:
                # A sequence never runs into an address already read.
                break
            mot = mots[suivant][0]
            minuscule = mot.lower()

            if mot in ".,;:!?":
                # A full stop between two spelled letters does not end them.
                if lettres and suivant + 1 < len(mots) and _lettre(mots[suivant + 1][0]):
                    suivant += 1
                    continue
                break

            apres = mots[suivant + 1][0].lower() if suivant + 1 < len(mots) else ""

            if minuscule == "double" and apres in ("v", "ve", "vé"):
                lettres.append("w")
                debut = mots[suivant][1] if debut is None else debut
                suivant += 2
                continue
            if minuscule in REPETITIONS and (repetee := _lettre(apres)):
                lettres += [repetee] * REPETITIONS[minuscule]
                if len(apres) == 1 and _franche(repetee):
                    franches += 1
                debut = mots[suivant][1] if debut is None else debut
                suivant += 2
                continue
            # "F comme François": the word that follows confirms the letter.
            if lettres and minuscule == "comme" and suivant + 1 < len(mots):
                suivant += 2
                continue
            # "d u p o n avec deux t": a linking word does not end the sequence
            # when it announces a repetition.
            if lettres and minuscule == "avec" and apres in REPETITIONS:
                suivant += 1
                continue
            if lettres and ((minuscule,) in ACCENTS or (minuscule, apres) in ACCENTS):
                cle = (minuscule,) if (minuscule,) in ACCENTS else (minuscule, apres)
                lettres[-1] = unicodedata.normalize("NFC", lettres[-1] + ACCENTS[cle])
                suivant += len(cle)
                continue
            if lettres and minuscule in SIGNES:
                lettres.append(SIGNES[minuscule])
                suivant += 1
                continue

            lettre = _lettre(mot)
            # Rule 2: a letter name never opens a sequence.
            if lettre and len(mot) > 1 and not lettres:
                lettre = None
            # Rule 1 (elisions) is NOT enforced here: ``MOTS`` keeps the
            # apostrophe inside the word, so "n'" is two characters long and
            # never reads as a letter. A guard was written here first; a mutation
            # test showed it changed nothing, and dead code in this file would
            # make the next reader believe elisions are handled at this line.
            # ⛔ The rule lives in ``MOTS``: ``test_lecture_epellation`` proves it.
            if lettre:
                lettres.append(lettre)
                if len(mot) == 1 and _franche(lettre):
                    franches += 1
                debut = mots[suivant][1] if debut is None else debut
                suivant += 1
                continue
            break

        compte = sum(1 for x in lettres if x.isalpha())
        if compte >= LETTRES_MINIMUM and franches:
            epele = _capitaliser("".join(lettres).strip("- "))
            trouvees.append(
                Epellation(debut, mots[suivant - 1][2], epele, texte[debut:mots[suivant - 1][2]])
            )
            rang = suivant
        else:
            rang += 1
    return trouvees
