"""[.mark] Finding the team's names in a text (chantier l-agent-collegue, L3, C12, C13).

The rule (C13), per name of the text compared with each name of the team:

- **sure** -- spelling score ≥ ``SEUIL_ORTHOGRAPHE`` (85) AND the same sound (the
  ``phonetic_fr`` key or our sound key), and ONE person only → ``detectee``;
- **one of the two only**, or two people possible (two « Julien ») → ``a_confirmer``. A name
  matched by its sound alone must still be written close enough (``PLANCHER_SON``, 60): two
  short words that happen to share a sound key are not a name (« Kamil » for « Camille »
  scores 67: it is kept, to be confirmed);
- otherwise nothing.

What counts as a name in the text (measured on the corpus, ``tests/mark/donnees/``):

- a full name (first name and last name, in either order) counts wherever it is, whatever
  its case; a first name of several words (« Jean-Marc », « Jean Marc ») counts when its
  first word has a capital;
- a single word counts only when it is written with a capital. A capital at the start of a
  sentence proves nothing for a common word (« Petit souci… », « Rose et blanc… »): such a
  word is ignored there. ⛔ Without these two rules, « le matin » is « Martin » to the
  spelling score (91) and the corpus without names is not clean.

The text is never changed; nothing here raises (an empty list on any problem).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from loguru import logger

SEUIL_ORTHOGRAPHE = 85.0
PLANCHER_SON = 60.0
LONGUEUR_MIN = 3
LONGUEUR_EXTRAIT = 160

_MOT = re.compile(r"[^\W\d_](?:[^\W\d_]|['’\-](?=[^\W\d_]))*", re.UNICODE)
_FIN_DE_PHRASE = re.compile(r"[.!?:\n]\s*$")


@dataclass(frozen=True)
class Reperage:
    cle: str
    certitude: str  # detectee | a_confirmer
    forme: str  # the words of the text
    extrait: str
    orthographe: float
    meme_son: bool


@dataclass
class _Jeton:
    norm: str
    majuscule: bool
    debut_de_phrase: bool
    debut: int
    fin: int


def _jetons(texte: str) -> list[_Jeton]:
    from api.services.communes.base import normaliser

    jetons: list[_Jeton] = []
    for m in _MOT.finditer(texte):
        mot = m.group(0)
        avant = texte[: m.start()]
        debut_de_phrase = not avant.strip() or bool(_FIN_DE_PHRASE.search(avant))
        # « Jean-Marc » is two words for the comparison, like the team's names.
        morceaux = normaliser(mot).split()
        for i, norm in enumerate(morceaux):
            jetons.append(
                _Jeton(
                    norm=norm,
                    majuscule=mot[:1].isupper(),
                    debut_de_phrase=debut_de_phrase and i == 0,
                    debut=m.start(),
                    fin=m.end(),
                )
            )
    return jetons


def _formes(personne) -> list[tuple[str, bool]]:
    """(normalised form, full name?) of a person: first name, last name, both orders."""
    from api.services.communes.base import normaliser

    prenom = normaliser(personne.prenom or "")
    nom = normaliser(personne.nom or "")
    formes = []
    if prenom and nom:
        formes += [(f"{prenom} {nom}", True), (f"{nom} {prenom}", True)]
    for seul in (prenom, nom):
        if len(seul.replace(" ", "")) >= LONGUEUR_MIN:
            formes.append((seul, False))
    return formes


def _meme_son(a: str, b: str) -> bool:
    from api.services.communes.base import cle_phonetique, cle_sonore

    try:
        pa, pb = cle_phonetique(a), cle_phonetique(b)
        if pa and pa == pb:
            return True
    except Exception:  # noqa: BLE001 -- phonetic_fr missing: our sound key alone
        pass
    sa, sb = cle_sonore(a), cle_sonore(b)
    return bool(sa) and sa == sb


def _orthographe(a: str, b: str) -> float:
    from rapidfuzz import fuzz

    return float(fuzz.ratio(a.replace(" ", ""), b.replace(" ", "")))


def _mot_courant(norm: str) -> bool:
    try:
        from api.services.lexique.analyse import mots_courants

        return norm in mots_courants()
    except Exception:  # noqa: BLE001 -- no list: be strict
        return True


def _extrait(texte: str, debut: int, fin: int) -> str:
    marge = max(0, (LONGUEUR_EXTRAIT - (fin - debut)) // 2)
    a, b = max(0, debut - marge), min(len(texte), fin + marge)
    morceau = " ".join(texte[a:b].split())
    return (("…" if a > 0 else "") + morceau + ("…" if b < len(texte) else ""))[:200]


def reperer(
    texte: str | None,
    personnes,
    seuil: float = SEUIL_ORTHOGRAPHE,
    plancher: float = PLANCHER_SON,
) -> list[Reperage]:
    """The people of ``personnes`` (objects with ``cle``, ``prenom``, ``nom``) the text names.
    One entry per person, the surest kept. Never raises."""
    try:
        return _reperer(texte or "", list(personnes or []), seuil, plancher)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Names of the team not searched in a text: {erreur!r}")
        return []


def _reperer(texte: str, personnes: list, seuil: float, plancher: float) -> list[Reperage]:
    jetons = _jetons(texte)
    if not jetons or not personnes:
        return []
    formes = [(p, forme, complet) for p in personnes for forme, complet in _formes(p)]
    pris: set[int] = set()
    trouves: dict[str, Reperage] = {}

    def garder(r: Reperage) -> None:
        avant = trouves.get(r.cle)
        if avant is None or (avant.certitude == "a_confirmer" and r.certitude == "detectee"):
            trouves[r.cle] = r

    def comparer(indices: list[int], candidats) -> bool:
        forme_texte = " ".join(jetons[i].norm for i in indices)
        resultats = []
        for personne, forme, _complet in candidats:
            ortho = _orthographe(forme_texte, forme)
            son = _meme_son(forme_texte, forme)
            if ortho >= seuil and son:
                resultats.append((personne, "sur", ortho, son))
            elif (ortho >= seuil) or (son and ortho >= plancher):
                resultats.append((personne, "un", ortho, son))
        if not resultats:
            return False
        cles = {r[0].cle for r in resultats}
        debut, fin = jetons[indices[0]].debut, jetons[indices[-1]].fin
        for personne, niveau, ortho, son in resultats:
            certitude = "detectee" if niveau == "sur" and len(cles) == 1 else "a_confirmer"
            garder(
                Reperage(
                    cle=personne.cle,
                    certitude=certitude,
                    forme=texte[debut:fin],
                    extrait=_extrait(texte, debut, fin),
                    orthographe=round(ortho, 1),
                    meme_son=son,
                )
            )
        pris.update(indices)
        return True

    # 1. Names of several words first: a full name whatever its case, a first name of
    #    several words when its first word has a capital.
    for taille in (4, 3, 2):
        for i in range(len(jetons) - taille + 1):
            indices = list(range(i, i + taille))
            if pris & set(indices):
                continue
            candidats = [
                f
                for f in formes
                if len(f[1].split()) == taille and (f[2] or jetons[i].majuscule)
            ]
            if candidats:
                comparer(indices, candidats)

    # 2. Single words: written with a capital, never a common word starting a sentence.
    seuls = [f for f in formes if len(f[1].split()) == 1]
    for i, jeton in enumerate(jetons):
        if i in pris or len(jeton.norm) < LONGUEUR_MIN or not jeton.majuscule:
            continue
        if jeton.debut_de_phrase and _mot_courant(jeton.norm):
            continue
        comparer([i], seuls)
    return list(trouves.values())
