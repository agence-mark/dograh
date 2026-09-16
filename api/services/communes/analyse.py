"""[.mark] Find the town a caller named in a transcribed sentence, with a verdict.

Why this module exists
----------------------
"Beauvais" was transcribed "Beauvet", then "Bovet" (2026-09-15, 2026-09-16).
A transcription error often lands on ANOTHER real town ("Bovet" sounds like
Boves, in the Somme), so a spelling check alone cannot tell; only a location
clue can: the shop's town, or a postal code the caller said.

The rules and thresholds below are those of the 2026-09-16 trial (prototype
v4, ``_AUTONOMIE/essais/2026-09-16-verification-communes/``), taken as they
are. Its reference result, shop at Saint-Maximin (60): 48 of 56 sentences
sure and right, 0 sure and wrong. ⚠️ Tuned on hand-written cases: only the
voice bench decides.

What the trial taught, and the code keeps
-----------------------------------------
- ⛔ Searching the whole sentence is unusable: 20 false "sure" towns on 64
  sentences ("avec" -> Hanvec, "deux" -> Dreux). A reading must be ANCHORED:
  right after "à", "sur", "commune"...; or the whole answer is short; or it
  sits next to a postal code.
- A name right after a street type ("rue", "allée"...) is a street, not a town.
- A reading that covers more words is preferred ("Nogent sur Oise" over
  "Nogent"), and an exact reading over several words wins over its parts.
- One-word readings under 4 letters only count when spelled like the town.
- 🔑 ``rapidfuzz.process.cdist`` compares every reading of the sentence in one
  call, which releases the Python lock: one call per reading held it and froze
  the event loop 38 ms (17 ms grouped). Still run it in a worker thread.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from api.services.communes.base import (
    BaseCommunes,
    Commune,
    cle_phonetique,
    cle_sonore,
    distance_km,
    normaliser,
)

# Words that never start or end a town name in a sentence.
MOTS_OUTILS = set(
    """a au aux c ce cet cette ces c est d de des du dans en et est il elle j je l la le les
    ma mon mes me m n ne nous on ou où par pas pour qu que qui s sa se son sur ses t ta te
    tu un une vous y oui non bah ben euh hein alors voila voilà merci bonjour
    rue avenue boulevard chemin allee allée impasse place route lieu dit residence résidence
    numero numéro code postal commune ville village habite j habite suis c est""".split()
)
# Words allowed INSIDE a compound name (Nogent-sur-Oise, Pont-Sainte-Maxence).
LIAISONS = {"sur", "sous", "les", "le", "la", "l", "de", "des", "du", "en", "et", "aux", "au", "d", "lès"}
# The word right before a town: "à Beauvais", "sur Creil", "commune de"...
AMORCES = {"a", "sur", "vers", "commune", "ville", "habite", "habitons", "habitent",
           "situe", "sis", "pres", "cote", "secteur"}
TYPES_VOIE = {"rue", "avenue", "av", "boulevard", "bd", "chemin", "allee", "impasse", "place", "route",
              "quai", "square", "residence", "lotissement", "cours", "passage", "sentier", "ruelle",
              "voie", "zac", "za", "lieu", "dit"}
ARTICLES = {"la", "le", "les", "l"}
# Words that do not make an answer longer: "oui c'est à Sanlis" is a short answer.
MOTS_VIDES_REPONSE = {"oui", "non", "alors", "euh", "ben", "bah", "c", "est", "ca", "je", "j", "suis",
                      "habite", "a", "sur", "moi", "on", "nous", "voila", "merci", "commune", "ville",
                      "de", "la", "le", "donc", "en", "fait", "bien", "sure"}

# Thresholds of the trial (prototype v4 defaults).
BONUS_MOT = 5
POIDS_POP = 1.5
POIDS_ORTHO = 0.2
N_MAX = 6
SEUIL_PHON = 72
SEUIL_DETECTION = 82
MARGE_SURE = 8
PHON_SURE = 85

SURE = "sure"
A_CONFIRMER = "a_confirmer"

_SEPARATEURS = r"[’'`\-_/.,;:!?()\"«»\s]"


@dataclass(frozen=True)
class Lecture:
    commune: Commune
    score: float
    phon: float
    ortho: float


@dataclass(frozen=True)
class Detection:
    entendu: str  # the words as the transcription wrote them
    debut: int  # word positions in the normalised sentence; -1 for a postal code alone
    fin: int
    statut: str  # SURE | A_CONFIRMER
    lectures: tuple[Lecture, ...]  # best first
    codes_postaux_dits: frozenset[str]


def _extrait_dorigine(texte: str, debut: int, fin: int, mots_normalises: list[str]) -> str:
    """The span of the ORIGINAL sentence behind normalised words [debut, fin).

    Each original token (split on the separators ``normaliser`` turns into
    spaces) gives exactly one normalised word. If that ever stops being true,
    the normalised words are returned rather than a wrong span.
    """
    jetons = [m for m in re.finditer(rf"[^{_SEPARATEURS[1:-1]}]+", texte)]
    if len(jetons) != len(mots_normalises):
        return " ".join(mots_normalises[debut:fin])
    return texte[jetons[debut].start():jetons[fin - 1].end()]


def analyser(
    texte: str,
    base: BaseCommunes,
    magasin: tuple[float, float] | None = None,
) -> list[Detection]:
    """The towns named in ``texte``, each with a verdict.

    ``magasin`` is the (longitude, latitude) of the business: towns nearby get
    a bonus, which is what separates "Bovet" -> Beauvais (60) from Boves (80).
    Blocking and CPU-bound: call it in a worker thread.
    """
    norm = normaliser(texte)
    mots = norm.split()
    cps = set(re.findall(r"\b\d{5}\b", texte))

    attente = []
    reponse_courte = sum(1 for m in mots if m not in MOTS_VIDES_REPONSE and not m.isdigit()) <= 5
    pos_cp = [k for k, m in enumerate(mots) if m in cps]
    for i in range(len(mots)):
        # A name right after a street type is a street name, not a town.
        avant = mots[max(0, i - 3):i]
        voies = [k for k, m in enumerate(avant) if m in TYPES_VOIE]
        if voies and not any(m in AMORCES for m in avant[voies[-1]:]):
            continue
        for n in range(1, N_MAX + 1):
            seg = mots[i:i + n]
            if len(seg) < n:
                break
            if (seg[0] in MOTS_OUTILS and not (n > 1 and seg[0] in ARTICLES)) or seg[-1] in MOTS_OUTILS or seg[-1] in LIAISONS:
                continue
            debut_utile = all(m in MOTS_VIDES_REPONSE for m in mots[:i])
            ancre = (
                (i > 0 and mots[i - 1] in AMORCES)
                or (reponse_courte and debut_utile)
                or any(p == i - 1 or p == i + n for p in pos_cp)
            )
            if not ancre:
                continue
            if any(m.isdigit() for m in seg) or any(m in TYPES_VOIE for m in seg):
                continue
            if any(m in MOTS_OUTILS and m not in LIAISONS for m in seg[1:-1]):
                continue
            extrait = " ".join(seg)
            if len(extrait.replace(" ", "")) < 3:
                continue
            amorce = i > 0 and mots[i - 1] in AMORCES
            k_phon, k_son = cle_phonetique(extrait), cle_sonore(extrait)
            if len(k_son) < 2:
                continue
            attente.append((i, n, extrait, amorce, k_phon, k_son))

    fenetres: list[tuple[float, int, int, list[Lecture]]] = []
    if attente:
        import numpy as np
        from rapidfuzz import fuzz, process

        m_phon = process.cdist([t[4] for t in attente], base.phons, scorer=fuzz.ratio,
                               score_cutoff=SEUIL_PHON, dtype=np.uint8, workers=-1)
        m_son = process.cdist([t[5] for t in attente], base.sons, scorer=fuzz.ratio,
                              score_cutoff=SEUIL_PHON, dtype=np.uint8, workers=-1)
        m_max = np.maximum(m_phon, m_son)
        for w, (i, n, extrait, amorce, k_phon, k_son) in enumerate(attente):
            ligne = m_max[w]
            trouves = np.nonzero(ligne)[0]
            if len(trouves) > 60:
                trouves = trouves[np.argsort(-ligne[trouves])[:60]]
            idxs: dict[int, float] = {int(j): float(ligne[j]) for j in trouves}
            # A postal code was said: the towns that carry it are compared too,
            # a partial name allowed.
            for cp in cps:
                for j in base.par_cp.get(cp, []):
                    s = max(fuzz.partial_ratio(k_son, base.sons[j]), fuzz.partial_ratio(extrait, base.norms[j]))
                    if s >= SEUIL_PHON:
                        idxs[j] = max(idxs.get(j, 0), s)
            lectures = []
            for j, s_phon in idxs.items():
                c = base.communes[j]
                s_ortho = fuzz.ratio(extrait, base.norms[j])
                score = (1 - POIDS_ORTHO) * s_phon + POIDS_ORTHO * s_ortho
                score += POIDS_POP * math.log10(max(c.population, 1))
                score += 5 if amorce else 0
                score += BONUS_MOT * (n - 1)  # a reading over more words is preferred
                if cps and set(c.cps) & cps:
                    score += 30
                if magasin:
                    score += max(0.0, 20 - distance_km(c, *magasin) / 7.5)
                lectures.append(Lecture(c, score, s_phon, s_ortho))
            if not lectures:
                continue
            # A very short word only counts when spelled like the town ("vos" is not Voh).
            if n == 1 and len(extrait) < 4:
                lectures = [l for l in lectures if l.ortho >= 90]
                if not lectures:
                    continue
            meilleures: dict[str, Lecture] = {}
            for l in sorted(lectures, key=lambda l: -l.score):
                meilleures.setdefault(l.commune.insee, l)
            lectures = list(meilleures.values())
            fenetres.append((lectures[0].score, i, i + n, lectures))

    # Readings that do not overlap, best first. An exact reading over several
    # words goes before the pieces it contains ("Clermont Ferrand" before
    # "Clermont"), whatever the pieces score.
    fenetres.sort(key=lambda f: -f[0])
    exactes = [f for f in fenetres if f[2] - f[1] > 1 and f[3][0].phon >= 90]
    exactes.sort(key=lambda f: (-(f[2] - f[1]), -f[0]))
    fenetres = exactes + [f for f in fenetres if f not in exactes]
    prises: list[Detection] = []
    for score, d, f, lectures in fenetres:
        # Threshold expressed for a town of 1,000 inhabitants.
        if score < SEUIL_DETECTION + POIDS_POP * math.log10(1000):
            continue
        if any(not (f <= p.debut or d >= p.fin) for p in prises):
            continue
        top = lectures[0]
        second = lectures[1].score if len(lectures) > 1 else -1e9
        sure = top.phon >= PHON_SURE and top.score - second >= MARGE_SURE
        prises.append(Detection(
            entendu=_extrait_dorigine(texte, d, f, mots),
            debut=d,
            fin=f,
            statut=SURE if sure else A_CONFIRMER,
            lectures=tuple(lectures[:3]),
            codes_postaux_dits=frozenset(cps),
        ))

    # A postal code said on its own.
    if cps and not prises:
        for cp in sorted(cps):
            communes = base.communes_du_code_postal(cp)
            if communes:
                ls = tuple(Lecture(c, 0, 0, 0) for c in communes)
                prises.append(Detection(
                    entendu=cp,
                    debut=-1,
                    fin=-1,
                    statut=SURE if len(ls) == 1 else A_CONFIRMER,
                    lectures=ls[:5],
                    codes_postaux_dits=frozenset(cps),
                ))
    return prises
