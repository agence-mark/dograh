"""[.mark] Mécanisme commun : le NUMÉRO d'un élément d'une liste fermée (capacité C2, SA-48).

Beaucoup de listes numérotent leurs éléments : le client dit « le 46 », « deux J24 », « un 16b ». Un numéro est une CLÉ, pas un nom : il se
retrouve par correspondance EXACTE sur sa forme normalisée, jamais approchée (« 46 » ne donne jamais « 47 »). Ce module lit les deux côtés :

- ``cle_ecrite("J 24")`` : le numéro écrit dans la liste (``J24``, ``46``, ``16b``), ramené à une clé (``j24``, ``46``, ``16b``) ;
- ``cles_dites("le numéro quarante-six")`` : ce que le client dit, ramené aux clés possibles (``46``). Plusieurs clés seulement quand
  un mot est ambigu (« un » est un mot de politesse OU le chiffre un, « n » est « numéro » OU la lettre N) : le moteur les essaie
  toutes et pose une question si elles désignent des éléments différents.

Une dictée n'est lue comme un numéro que si TOUTE la phrase en est un : [lettres] nombre [lettre]. « 4 fromages », « Coca 33 cl » ou
« lot 1 » ne sont pas des numéros et suivent la recherche par le nom. Aucun mot propre à un métier ici : seulement des nombres français.
"""

from __future__ import annotations

import re
import unicodedata

# Mots de politesse ou de renvoi qui précèdent un numéro : toujours ignorés.
_AVANT_SUR = frozenset({"le", "la", "les", "l", "numero", "num", "no", "code", "ref", "reference", "article", "produit"})
# Ambigus : ignorés OU lus comme un chiffre (un, une) ou une lettre (n).
_AVANT_AMBIGUS = frozenset({"un", "une", "n"})
_SUFFIXES_MOTS = frozenset({"bis", "ter"})

