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
- e-mail addresses (Q9): "marc point v d k arobase example point f r" ->
  ``marc.vdk@example.fr``; 🆕 said entirely in words too (plan courriel-dicte, D1:
  "evan point jourde arobase gmail point com"), a domain said in several words
  glued back from ONE list (``domaines.py``: "hot mail" -> ``hotmail``), and a domain
  close to a known one reported, never replaced (D3).

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

# --- E-mail addresses (Q9; plan courriel-dicte, D1 and D3) ---------------
SEPARATEURS_COURRIEL = {"point": ".", "tiret": "-"}
# How "@" is said. The strong forms make an address on their own; the weak ones
# ("at", "a commercial") only in front of a whole domain, point included: "at"
# and "a" are also ordinary words.
AROBASES = frozenset({"arobase", "arrobase", "arobas", "arrobas", "arobaz"})
AROBASES_FAIBLES = (("at",), ("a", "commercial"))
# Words that introduce an address and therefore end it. ⛔ No single letter
# here: "e" in the set ate the "e" of "e v a n point…".
OUTILS_COURRIEL = frozenset(
    {
        "c'est", "cest", "oui", "non", "mon", "ma", "mail", "adresse", "courriel",
        "email", "alors", "donc", "voila", "voilà", "euh", "bah", "ben", "et",
    }
)
# 🆕 D1 (an address said entirely in words): the words of the SENTENCE that end the
# address on its left. Without them, "je suis evan arobase…" glued the whole
# sentence into the address. A letter name among them ("de") still joins an address
# next to a letter said alone ("v de k").
OUTILS_AVANT_COURRIEL = OUTILS_COURRIEL | frozenset(
    {
        "je", "suis", "moi", "est", "votre", "vous", "il", "elle", "on", "nous", "le",
        "la", "les", "un", "une", "des", "du", "de", "au", "aux", "pour", "par", "avec",
        "sur", "dans", "ou", "envoyer", "envoyez", "ecrire", "écrire", "mails", "e-mail", "perso", "pro", "professionnelle", "personnelle", "bonjour",
        "merci", "parfait", "écrivez", "ecrivez", "notez", "note",
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
    # 🆕 courriel-dicte: an e-mail address, spelled or said in words.
    courriel: bool = False
    # 🆕 D3: the known domain the address's domain is close to but is not
    # ("gmial.com" -> "gmail.com"). Reported, never written in its place.
    domaine_proche: str | None = None


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


def _seule(mots: list[tuple[str, int, int]], rang: int) -> bool:
    """A letter said alone at ``rang``."""
    return 0 <= rang < len(mots) and len(mots[rang][0]) == 1 and mots[rang][0].isalpha()


def _arobase(mots: list[tuple[str, int, int]], place: int) -> tuple[int, bool] | None:
    """(how many words say "@" at ``place``, is it a weak form) or None."""
    mot = mots[place][0].lower()
    if mot in AROBASES:
        return 1, False
    for forme in AROBASES_FAIBLES:
        bout = [m[0].lower() for m in mots[place:place + len(forme)]]
        if tuple(bout) == forme:
            return len(forme), True
    return None


def _ecrire_mot(mots: list[tuple[str, int, int]], rang: int) -> str:
    """A word of the address as it is written. 🆕 A letter name next to a letter said
    alone is that letter ("v de k" -> ``vdk``), not the word."""
    mot = mots[rang][0].lower()
    lettre = NOMS_DE_LETTRES.get(mot)
    if lettre and (_seule(mots, rang - 1) or _seule(mots, rang + 1)):
        return lettre
    return mot


def _lire_courriel(
    mots: list[tuple[str, int, int]], place: int, largeur: int, faible: bool
) -> tuple[int, int, str] | None:
    """The address around the "@" said at ``place`` (``largeur`` words), or None.

    Left of "@": letters said alone, whole words, "point / tiret / tiret bas", up to a
    word of the sentence (``OUTILS_AVANT_COURRIEL``). Right of "@": the domain, a name
    said in several words glued back from the list of domains ("hot mail"), then
    "point" and its extension ("com", "f r"); after an extension, only another
    "point" or "tiret" goes on ("point f r, merci" ends at ``fr``).
    """
    from api.services.epellation.domaines import formes_dites

    def gauche(rang: int) -> bool:
        if not 0 <= rang < len(mots):
            return False
        mot = mots[rang][0].lower()
        if mot in ".,;:!?" or "'" in mot or not mot.replace("-", "").isalpha():
            return False
        if mot == "bas":
            return rang > 0 and mots[rang - 1][0].lower() == "tiret"
        if len(mot) == 1 and not mot.isascii():
            # "écrire à evan arobase…": "à" is a word, an address carries no accent.
            return False
        if len(mot) > 1 and mot in OUTILS_AVANT_COURRIEL:
            # "v de k": a letter name between letters is a letter.
            return mot in NOMS_DE_LETTRES and (_seule(mots, rang - 1) or _seule(mots, rang + 1))
        return True

    def libre(rang: int) -> bool:
        """A word the domain can carry."""
        if not 0 <= rang < len(mots):
            return False
        mot = mots[rang][0].lower()
        return (
            mot not in ".,;:!?"
            and "'" not in mot
            and mot not in OUTILS_COURRIEL
            and mot not in AROBASES
            and mot.replace("-", "").isalpha()
        )

    debut = place
    while gauche(debut - 1):
        debut -= 1
    if debut == place:
        return None

    formes = formes_dites()
    plus_longue = max((len(f) for f in formes), default=1)
    domaine: list[str] = []
    rang = place + largeur
    apres_extension = False
    while libre(rang):
        mot = mots[rang][0].lower()
        if mot == "point":
            if not libre(rang + 1) or mots[rang + 1][0].lower() in SEPARATEURS_COURRIEL:
                break
            domaine.append(".")
            rang += 1
            if _seule(mots, rang):
                # "point f r": the letters of the extension, as many as are said.
                while _seule(mots, rang):
                    domaine.append(mots[rang][0].lower())
                    rang += 1
            else:
                domaine.append(mots[rang][0].lower())
                rang += 1
            apres_extension = True
            continue
        if mot == "tiret":
            if rang + 1 < len(mots) and mots[rang + 1][0].lower() == "bas":
                domaine.append("_")
                rang += 2
            else:
                domaine.append("-")
                rang += 1
            apres_extension = False
            continue
        if apres_extension:
            break
        # A domain said in several words, the longest form first ("hot mail").
        for taille in range(min(plus_longue, len(mots) - rang), 1, -1):
            dite = tuple(m[0].lower() for m in mots[rang:rang + taille])
            if dite in formes:
                domaine.append(formes[dite])
                rang += taille
                break
        else:
            nom = formes.get((mot,))
            domaine.append(nom if nom else _ecrire_mot(mots, rang))
            rang += 1
    fin = rang - 1

    local: list[str] = []
    rang = debut
    while rang < place:
        mot = mots[rang][0].lower()
        if mot == "tiret" and rang + 1 < place and mots[rang + 1][0].lower() == "bas":
            local.append("_")
            rang += 2
            continue
        local.append(SEPARATEURS_COURRIEL.get(mot) or _ecrire_mot(mots, rang))
        rang += 1

    partie_locale, partie_domaine = "".join(local), "".join(domaine)
    if not partie_locale.strip("._-") or not partie_domaine.strip("._-"):
        return None
    epelee = any(_seule(mots, r) for r in range(debut, fin + 1))
    # 🆕 D1 (Evan, 12/10): an address said entirely in words IS read, but only with a
    # whole domain, point included. Without a letter said alone, "arobase gmail" is a
    # beginning, not an address: nothing is invented. A weak "@" ("at") never makes an
    # address without that point either.
    if (faible or not epelee) and "." not in partie_domaine.strip("."):
        return None
    if partie_domaine.endswith((".", "-")):
        return None
    return debut, fin, f"{partie_locale}@{partie_domaine}"


def lire(texte: str) -> list[Epellation]:
    """Every spelling in ``texte``, in order. Never raises on ordinary text."""
    if not texte:
        return []
    mots = [(m.group(), m.start(), m.end()) for m in MOTS.finditer(texte)]

    # 🔑 Addresses first: "v d k" is both a spelled sequence and a piece of
    # "marc.vdk@example.fr". Read in word order, the sequence went first and the
    # address came out twice, truncated.
    from api.services.epellation.domaines import domaine_proche

    adresses: dict[int, tuple[int, str]] = {}
    occupes: set[int] = set()
    for place in range(len(mots)):
        if place in occupes:
            continue
        forme = _arobase(mots, place)
        if forme is None:
            continue
        adresse = _lire_courriel(mots, place, *forme)
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
            trouvees.append(
                Epellation(
                    mots[rang][1],
                    mots[fin][2],
                    ecrit,
                    texte[mots[rang][1]:mots[fin][2]],
                    courriel=True,
                    domaine_proche=domaine_proche(ecrit.rsplit("@", 1)[-1]),
                )
            )
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
