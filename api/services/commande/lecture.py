"""[.mark] Mécanisme commun : ce que dit l'appelant, découpé en quantités et en morceaux (lot 5, W16 : aucun article perdu).

« deux filtres et un joint 33 mm, trois vis » -> ``[(2, "filtres"), (1, "joint 33 mm"), (3, "vis")]``. Les nombres dits en
lettres sont lus par ``text_to_num`` (déjà utilisé par le fork). Un nombre suivi d'une unité (« 33 cl ») n'est jamais une quantité.
Le découpage ne décide de rien : le moteur essaie aussi le texte entier quand un morceau est introuvable (un nom qui contient « et »).
"""

from __future__ import annotations

import re
from typing import NamedTuple

QUANTITE_MAX = 20
_SEPARATEURS = re.compile(r"\s*(?:,|;|\bet\b|\bpuis\b|\bplus\b|\bainsi que\b)\s*", re.IGNORECASE)
_UNITES = r"(?:cl|centilitres?|ml|l|litres?|g|grammes?|kg|cm|euros?|€)(?![a-zà-ÿ])"
# Les petits nombres dits en lettres en tête de morceau : ``text_to_num`` laisse « deux » seul en lettres, on les lit ici.
_MOTS = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
    "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16, "vingt": 20,
}
_QUANTITE = re.compile(
    rf"^(?:(?P<n>\d{{1,2}})(?!\s*{_UNITES})\s*(?:x|fois)?\s+|(?P<mot>{'|'.join(_MOTS)})\s+)(?P<reste>.+)$", re.IGNORECASE
)


def en_chiffres(texte: str) -> str:
    """Les nombres dits en lettres passent en chiffres (« deux » -> 2, « trente-trois » -> 33) ; « un » et « une » restent."""
    try:
        from text_to_num import alpha2digit

        return alpha2digit(texte, "fr")
    except Exception:  # noqa: BLE001 -- sans la bibliothèque : le texte tel quel, jamais une panne
        return texte


class Morceau(NamedTuple):
    """Un morceau dit : sa quantité, son texte sans la quantité, et le texte tel que dit (« 4 saisons » est peut-être un NOM)."""

    quantite: int
    texte: str
    brut: str


def une_quantite(morceau: str) -> tuple[int, str]:
    """``"2 margherita"`` -> ``(2, "margherita")`` ; sans quantité : ``(1, morceau)``."""
    m = _QUANTITE.match(morceau.strip())
    if not m:
        return 1, morceau.strip()
    return (int(m["n"]) if m["n"] else _MOTS[m["mot"].casefold()]), m["reste"].strip()


def decouper(texte: str) -> list[Morceau]:
    """Les morceaux d'une phrase de commande, chacun avec sa quantité. Vide : liste vide."""
    texte = en_chiffres((texte or "").strip())
    sortie: list[Morceau] = []
    for morceau in _SEPARATEURS.split(texte):
        if morceau.strip():
            quantite, reste = une_quantite(morceau)
            if reste:
                sortie.append(Morceau(quantite, reste, morceau.strip()))
    return sortie


_MOITIES = re.compile(
    r"^(?P<debut>[^,;]*?)\bmoiti[eé]s?\b(?P<a>[^,;]*?)\s*(?:[,;]|\bet\b|\bpuis\b|\bplus\b)?\s*\bmoiti[eé]s?\b(?P<b>.+)$", re.IGNORECASE
)


class DeuxMoities(NamedTuple):
    """« un truc moitié A moitié B » : la quantité, ce qui précède (« truc »), et les deux moitiés dites."""

    quantite: int
    debut: str
    a: str
    b: str


def deux_moities(texte: str) -> DeuxMoities | None:
    """Une phrase de deux moitiés dites chacune après son marqueur (« moitié A moitié B », avec ou sans « et »). Rien de plus : « moitié-moitié A B »
    (un seul marqueur de chaque, sans séparation sûre) reste au paramètre des moitiés du modèle. ``None`` : ce n'est pas cette forme."""
    m = _MOITIES.match(en_chiffres((texte or "").strip()))
    if not m:
        return None
    a, b = (m["a"] or "").strip(" -"), (m["b"] or "").strip(" -")
    if not re.search(r"[a-zà-ÿ]", a, re.IGNORECASE) or not re.search(r"[a-zà-ÿ]", b, re.IGNORECASE):
        return None
    quantite, debut = une_quantite(m["debut"].strip())
    if debut.casefold() in _MOTS:  # « une moitié A, moitié B » : « une » est la quantité, rien ne précède
        quantite, debut = _MOTS[debut.casefold()], ""
    return DeuxMoities(quantite, debut.strip(), a, b)


def sans_quantite(texte: str) -> str:
    """Le texte entier sans sa quantité de tête (pour essayer un nom qui contient « et »)."""
    return une_quantite(en_chiffres((texte or "").strip()))[1]


def morceaux_d_options(texte: str) -> list[Morceau]:
    """Les choix dits d'un article (« sauce barbecue et double fromage ») : mêmes séparateurs, « avec » et « en supplément » en plus."""
    brut = re.sub(r"\b(?:avec|en supplément|supplément|en plus)\b", ",", en_chiffres((texte or "").strip()), flags=re.IGNORECASE)
    sortie = []
    for m in _SEPARATEURS.split(brut):
        if m.strip():
            quantite, reste = une_quantite(m)
            sortie.append(Morceau(quantite, reste, m.strip()))
    return sortie
