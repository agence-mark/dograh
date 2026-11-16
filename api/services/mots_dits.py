"""[.mark] Mécanisme commun : la MISE EN MOTS de ce que l'agent dit (lot 26, M26) : montants, heures, durées et noms accordés, toujours en lettres.

Un seul module pour tout ce que le code propose à la voix : jamais « 25,00 euros », « 5 h 11 » ni « un Chaise ». Les phrases sont PROPOSÉES : le réglage
de l'outil dit si le modèle les prononce mot pour mot ou les reformule (T-01). Aucun mot d'un métier ici : le lexique d'un métier (genres, noms
communs) vient de l'appelant. Pur : ni base, ni heure réelle.
"""

from __future__ import annotations

import re


def _lettres(n: int) -> str:
    try:
        from num2words import num2words  # dépendance de Pipecat, chargée à la demande comme ``services/nombres/voix.py``

        return num2words(n, lang="fr")
    except Exception:  # noqa: BLE001 -- un nombre qu'on ne sait pas écrire reste en chiffres plutôt que de casser l'appel
        return str(n)


def montant_en_lettres(centimes: int) -> str:
    """``2380`` -> « vingt-trois euros quatre-vingts » ; ``1000`` -> « dix euros » ; ``50`` -> « cinquante centimes »."""
    euros, reste = divmod(max(int(centimes), 0), 100)
    morceaux = []
    if euros or not reste:
        morceaux.append(f"{_lettres(euros)} euro{'s' if euros > 1 else ''}")
    if reste:
        morceaux.append(_lettres(reste) if euros else f"{_lettres(reste)} centime{'s' if reste > 1 else ''}")
    return " ".join(morceaux)


def nombre_en_lettres(n: int) -> str:
    """``25`` -> « vingt-cinq » : le nombre tel qu'on le dit (jamais en chiffres à lire)."""
    return _lettres(int(n))


def _lettres_f(n: int) -> str:
    """Le nombre devant un nom féminin : « une », « vingt et une »."""
    t = _lettres(n)
    return t + "e" if t.endswith("un") else t


def heure_en_lettres(heure: int, minute: int) -> str:
    """``(20, 15)`` -> « vingt heures quinze » ; ``(19, 30)`` -> « dix-neuf heures trente » ; ``(12, 0)`` -> « douze heures » ; ``(0, 0)`` -> « minuit »."""
    if heure == 0 and not minute:
        return "minuit"
    base = f"{_lettres_f(heure)} heure{'s' if heure > 1 else ''}" if heure else "zéro heure"
    return f"{base} {_lettres(minute)}" if minute else base


def duree_en_lettres(minutes: int) -> str:
    """``30`` -> « trente minutes » ; ``1`` -> « une minute » ; ``60`` -> « une heure » ; ``90`` -> « une heure trente »."""
    minutes = max(int(minutes), 0)
    heures, reste = divmod(minutes, 60)
    if not heures:
        return f"{_lettres_f(reste)} minute{'s' if reste > 1 else ''}"
    base = f"{_lettres_f(heures)} heure{'s' if heures > 1 else ''}"
    return f"{base} {_lettres(reste)}" if reste else base


# --------------------------------------------------------------------------- #
# Les noms dits : article, genre, pluriel (M26). Aucun mot du métier ici : ce qui est propre à un lexique vient de l'appelant.
# --------------------------------------------------------------------------- #

_FEMININ_EN = ("tion", "sion", "té", "tié", "ée", "ette", "ure", "ance", "ence", "ie", "ine", "esse", "ade", "ille", "a")
_MASCULIN_EN = ("age", "ège", "isme", "ment", "ème", "eau", "ier", "eur", "ing", "er", "ot")


def genre_du_mot(mot: str, connus: dict[str, str] | None = None) -> str:
    """``"f"`` ou ``"m"`` : d'abord le lexique ``connus`` (mot sans accent ni majuscule -> genre), puis la terminaison du mot ; masculin par défaut
    (un mot qu'on ne sait pas classer reste « un »)."""
    brut = mot.strip().casefold()
    if connus and brut in connus:
        return connus[brut]
    if brut.endswith(_MASCULIN_EN):
        return "m"
    if brut.endswith(_FEMININ_EN):
        return "f"
    return "f" if brut.endswith("e") and not brut.endswith(("é", "ée")) and len(brut) > 3 else "m"


