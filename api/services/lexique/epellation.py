"""[.mark] A spelled sequence that IS a name of the vocabulary: a brand, never a person's name.

Why this module exists
----------------------
Run 803 (2026-09-24): the caller said « c'est un M C Z »; the spelling reader
read « Mcz », and the record's ``nom`` went from « Caron » to « Mcz ». The
letters were the caller's brand, spelled because brands are spelled (question
216 of the labo). Decision of Evan, 2026-09-26 (plan « le lexique », Q6): a
spelled sequence equal, or very close, to a term of the vocabulary is that
term -- never a name.

« Very close » (``SEUIL_PROCHE``) covers a letter heard wrong or doubled
(« P A L A Z E T T I » for Palazzetti); below ``LONGUEUR_MIN_PROCHE`` letters
only an exact match counts, since two short sequences are close by chance.

⚠️ Known consequence, accepted with Q6: a person whose name IS a term of the
vocabulary (a Mrs Godin, when Godin is a brand) and who spells it is not
written in the name field; the agent asks again or keeps the name heard.
"""

from __future__ import annotations

from rapidfuzz import fuzz

from api.schemas.lexique_metier import normaliser_terme

SEUIL_PROCHE = 90
LONGUEUR_MIN_PROCHE = 5


def _compacte(texte: str) -> str:
    return normaliser_terme(texte).replace(" ", "")


def terme_epele(epele: str | None, termes: dict[str, str] | None) -> str | None:
    """The term of the vocabulary these letters spell, or None.

    ``termes``: every spelling of every term, normalised (``normaliser_terme``)
    -> the official spelling -- what the record already holds
    (``ReglagesFiche.termes_du_lexique``).
    """
    if not epele or not termes:
        return None
    lettres = _compacte(epele)
    if not lettres:
        return None
    meilleur, score_meilleur = None, 0.0
    for forme, terme in termes.items():
        compacte = forme.replace(" ", "")
        if compacte == lettres:
            return terme
        if min(len(compacte), len(lettres)) < LONGUEUR_MIN_PROCHE:
            continue
        score = fuzz.ratio(compacte, lettres)
        if score >= SEUIL_PROCHE and score > score_meilleur:
            meilleur, score_meilleur = terme, score
    return meilleur


def formes_des_termes(lexique) -> dict[str, str]:
    """Every spelling of every term, normalised -> the official spelling. Never raises."""
    formes: dict[str, str] = {}
    try:
        for terme in getattr(lexique, "termes", None) or []:
            for forme in (terme.terme, *(terme.variantes or [])):
                if forme and (cle := normaliser_terme(forme)):
                    formes.setdefault(cle, terme.terme)
    except Exception:  # noqa: BLE001 -- the vocabulary never costs a call
        return {}
    return formes
