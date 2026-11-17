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


_MOITIE_UNIQUE = re.compile(r"^(?P<debut>.*?)\bmoiti[eé]s?[-\s]+moiti[eé]s?\b[\s:,-]*(?P<reste>.+)$", re.IGNORECASE)


def moities_apres_le_marqueur(texte: str) -> tuple[str, str] | None:
    """« <article> moitié-moitié A B » (un seul marqueur) : ce qui précède le marqueur, et les deux moitiés dites derrière. ``None`` : pas cette forme."""
    m = _MOITIE_UNIQUE.match((texte or "").strip())
    if not m or not re.search(r"[a-zà-ÿ]", m["reste"], re.IGNORECASE):
        return None
    return m["debut"].strip(), m["reste"].strip()


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


# --------------------------------------------------------------------------- #
# M117, M119 (appel 2598) : chaque article de la phrase, avec ce qui ne vaut que pour une partie (« dont une sans Y »)
# --------------------------------------------------------------------------- #


class ArticleDit(NamedTuple):
    """Un article dit : sa quantité, son texte, le texte tel que dit, et ce qui ne vaut que pour lui (un retrait, un choix)."""

    quantite: int
    texte: str
    brut: str
    sans: str | None = None
    avec: str | None = None


_DONT = re.compile(r"\s*\bdont\b\s*", re.IGNORECASE)
_PRECISION = re.compile(r"^(?P<mot>sans|avec)\b\s*(?P<quoi>.+)$", re.IGNORECASE)
_SANS_DANS_LE_NOM = re.compile(r"^(?P<nom>.*?[a-zà-ÿ].*?)\s+\bsans\b\s*(?P<quoi>.+)$", re.IGNORECASE)


def parle_de_moities(texte: str | None) -> bool:
    return bool(re.search(r"\bmoiti[eé]", texte or "", re.IGNORECASE))


def lire_les_articles(texte: str | None) -> list[ArticleDit]:
    """Les articles d'une phrase de commande, chacun traité à part (un introuvable ne fait perdre aucun autre).

    - « deux X dont une sans Y », « deux X, une sans Y », « trois X dont deux avec Z » : la précision ne vaut que pour la quantité dite, le
      reste de l'article fait sa propre ligne (jamais une moitié-moitié). Sans quantité dite, elle vaut pour tout l'article d'avant.
    - « un X sans Y » : le retrait est lu à part du nom.
    Une phrase de moitiés n'est pas lue ici (``deux_moities`` et les moitiés du modèle la tiennent)."""
    if parle_de_moities(texte):
        return [ArticleDit(q, t, b) for q, t, b in decouper(texte or "")]
    sortie: list[ArticleDit] = []
    for morceau in _SEPARATEURS.split(_DONT.sub(", dont ", en_chiffres((texte or "").strip()))):
        brut = re.sub(r"^dont\s+", "", morceau.strip(), flags=re.IGNORECASE).strip()
        if not brut:
            continue
        quantite_dite = _QUANTITE.match(brut) is not None
        quantite, reste = une_quantite(brut)
        precision = _PRECISION.match(reste)
        if precision and sortie:
            mot, quoi = precision["mot"].casefold(), precision["quoi"].strip()
            base = next((a for a in reversed(sortie) if a.sans is None and a.avec is None), sortie[-1])
            i = len(sortie) - 1 - sortie[::-1].index(base)
            precise = base._replace(sans=quoi if mot == "sans" else base.sans, avec=quoi if mot == "avec" else base.avec)
            if quantite_dite and quantite < base.quantite:
                sortie[i] = base._replace(quantite=base.quantite - quantite)
                sortie.append(precise._replace(quantite=quantite))
            else:
                sortie[i] = precise
            continue
        if not reste:
            continue
        dans_le_nom = _SANS_DANS_LE_NOM.match(reste)
        if dans_le_nom:
            sortie.append(ArticleDit(quantite, dans_le_nom["nom"].strip(), brut, sans=dans_le_nom["quoi"].strip()))
        else:
            sortie.append(ArticleDit(quantite, reste, brut))
    return sortie


def recherche_normale(texte: str | None) -> str:
    """Le texte d'un article comparé à un autre (casse, accents, pluriel) : deux morceaux du même article (« dont une sans Y »)."""
    from api.db.bases_clients.recherche_liste import normaliser

    return normaliser(texte or "")
