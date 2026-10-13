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
- the telephone alphabet (🆕 plan courriel-dicte, D6): "P comme Pascal", "N pour
  Nathalie", "C de Carine", "P, Pascal": the confirming word is read, never written; a
  word of a closed list wins over a letter it does not agree with (P/B, M/N, F/S),
  and a letter lost before "comme Ursule" is its initial (``_confirmation``);
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

# 🆕 courriel-dicte (Evan, 13/10 : « un module parfait ») : les chiffres sont des mots
# à part entière, pour l'adresse mail (« jean75 arobase… »). Une suite épelée s'arrête
# sur eux ; avant, ils étaient invisibles et la suite les sautait.
MOTS = re.compile(r"[A-Za-zÀ-ÿ']+|\d+|[.,;:!?]")

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
        "sur", "dans", "ou", "envoyer", "envoyez", "ecrire", "écrire", "mails", "e-mail",
        "perso", "pro", "professionnelle", "personnelle", "bonjour", "merci", "parfait",
        "écrivez", "ecrivez", "notez", "note",
        # Revue du 13/10 : « mon prénom point mon nom arobase… », « le nom de la boîte
        # arobase… » décrivent une adresse, ils n'en sont pas une.
        "nom", "prénom", "prenom", "société", "societe", "boîte", "boite", "entreprise",
    }
)


# --- The telephone alphabet (plan courriel-dicte, D6 and lot 1 bis) --------
# "P comme Pascal", "N pour Nathalie", "C de Carine": the word confirms the letter,
# it is never written. Links, the longest first; "rien" ("P Pascal") only with a word
# of the closed list below.
LIENS_FORTS = ((",", "comme", "dans"), (",", "comme"), ("comme", "dans"), ("comme",))
LIENS_FAIBLES = ((",", "c'est"), (",",), ("pour",), ("de",), ("c'est",))
# 🔑 The CLOSED list of confirming words: the French spelling alphabet, then usual
# first names and words. Only a word of this list may OVERRIDE the letter it follows
# (rule 2: the network confuses P and B, M and N, F and S; the word exists for that) or
# stand for a letter the transcription lost (rule 3). Generic: no customer's word here.
# Written without accents, lowercase (compared through ``_sans_accent``).
MOTS_DE_CONFIRMATION = frozenset(
    {
        # The French spelling alphabet.
        "anatole", "berthe", "celestin", "desire", "eugene", "francois", "gaston",
        "henri", "irma", "joseph", "kleber", "louis", "marcel", "nicolas", "oscar",
        "pierre", "quintal", "raoul", "suzanne", "therese", "ursule", "victor",
        "william", "xavier", "yvonne", "zoe", "emile",
        # Usual first names and words said to confirm a letter.
        "alice", "andre", "antoine", "bernard", "bertrand", "camille", "carine",
        "caroline", "celine", "charles", "claude", "daniel", "david", "denis", "emilie",
        "eric", "etienne", "fabien", "frederic", "georges", "gerard", "helene", "hugo",
        "isabelle", "jacques", "jean", "julie", "julien", "karine", "kevin", "laurent",
        "leon", "lucie", "marie", "martine", "michel", "nathalie", "noel", "olivier",
        "pascal", "patrick", "paul", "philippe", "quentin", "rene", "robert", "roger",
        "simon", "sophie", "sylvie", "thierry", "thomas", "ulysse", "valerie",
        "vincent", "walter", "yann", "yves", "zorro", "framboise", "zebre",
    }
)


# The words that carry a spelling on ("m a de double l e"): "de" before them is a letter.
MOTS_D_EPELLATION = frozenset(
    {"deux", "double", "trois", "tiret", "accent", "apostrophe", "espace", "trait", "avec"}
)
# Un nombre dit en mots dans la partie locale d'une adresse (« jean soixante quinze
# arobase… ») s'écrit en chiffres (Evan, 13/10 : lire les chiffres, question n° 345).
NOMBRES_EN_MOTS = frozenset(
    {
        "zéro", "zero", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit",
        "neuf", "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize", "vingt",
        "trente", "quarante", "cinquante", "soixante", "septante", "huitante", "nonante",
        "cent", "cents", "mille",
    }
)