_UNITES = {"zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9}
_ADOS = {"dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16}
_DIZAINES = {"vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60}
_BELGES = {"septante": 70, "huitante": 80, "octante": 80, "nonante": 90}
_MOTS_DE_NOMBRE = frozenset({*_UNITES, *_ADOS, *_DIZAINES, *_BELGES, "vingts", "cent", "cents", "mille", "et"})
_ECRIT = re.compile(r"^([a-z]{1,2})?(\d{1,4})([a-z]|bis|ter)?$")


def _jetons(texte: str) -> list[str]:
    sans_accent = "".join(c for c in unicodedata.normalize("NFKD", (texte or "").lower().replace("°", " ")) if not unicodedata.combining(c))
    return re.findall(r"[a-z]+|\d+", sans_accent)


def _cle(prefixe: str, nombre: int, suffixe: str) -> str:
    return f"{prefixe}{nombre}{suffixe}"


def cle_ecrite(numero: str | None) -> str | None:
    """Le numéro tel que la liste l’écrit -> sa clé ; ``None`` si ce n'est pas un numéro lisible (lettres, chiffres, lettre finale)."""
    jetons = _jetons(numero or "")
    trouve = _ECRIT.match("".join(jetons))
    if not trouve:
        return None
    return _cle(trouve.group(1) or "", int(trouve.group(2)), trouve.group(3) or "")


def _groupe_99(m: list[str]) -> int | None:
    """Un nombre de 0 à 99 écrit en toutes lettres (vide : ``None``)."""
    m = [x for x in m if x != "et"]
    if not m:
        return None
    if len(m) == 1:
        x = m[0]
        return _UNITES.get(x, _ADOS.get(x, _DIZAINES.get(x, _BELGES.get(x))))
    if m[0] == "dix" and len(m) == 2 and m[1] in ("sept", "huit", "neuf"):
        return 10 + _UNITES[m[1]]
    if m[0] in _DIZAINES or m[0] in _BELGES:
        base = _DIZAINES.get(m[0]) or _BELGES[m[0]]
        reste = m[1:]
        if len(reste) == 1 and reste[0] in _UNITES and reste[0] != "zero":
            return base + _UNITES[reste[0]]
        if m[0] == "soixante":  # 70 à 79 : soixante + (dix à seize, dix sept à dix neuf)
            petit = _groupe_99(reste)
            if petit is not None and 10 <= petit <= 19:
                return 60 + petit
        return None
    if len(m) >= 2 and m[0] == "quatre" and m[1] in ("vingt", "vingts"):  # 80 à 99
        reste = m[2:]
        if not reste:
            return 80
        petit = _groupe_99(reste)
        if petit is not None and (1 <= petit <= 19):
            return 80 + petit
    return None


def _nombre(m: list[str]) -> int | None:
    """Un nombre de 0 à 9999 écrit en toutes lettres ; ``None`` si ce n'est pas un nombre bien formé."""
    if "mille" in m:
        i = m.index("mille")
        gauche = _nombre(m[:i]) if m[:i] else 1
        droite = _nombre(m[i + 1:]) if m[i + 1:] else 0
        if gauche is None or droite is None or not 1 <= gauche <= 9 or droite >= 1000:
            return None
        return gauche * 1000 + droite
    m = ["cent" if x == "cents" else x for x in m]
    if "cent" in m:
        i = m.index("cent")
        avant = m[:i]
        centaines = 1 if not avant else (_UNITES.get(avant[0]) if len(avant) == 1 and avant[0] != "zero" else None)
        reste = _groupe_99(m[i + 1:]) if m[i + 1:] else 0
        if centaines is None or reste is None:
            return None
        return centaines * 100 + reste
    return _groupe_99(m)


def _nombre_dit(m: list[str]) -> int | None:
    if not m or any(x not in _MOTS_DE_NOMBRE for x in m):
        return None
    valeur = _nombre(m)
    if valeur is not None:
        return valeur
    # Les chiffres un par un : « deux zéro un » = 201.
    if len(m) >= 2 and all(x in _UNITES for x in m):
        return int("".join(str(_UNITES[x]) for x in m))
    return None


def _lire(jetons: list[str]) -> str | None:
    """[lettres] nombre [lettre] : toute la phrase, ou rien."""
    if not jetons:
        return None
    prefixe, suffixe, milieu = "", "", list(jetons)
    if len(milieu) >= 2 and milieu[0].isalpha() and len(milieu[0]) <= 2 and milieu[0] not in _MOTS_DE_NOMBRE:
        prefixe = milieu.pop(0)
    if len(milieu) >= 2 and milieu[-1].isalpha() and milieu[-1] not in _MOTS_DE_NOMBRE and (len(milieu[-1]) == 1 or milieu[-1] in _SUFFIXES_MOTS):
        suffixe = milieu.pop()
    if len(milieu) == 1 and milieu[0].isdigit():
        nombre = int(milieu[0])
        return _cle(prefixe, nombre, suffixe) if nombre < 10000 else None
    nombre = _nombre_dit(milieu)
    return _cle(prefixe, nombre, suffixe) if nombre is not None else None


def cles_dites(texte: str | None) -> list[str]:
    """Les clés que désigne ce que le client dit, si TOUTE la phrase est un numéro ; sinon liste vide (ce n'est pas un numéro)."""
    candidats: list[list[str]] = []

    def parcourir(j: list[str]) -> None:
        # Les mots sûrs sont retirés ; les ambigus donnent deux lectures (gardé / retiré).
        if len(j) > 1 and j[0] in _AVANT_SUR:
            parcourir(j[1:])
            return
        candidats.append(j)
        if len(j) > 1 and j[0] in _AVANT_AMBIGUS:
            parcourir(j[1:])

    parcourir(_jetons(texte or ""))
    cles: list[str] = []
    for c in candidats:
        cle = _lire(c)
        if cle and cle not in cles:
            cles.append(cle)
    if not cles:
        # « deux J24 » : une quantité devant un numéro À LETTRE (sans la lettre, « deux 46 » serait ambigu). La quantité est portée par l'appelant.
        j = _jetons(texte or "")
        if len(j) >= 3 and (j[0].isdigit() or j[0] in _UNITES) and j[1].isalpha() and len(j[1]) <= 2 and j[1] not in _MOTS_DE_NOMBRE:
            cle = _lire(j[1:])
            if cle:
                cles.append(cle)
    return cles
