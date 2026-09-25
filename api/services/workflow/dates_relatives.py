"""[.mark] Les dates relatives dites par l'appelant (décision D46, 24/09/2026).

« Il a eu lieu l'année dernière » : le modèle note 2025, le contrôle de citation
le refusait (D38), et l'agent passait quatre tours à faire dire l'année (run 837).
La bibliothèque `dateparser` calcule la date à partir des mots de la personne, au
jour de l'appel ; la fiche garde la date calculée ET les mots dits.

⚠️ Sa RECHERCHE dans une phrase est inutilisable ici (essayée le 24/09) : « zéro
six douze » y devient le 12 juin, « il a deux ans » (l'âge de l'appareil) une date,
« je » une date, et elle ne trouve pas « le mois dernier ». Les expressions sont
donc repérées ici, dans une liste fermée de tournures relatives ; `dateparser` ne
fait que le calcul, sur l'expression seule.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import dateparser

FUSEAU = ZoneInfo("Europe/Paris")
LANGUES = ["fr"]

_NOMBRE = r"(\d+|un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze)"
_UNITE = r"(ans|an|mois|semaines|semaine|jours|jour)"

# Les tournures retenues, repérées sur le texte sans accents, et l'expression
# que `dateparser` calcule pour chacune (toutes essayées le 24/09).
_TOURNURES: list[tuple[re.Pattern[str], Callable[[re.Match[str]], str]]] = [
    (
        re.compile(r"\bl'(annee|an) (derniere|dernier|passee|passe)\b"),
        lambda m: "l'année dernière",
    ),
    (re.compile(r"\ble mois (dernier|passe)\b"), lambda m: "le mois dernier"),
    (
        re.compile(r"\bla semaine (derniere|passee)\b"),
        lambda m: "la semaine dernière",
    ),
    (
        re.compile(rf"\b(il y a|ca fait|cela fait) {_NOMBRE} {_UNITE}\b"),
        lambda m: f"il y a {m[2]} {m[3]}",
    ),
    (re.compile(r"\bavant-hier\b"), lambda m: "avant-hier"),
    (re.compile(r"(?<!avant-)\bhier\b"), lambda m: "hier"),
    (re.compile(r"\bcette annee\b"), lambda m: "cette année"),
]
_ANNEE = re.compile(r"^(19|20)\d{2}$")
_MOIS_ANNEE = re.compile(r"^(0?[1-9]|1[0-2])/(19|20)\d{2}$")
_JOUR = re.compile(r"^\d{1,2}/\d{1,2}/(19|20)\d{2}$")


def _simple(texte: str) -> str:
    """Minuscules, sans accents, apostrophes droites, caractère pour caractère :
    une position dans le texte simplifié est la même dans le texte dit."""
    return "".join(
        unicodedata.normalize("NFD", c)[0] for c in texte.lower().replace("’", "'")
    )


def aujourd_hui() -> datetime:
    """Le jour de l'appel, à l'heure française, sans fuseau (`dateparser`)."""
    return datetime.now(FUSEAU).replace(tzinfo=None)


@dataclass(frozen=True)
class DateDite:
    valeur: str  # la date calculée : « 2025 », « 08/2026 » ou « 23/09/2026 »
    dit: str  # les mots de la personne
    depuis_les_paroles: bool  # trouvée dans ce qu'elle a dit, pas dans la valeur


def _format(expression: str, date: datetime) -> str:
    """La précision de ce qui a été dit : l'année, le mois ou le jour."""
    simple = _simple(expression)
    if re.search(r"\b(an|ans|annee)\b", simple):
        return f"{date.year}"
    if "mois" in simple:
        return f"{date.month:02d}/{date.year}"
    return f"{date.day:02d}/{date.month:02d}/{date.year}"


def lire_expression(texte: str, jour: datetime) -> tuple[str, str] | None:
    """La première date relative du texte : (mots dits, date calculée)."""
    simple = _simple(texte)
    trouvees = sorted(
        (m.start(), m.end(), calcul(m))
        for motif, calcul in _TOURNURES
        for m in motif.finditer(simple)
    )
    for debut, fin, expression in trouvees:
        date = dateparser.parse(
            expression,
            languages=LANGUES,
            settings={"RELATIVE_BASE": jour, "PREFER_DATES_FROM": "past"},
        )
        if date is not None:
            return texte[debut:fin], _format(expression, date)
    return None


def _meme_date(valeur: str, calculee: str) -> bool:
    """La valeur du modèle dit-elle la même chose que la date calculée ?"""
    if valeur == calculee:
        return True
    # Une année seule vaut pour toute date de cette année : « 2025 » pour
    # « l'année dernière », oui ; pour « le mois dernier » en septembre 2026, non.
    return bool(_ANNEE.match(valeur)) and calculee.endswith(valeur)


_MOIS = (
    "janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre"
    "|decembre"
)
# Une année ou un mois nommé, où qu'ils soient : « 2024 », « fin 2023 »,
# « mars 2024 », « le 12 mars ». Large exprès : ne refuser que ce qui n'a rien
# d'une date.
_TRACE_DE_DATE = re.compile(rf"\b((19|20)\d{{2}}|{_MOIS})\b")


def est_une_date(valeur: str, jour: datetime | None = None) -> bool:
    """C8 (PB11, run 852) : une date écrite, ou une date relative reconnue ?
    « annuel », écrit par le balayage dans `dernier_entretien`, n'en est pas une."""
    valeur = str(valeur).strip()
    if _ANNEE.match(valeur) or _MOIS_ANNEE.match(valeur) or _JOUR.match(valeur):
        return True
    if _TRACE_DE_DATE.search(_simple(valeur)):
        return True
    return lire_expression(valeur, jour or aujourd_hui()) is not None


def lire_date(
    valeur: str, paroles: list[str], jour: datetime | None = None
) -> DateDite | None:
    """Deux cas, et seulement deux :

    1. la valeur EST une date relative (« l'année dernière », ou la phrase du
       balayage « il a eu lieu l'année dernière ») : on la calcule ;
    2. la valeur est une date écrite (« 2025 ») que la personne n'a pas dite
       telle quelle : on la cherche dans ses paroles, de la plus récente à la
       plus ancienne, et on ne la retient que si les deux disent la même chose.
    """
    jour = jour or aujourd_hui()
    valeur = str(valeur).strip()
    trouve = lire_expression(valeur, jour)
    if trouve:
        return DateDite(valeur=trouve[1], dit=valeur, depuis_les_paroles=False)
    if not (_ANNEE.match(valeur) or _MOIS_ANNEE.match(valeur) or _JOUR.match(valeur)):
        return None
    for parole in reversed(paroles):
        trouve = lire_expression(parole, jour)
        if trouve and _meme_date(valeur, trouve[1]):
            # Le verbatim : la phrase de la personne, telle que dite.
            return DateDite(valeur=trouve[1], dit=parole, depuis_les_paroles=True)
    return None