# 🔑 Revue du 13/10 (bloquant) : un mot de la liste ne l'emporte sur la lettre QUE pour les
# paires que le réseau téléphonique confond (règle 2 du plan). Sans cette borne, « j e a n,
# Jean » s'écrivait « Jeaj » et « d u p o n t pour Nathalie » « Duponn », en silence.
LETTRES_CONFONDUES = (frozenset("pb"), frozenset("mn"), frozenset("fs"))


def _confondues(une: str, autre: str) -> bool:
    return frozenset((_sans_accent(une), _sans_accent(autre))) in LETTRES_CONFONDUES


def _sans_accent(texte: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texte) if not unicodedata.combining(c)
    ).lower()


def _confirmation(
    mots: list[tuple[str, int, int]], rang: int, lettre: str | None
) -> tuple[int, str | None, str | None] | None:
    """A confirming word starting at ``rang``, right after ``lettre`` (``None``: right
    after another confirmation, where the letter may have been lost).

    Returns (words consumed, letter to write instead -- or to add when ``lettre`` is
    ``None`` --, doubt to report) or ``None``. Rules of the plan, lot 1 bis:
    1. after a letter, a link and a word that STARTS with that letter are swallowed;
       a weak link ("pour", "de", "c'est", a comma) needs a word of the list or a
       capitalized one, so "s, sans accent" stays what it is;
    2. a word of the list that does not agree wins over the letter ONLY for the pairs
       the network confuses, P/B, M/N, F/S ("B comme Pascal" is P), and only after
       "comme"; any other disagreement ends the spelling, nothing swallowed ("j e a n,
       Jean" stays "Jean", "m a r t i n, Michel" stays "Martin": reviews of 13/10). A capitalized word outside the
       list after "comme", the spelling going on after it, keeps the letter and is
       reported ("B comme Parapluie, l e");
    3. "comme Pascal" right after a confirmation, the letter lost: the word's initial;
    4. "de" followed by a confirming word is a link, never the letter D;
    5. ⛔ no letter before, nothing: "comme Pascal me l'a dit" opens nothing (the
       caller of this function only calls it inside a sequence already started).
    """
    debut = rang
    if lettre is None and debut < len(mots) and mots[debut][0] == ",":
        debut += 1
    liens = [(lien, True) for lien in LIENS_FORTS]
    if lettre is not None:
        liens += [(lien, False) for lien in LIENS_FAIBLES] + [((), False)]
    for lien, fort in liens:
        n = len(lien)
        if tuple(m[0].lower() for m in mots[debut:debut + n]) != lien or debut + n >= len(mots):
            continue
        mot = mots[debut + n][0]
        if len(mot) < 3 or not mot.isalpha():
            continue
        initiale = _sans_accent(mot)[0]
        connu = _sans_accent(mot) in MOTS_DE_CONFIRMATION
        consomme = debut + n + 1 - rang
        if lettre is None:
            return (consomme, initiale, None) if connu else None
        if not lien and not connu:
            continue
        if _sans_accent(lettre) == initiale:
            if connu or fort or mot[0].isupper():
                return consomme, None, None
            continue
        if connu:
            # Revue n° 2 du 13/10 : seulement derrière « comme ». Derrière une virgule,
            # « pour » ou « de », c'est le prénom qui suit le nom (« m a r t i n,
            # Michel » écrivait « Martim »).
            if fort and _confondues(lettre, initiale):
                return consomme, initiale, None
            continue
        # The spelling goes on after the word: a letter said alone, possibly after a
        # comma. Otherwise "f l a m a n t comme Martin me l'a dit" is a sentence.
        suite = debut + n + 1
        if suite < len(mots) and mots[suite][0] == ",":
            suite += 1
        if fort and mot[0].isupper() and _seule(mots, suite):
            return consomme, None, f"{lettre.upper()} comme {mot}"
    return None


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
    # 🆕 lot 1 bis: a letter its confirming word does not agree with, the word being
    # outside the closed list ("B comme Parapluie"): the letter is kept, the note asks
    # for it to be confirmed.
    doutes: tuple[str, ...] = ()


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