def pluriel_du_mot(mot: str) -> str:
    """``"joint"`` -> « joints » ; ``"bateau"`` -> « bateaux » ; ``"cheval"`` -> « chevaux » ; ``"vis"`` -> « vis » ; invariable : s, x, z, et tout mot à trait d'union."""
    if not mot or "-" in mot or mot.endswith(("s", "x", "z")):
        return mot
    if mot.endswith(("eau", "eu")) and not mot.endswith("pneu"):
        return mot + "x"
    if mot.endswith("al") and len(mot) > 3:
        return mot[:-2] + "aux"
    return mot + "s"


def article_indefini(genre: str | None) -> str:
    return "une" if genre == "f" else "un"


def nom_dit(nom: str, quantite: int = 1, *, genre: str | None = None, commun: bool = False) -> str:
    """Un nom précédé de sa quantité, accordé : ``("Chaise haute", 1, genre="f", commun=True)`` -> « une chaise haute » ;
    ``("Joint", 2, genre="m", commun=True)`` -> « deux joints ». ``commun`` : le premier mot est un nom commun (minuscule, pluriel) ;
    sinon c'est un nom propre qui garde sa majuscule et ne prend pas de marque du pluriel (« deux Dupont »). Le reste du nom ne change pas."""
    nom = " ".join((nom or "").split())
    mots = nom.split(" ") if nom else []
    if commun and mots:
        premier = mots[0][:1].lower() + mots[0][1:]
        mots[0] = pluriel_du_mot(premier) if quantite > 1 else premier
    corps = " ".join(mots)
    if quantite == 1:
        return f"{article_indefini(genre)} {corps}".strip()
    return f"{_lettres(quantite)} {corps}".strip()


_RE_MONTANT = re.compile(r"(?<![\w.,])(\d{1,6})(?:[,.](\d{1,2}))?\s*(?:€|euros?\b|eur\b)", re.IGNORECASE)
_RE_POURCENT = re.compile(r"(?<![\w.,])(\d{1,3})(?:[,.](\d{1,2}))?\s*%")
_RE_HEURE = re.compile(r"(?<![\w.,:])(\d{1,2})\s*(?:h|:)\s*(\d{2})?(?![\w])", re.IGNORECASE)
_RE_ENTIER = re.compile(r"(?<![\w.,:-])(\d{1,6})(?![\w.,:])")


def _montant_trouve(m: re.Match) -> str:
    euros, centimes = int(m.group(1)), m.group(2)
    reste = int(centimes.ljust(2, "0")) if centimes else 0
    return montant_en_lettres(euros * 100 + reste)


def chiffres_en_lettres(texte: str) -> str:
    """Les chiffres d'une phrase écrite par une personne (``phrase`` d'une offre, note) passent en lettres, comme on les dit : « 12,50 € » ->
    « douze euros cinquante » ; « 20 % » -> « vingt pour cent » ; « 19 h 30 » -> « dix-neuf heures trente » ; « 2 joints » -> « deux joints ».
    Ce qui n'est pas un nombre isolé (un numéro, une référence collée à des lettres) n'est pas touché."""
    sortie = _RE_MONTANT.sub(_montant_trouve, texte or "")
    sortie = _RE_POURCENT.sub(lambda m: f"{_lettres(int(m.group(1)))}{' virgule ' + _lettres(int(m.group(2))) if m.group(2) else ''} pour cent", sortie)
    sortie = _RE_HEURE.sub(
        lambda m: heure_en_lettres(int(m.group(1)), int(m.group(2) or 0)) if int(m.group(1)) < 24 and int(m.group(2) or 0) < 60 else m.group(0), sortie
    )
    return _RE_ENTIER.sub(lambda m: _lettres(int(m.group(1))), sortie)


def phrase_nette(texte: str) -> str:
    """Un point final et un seul, pas d'espace en trop : « En ce moment : une offre.. » -> « En ce moment : une offre. »"""
    t = " ".join((texte or "").split())
    t = re.sub(r"([.!?])(?:\s*\.)+", lambda m: m.group(1), t)
    return t


def liste_dite(elements: list[str]) -> str:
    """``["a", "b", "c"]`` -> « a, b ou c »."""
    if len(elements) <= 1:
        return "".join(elements)
    return ", ".join(elements[:-1]) + " ou " + elements[-1]


def liste_dite_et(elements: list[str]) -> str:
    """``["a", "b", "c"]`` -> « a, b et c »."""
    if len(elements) <= 1:
        return "".join(elements)
    return ", ".join(elements[:-1]) + " et " + elements[-1]