def _chiffres_isoles(mots: list[tuple[str, int, int]], rang: int) -> bool:
    """Digits that belong to an address: one group of at most four digits (« jean75 »,
    « dupont 1975 »), or at most four digits said one by one (« j e a n 7 5 »). Never a
    run of groups: « 06 12 34 56 78 jean arobase… » is a phone number, not the address."""
    if not 0 <= rang < len(mots) or not mots[rang][0].isdigit():
        return False
    debut = fin = rang
    while debut > 0 and mots[debut - 1][0].isdigit():
        debut -= 1
    while fin + 1 < len(mots) and mots[fin + 1][0].isdigit():
        fin += 1
    groupes = [mots[r][0] for r in range(debut, fin + 1)]
    if len(groupes) == 1:
        return len(groupes[0]) <= 4
    return all(len(g) == 1 for g in groupes) and len(groupes) <= 4


# Fallback when ``text_to_num`` leaves a small number in words (« deux » stays « deux »).
UNITES = {
    "zéro": "0", "zero": "0", "deux": "2", "trois": "3", "quatre": "4", "cinq": "5",
    "six": "6", "sept": "7", "huit": "8", "neuf": "9", "dix": "10",
}


def _en_chiffres(nombre: list[str]) -> str | None:
    """« soixante quinze » -> ``75``, « deux mille » -> ``2000``; None if unsure."""
    try:
        from text_to_num import alpha2digit

        ecrit = alpha2digit(" ".join(nombre), "fr").replace(" ", "")
    except Exception:  # noqa: BLE001 -- unsure: no reading
        return None
    if ecrit.isdigit():
        return ecrit
    chiffres = [UNITES.get(mot) for mot in nombre]
    return "".join(chiffres) if all(chiffres) else None


def _lire_courriel(
    mots: list[tuple[str, int, int]], place: int, largeur: int, faible: bool
) -> tuple[int, int, str, tuple[str, ...]] | None:
    """The address around the "@" said at ``place`` (``largeur`` words), or None.

    Left of "@": letters said alone, whole words, "point / tiret / tiret bas", up to a
    word of the sentence (``OUTILS_AVANT_COURRIEL``). Right of "@": the domain, a name
    said in several words glued back from the list of domains ("hot mail"), then
    "point" and its extension ("com", "f r"); after an extension, only another
    "point" or "tiret" goes on ("point f r, merci" ends at ``fr``).
    """
    from api.services.epellation.domaines import DOMAINES, formes_dites

    noms_de_domaine = {domaine.split(".", 1)[0] for domaine in DOMAINES}

    # 🆕 lot 1 bis: "p comme Pascal a u l arobase…" -- the link and its word belong to
    # the address (they are read), they are never written.
    confirmations: dict[int, tuple[int, str | None]] = {}
    for rang in range(place):
        if _seule(mots, rang) and (lue := _confirmation(mots, rang + 1, mots[rang][0].lower())):
            confirmations[rang] = (lue[0], lue[1])
    couverts = {r + k for r, (n, _) in confirmations.items() for k in range(1, n + 1)}

    def gauche(rang: int) -> bool:
        if not 0 <= rang < len(mots):
            return False
        if rang in couverts:
            return True
        mot = mots[rang][0].lower()
        if mot.isdigit():
            return _chiffres_isoles(mots, rang)
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
        if mot.isdigit():
            return _chiffres_isoles(mots, rang)
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
    # Relecture n° 4 : un nombre dit juste avant l'adresse, séparé d'elle par un espace
    # (« c'est le 15 evan arobase… »), n'en fait pas partie.
    while (
        debut < place - 1
        and mots[debut][0].isdigit()
        and not mots[debut + 1][0].isdigit()
        and mots[debut + 1][1] > mots[debut][2]
    ):
        debut += 1
    if debut == place:
        return None

    formes = formes_dites()
    plus_longue = max((len(f) for f in formes), default=1)
    domaine: list[str] = []
    # Revue du 13/10 : deux mots dits l'un après l'autre sont recollés sans séparateur
    # (« jean pierre » -> ``jeanpierre``) : une supposition, donc à faire confirmer.
    colles: list[str] = []
    doutes_nombres: list[str] = []
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
            ecrit = nom if nom else _ecrire_mot(mots, rang)
            if not nom and len(ecrit) > 1 and domaine and len(domaine[-1]) > 1:
                colles.append(f"{domaine[-1]} {ecrit}")
            domaine.append(ecrit)
            rang += 1
    fin = rang - 1

    local: list[str] = []
    precedent = None  # the rank of the last word written, to see the space after it
    rang = debut
    while rang < place:
        mot = mots[rang][0].lower()
        if mot in REPETITIONS and _seule(mots, rang + 1) and rang + 1 < place:
            # « b o deux t e » : a repetition, never a number.
            local.append(mots[rang + 1][0].lower() * REPETITIONS[mot])
            precedent, rang = rang + 1, rang + 2
            continue
        if mot in NOMBRES_EN_MOTS - {"un"}:
            # 🆕 « jean soixante quinze arobase… » (Evan, 13/10) : le nombre dit en mots
            # s'écrit en chiffres ; c'est une lecture, donc à faire confirmer.
            nombre = []
            while rang < place and mots[rang][0].lower() in NOMBRES_EN_MOTS - {"un"}:
                nombre.append(mots[rang][0].lower())
                rang += 1
            chiffres = _en_chiffres(nombre)
            if chiffres is None:
                return None
            doutes_nombres.append(f"« {' '.join(nombre)} » écrit {chiffres}")
            local.append(chiffres)
            precedent = rang - 1
            continue
        if rang in confirmations:
            consomme, nouvelle = confirmations[rang]
            local.append(nouvelle or mot)
            rang += 1 + consomme
            continue
        if rang in couverts:
            # The address starts inside a confirmation: its word is not written.
            rang += 1
            continue
        if mot == "tiret" and rang + 1 < place and mots[rang + 1][0].lower() == "bas":
            local.append("_")
            rang += 2
            continue
        ecrit = SEPARATEURS_COURRIEL.get(mot) or _ecrire_mot(mots, rang)
        # Glued only when a SPACE was said between them: « jean75 » is one word.
        espace = precedent is not None and mots[rang][1] > mots[precedent][2]
        if len(ecrit) > 1 and local and len(local[-1]) > 1 and espace:
            colles.append(f"{local[-1]} {ecrit}")
        local.append(ecrit)
        precedent = rang
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
    # Revue du 13/10 : « at » seulement devant un domaine de la liste (« un compte at
    # home point net » n'est pas une adresse).
    if faible and partie_domaine.split(".", 1)[0] not in noms_de_domaine:
        return None
    adresse = f"{partie_locale}@{partie_domaine}"
    doutes = [f"« {paire} » écrit sans séparateur" for paire in colles] + doutes_nombres
    # Revue du 13/10 : une adresse ne porte pas d'accent ; la transcription en met
    # (« hélène »). Retiré, et signalé : c'est une supposition.
    sans_accent = _sans_accent(adresse)
    if sans_accent != adresse:
        doutes.append(f"accents retirés (« {adresse} »)")
        adresse = sans_accent
    return debut, fin, adresse, tuple(doutes)


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
        debut, fin, ecrit, doutes_adresse = adresse
        adresses[debut] = (fin, ecrit, doutes_adresse)
        occupes |= set(range(debut, fin + 1))

    trouvees: list[Epellation] = []
    rang = 0
    while rang < len(mots):
        if rang in adresses:
            fin, ecrit, doutes_adresse = adresses[rang]
            trouvees.append(
                Epellation(
                    mots[rang][1],
                    mots[fin][2],
                    ecrit,
                    texte[mots[rang][1]:mots[fin][2]],
                    courriel=True,
                    domaine_proche=domaine_proche(ecrit.rsplit("@", 1)[-1]),
                    doutes=doutes_adresse,
                )
            )
            rang = fin + 1
            continue

        suivant, lettres, debut, franches = rang, [], None, 0
        # 🆕 lot 1 bis: what came last ("lettre", "confirmation", other), and the doubts.
        etat, doutes = None, []
        # 🆕 « p a u l, P comme Pierre » (Evan, 13/10) : des lettres dites seules, puis,
        # après une virgule, une lettre DÉJÀ dite confirmée par son mot : c'est une
        # reconfirmation, pas une lettre de plus (« Paulp » avant). Seulement quand rien
        # n'a été épelé en alphabet avant : « …, A comme André » dans « Panchaud » est une
        # vraie lettre.
        alphabet_avant, apres_virgule = False, False
        while suivant < len(mots):
            if suivant in occupes:
                # A sequence never runs into an address already read.
                break
            mot = mots[suivant][0]
            minuscule = mot.lower()

            # "P comme Pascal", "N pour Nathalie", "C de Carine" (the telephone alphabet).
            if lettres and etat in ("lettre", "confirmation"):
                lue = _confirmation(mots, suivant, lettres[-1] if etat == "lettre" else None)
                if lue:
                    consomme, nouvelle, doute = lue
                    if etat == "lettre" and nouvelle:
                        lettres[-1] = nouvelle
                    elif etat == "confirmation":
                        lettres.append(nouvelle)
                    if doute:
                        doutes.append(doute)
                    alphabet_avant = True
                    # A confirmed letter is a spelled letter.
                    franches += 1
                    suivant += consomme
                    etat = "confirmation"
                    continue
            etat = None

            if mot in ".,;:!?":
                # A full stop between two spelled letters does not end them.
                if lettres and suivant + 1 < len(mots) and _lettre(mots[suivant + 1][0]):
                    apres_virgule = mot == ","
                    suivant += 1
                    continue
                break

            apres = mots[suivant + 1][0].lower() if suivant + 1 < len(mots) else ""

            if minuscule == "double" and apres in ("v", "ve", "vé"):
                lettres.append("w")
                debut = mots[suivant][1] if debut is None else debut
                suivant += 2
                etat = "lettre"
                continue
            if minuscule in ("2", "3") and lettres and len(apres) == 1 and apres.isalpha():
                # Relecture n° 4 : « d u p o n 2 t » quand la transcription écrit le
                # chiffre ; depuis que les chiffres sont des mots, il coupait la suite.
                minuscule = "deux" if minuscule == "2" else "trois"
            if minuscule in REPETITIONS and (repetee := _lettre(apres)):
                lettres += [repetee] * REPETITIONS[minuscule]
                if len(apres) == 1 and _franche(repetee):
                    franches += 1
                debut = mots[suivant][1] if debut is None else debut
                suivant += 2
                etat = "lettre"
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

            # Revue du 13/10 : « r o b e r t de Robert » : « de » devant un mot est la
            # préposition, pas la lettre D (« Robertd »). Il finit la suite.
            if (
                minuscule == "de"
                and len(apres) > 2
                and apres.isalpha()
                and not _lettre(apres)
                and apres not in MOTS_D_EPELLATION
            ):
                break
            if apres_virgule and lettres and not alphabet_avant and len(mot) == 1 and mot.isalpha():
                lue = _confirmation(mots, suivant + 1, mot.lower())
                deja = {_sans_accent(x) for x in lettres if x.isalpha()}
                apres_lue = suivant + 1 + lue[0] if lue else 0
                if apres_lue < len(mots) and mots[apres_lue][0] == ",":
                    apres_lue += 1
                # Relecture n° 4 : seulement quand l'épellation S'ARRÊTE après la
                # confirmation ; « b o n, N comme Nicolas, e » est « Bonne » (une lettre
                # doublée, c'est justement là qu'on passe à l'alphabet).
                if (
                    lue
                    and lue[2] is None
                    and _sans_accent(lue[1] or mot) in deja
                    and not (
                        # Une lettre seule SANS mot qui la confirme : le nom continue.
                        # « p a u l, p comme Pierre, l comme Louis » reste une relecture.
                        _seule(mots, apres_lue)
                        and not _confirmation(mots, apres_lue + 1, mots[apres_lue][0].lower())
                    )
                ):
                    suivant += 1 + lue[0]
                    apres_virgule = False
                    continue
            apres_virgule = False
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
                etat = "lettre"
                continue
            break

        compte = sum(1 for x in lettres if x.isalpha())
        if compte >= LETTRES_MINIMUM and franches:
            epele = _capitaliser("".join(lettres).strip("- "))
            trouvees.append(
                Epellation(
                    debut,
                    mots[suivant - 1][2],
                    epele,
                    texte[debut:mots[suivant - 1][2]],
                    doutes=tuple(doutes),
                )
            )
            rang = suivant
        else:
            rang += 1
    return trouvees
