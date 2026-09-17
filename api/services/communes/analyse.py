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
from typing import Mapping, Sequence

from api.services.communes.base import (
    BaseCommunes,
    Commune,
    cle_phonetique,
    cle_sonore,
    distance_km,
    normaliser,
)
from api.services.communes.sons import sons
from api.services.nombres.mots import MOTS_NOMBRE

# Words that never start or end a town name in a sentence.
MOTS_OUTILS = set(
    """a au aux c ce cet cette ces c est d de des du dans en et est il elle j je l la le les
    ma mon mes me m n ne nous on ou où par pas pour qu que qui s sa se son sur ses t ta te
    tu un une vous y oui ouais non bah ben euh hein hum alors voila voilà merci bonjour tres très bien etre être
    rue avenue boulevard chemin allee allée impasse place route lieu dit residence résidence
    numero numéro code postal commune ville village habite j habite suis c est""".split()
)
# N6 (plan nombres-dictes): billing words never start or end a town, and do not
# make an answer longer. "le devis faisait 15000 euros" gave Devise (80) sure,
# "c'est la commande 60300" gave Lacommande (64) sure.
MOTS_FACTURATION = frozenset(
    """devis facture commande euro euros centime centimes numero reference dossier
    montant acompte total prix ttc ht tiret""".split()
)
MOTS_OUTILS |= MOTS_FACTURATION
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
# N6: billing words and number words do not COUNT in the length of an answer
# ("Senlis soixante trois cents" is a short answer). ⛔ Counting only: they do
# not open an answer either, or "La facture de juillet" reads Juilly as sure
# (measured on the lab sentences, 2026-09-16).
MOTS_HORS_COMPTE = MOTS_VIDES_REPONSE | MOTS_FACTURATION | MOTS_NOMBRE

# Thresholds of the trial (prototype v4 defaults).
BONUS_MOT = 5
POIDS_POP = 1.5
POIDS_ORTHO = 0.2
N_MAX = 6
SEUIL_PHON = 72
SEUIL_DETECTION = 82
MARGE_SURE = 8
PHON_SURE = 85
# Among several readings of a postal code, only a name heard this closely is backed by one.
PHON_EXACT = 90
# First words too common to name a town on their own.
PREFIXES_GENERIQUES = frozenset({"saint", "sainte", "le", "la", "les", "l", "pont", "mont", "val", "villers", "ville"})
# A town of a department the caller said ("dans l'Oise").
BONUS_DEPARTEMENT = 15
# V5 (plan voix-et-communes), measured by sweep on 2026-09-17: the pronounced
# sounds count from SEUIL_ESP, lowered by DECALAGE_ESP before joining the
# spelling scores. POIDS_ESP = 0 turns them off.
POIDS_ESP = 1
SEUIL_ESP = 80
DECALAGE_ESP = 0

SURE = "sure"
A_CONFIRMER = "a_confirmer"

_SEPARATEURS = r"[’'`\-_/.,;:!?()\"«»\s]"


@dataclass(frozen=True)
class Lecture:
    commune: Commune
    score: float
    phon: float
    ortho: float
    # With the number reader: the name's own resemblance (without the partial
    # match a postal code allows), and whether a postal code backed this reading.
    phon_nom: float | None = None
    par_code: bool = False

    @property
    def nom_exact(self) -> bool:
        """Heard almost exactly: decision of Evan, 2026-09-16, the only way a
        postal code may make a town sure when the code has several towns."""
        return (self.phon if self.phon_nom is None else self.phon_nom) >= PHON_EXACT


@dataclass(frozen=True)
class Detection:
    entendu: str  # the words as the transcription wrote them
    debut: int  # word positions in the normalised sentence; -1 for a postal code alone
    fin: int
    statut: str  # SURE | A_CONFIRMER
    lectures: tuple[Lecture, ...]  # best first
    codes_postaux_dits: frozenset[str]
    # The words heard are a postal code, not a name: the note then asks for the
    # town only (asking for "the town or its postal code" gets the same code again).
    code_postal_entendu: bool = False


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


def _joints(texte: str, mots: list[str]) -> set[int]:
    """Positions k whose word is glued to word k + 1 by a hyphen or an apostrophe
    in the ORIGINAL sentence ("Saint-Le-Destran", "l'Isle")."""
    jetons = [m for m in re.finditer(rf"[^{_SEPARATEURS[1:-1]}]+", texte)]
    if len(jetons) != len(mots):
        return set()
    return {
        k for k in range(len(jetons) - 1)
        if re.search(r"[-’'`]", texte[jetons[k].end():jetons[k + 1].start()])
    }


def _segments(texte: str, mots: list[str], spans_cp, mots_cp: set[int], avec_lecteur: bool):
    """The readings of a sentence a town may hide in: (start, length, words, after an amorce)."""
    joints = _joints(texte, mots)
    reponse_courte = sum(1 for m in mots if m not in MOTS_HORS_COMPTE and not m.isdigit()) <= 5
    for i in range(len(mots)):
        # A name right after a street type is a street name, not a town.
        avant = mots[max(0, i - 3):i]
        voies = [k for k, m in enumerate(avant) if m in TYPES_VOIE]
        if voies and not any(m in AMORCES for m in avant[voies[-1]:]):
            continue
        # T8 (plan voix-et-communes): the rest of a name that opens on a generic
        # prefix is not a town of its own. "Saint-Le-Destran" read "Le-Destran"
        # as Lestrem (62), sure (run 265). An article counts only when glued.
        if i > 0 and mots[i - 1] in PREFIXES_GENERIQUES and (
            mots[i - 1] not in ARTICLES or (i - 1) in joints
        ):
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
                or any(f == i or d == i + n for d, f in spans_cp)
            )
            if not ancre:
                continue
            if any(m.isdigit() for m in seg) or any(m in TYPES_VOIE for m in seg):
                continue
            if any(k in mots_cp for k in range(i, i + n)):
                continue
            # With the reader, words that are only a number are never a town
            # ("c'est deux mille" read Dreux as sure). Names that carry a number
            # word among others stay searchable (Six-Fours-les-Plages).
            if avec_lecteur and all(m in MOTS_NOMBRE or m == "et" for m in seg):
                continue
            # A tool word inside a name only when glued on both sides: "monte-à-terre"
            # is one written name (Montataire, run 264), "Beauvais à côté" is not.
            if any(
                m in MOTS_OUTILS and m not in LIAISONS and not (k - 1 in joints and k in joints)
                for k, m in enumerate(seg[1:-1], start=i + 1)
            ):
                continue
            extrait = " ".join(seg)
            if len(extrait.replace(" ", "")) < 3:
                continue
            yield i, n, extrait, i > 0 and mots[i - 1] in AMORCES


def analyser(
    texte: str,
    base: BaseCommunes,
    magasin: tuple[float, float] | None = None,
    codes_postaux: Mapping[str, Sequence[tuple[int, int]]] | None = None,
    departements: set[str] | frozenset[str] | None = None,
    mots_nombres: set[int] | frozenset[int] | None = None,
) -> list[Detection]:
    """The towns named in ``texte``, each with a verdict.

    ``magasin`` is the (longitude, latitude) of the business: towns nearby get
    a bonus, which is what separates "Bovet" -> Beauvais (60) from Boves (80).
    Blocking and CPU-bound: call it in a worker thread.

    ``codes_postaux`` (plan nombres-dictes, T6): the postal codes the number
    reader found, EVERY existing reading, each with the word spans [debut, fin)
    that say it. Given, it replaces the search for five digits, its words are
    never part of a town, and a postal code said alone is left to the caller
    (``nombres.lecture.analyser_message``), which chooses between readings.
    ``departements``: codes of the departments said; their towns get a bonus.
    ``mots_nombres``: word positions of the numbers the reader classified
    (phone, amount, reference, department): never part of a town. Without it,
    a phone dictated in words at the address step proposed "zéro six" as
    Clairoix (lot 3 of the plan, 2026-09-16).
    Without these arguments, postal codes are found as on 2026-09-16.
    """
    norm = normaliser(texte)
    mots = norm.split()
    if codes_postaux is None:
        cps = set(re.findall(r"\b\d{5}\b", texte))
        spans_cp = [(k, k + 1) for k, m in enumerate(mots) if m in cps]
        mots_cp: set[int] = set()
    else:
        cps = set(codes_postaux)
        spans_cp = sorted({s for spans in codes_postaux.values() for s in spans})
        mots_cp = {k for d, f in spans_cp for k in range(d, f)}
    mots_cp |= set(mots_nombres or ())
    # Decision of Evan, 2026-09-16: the towns of a code are added as candidates
    # (partial match) only when that code is the SINGLE reading of its number.
    # "donc soixante cinq cents" made Ourdon (65100) sure from the word "donc".
    if codes_postaux is None:
        cps_candidates = cps
    else:
        lectures_par_span: dict[tuple[int, int], set[str]] = {}
        for cp, spans in codes_postaux.items():
            for s in spans:
                lectures_par_span.setdefault(tuple(s), set()).add(cp)
        cps_candidates = {
            cp for cp, spans in codes_postaux.items()
            if all(len(lectures_par_span[tuple(s)]) == 1 for s in spans)
        }

    attente = [
        (i, n, extrait, amorce, cle_phonetique(extrait), cle_sonore(extrait))
        for i, n, extrait, amorce in _segments(texte, mots, spans_cp, mots_cp, codes_postaux is not None)
    ]
    attente = [a for a in attente if len(a[5]) >= 2]

    fenetres: list[tuple[float, int, int, list[Lecture]]] = []
    if attente:
        import numpy as np
        from rapidfuzz import fuzz, process

        m_phon = process.cdist([t[4] for t in attente], base.phons, scorer=fuzz.ratio,
                               score_cutoff=SEUIL_PHON, dtype=np.uint8, workers=-1)
        m_son = process.cdist([t[5] for t in attente], base.sons, scorer=fuzz.ratio,
                              score_cutoff=SEUIL_PHON, dtype=np.uint8, workers=-1)
        m_max = np.maximum(m_phon, m_son)
        # V5 (plan voix-et-communes): the pronounced sounds, in one call for the
        # whole sentence, scored on their own threshold and combined by the
        # maximum, so a town already recognised is never lost.
        sons_entendus = sons([t[2] for t in attente]) if base.esps and POIDS_ESP else None
        if sons_entendus is not None:
            m_esp = process.cdist(sons_entendus, base.esps, scorer=fuzz.ratio,
                                  score_cutoff=SEUIL_ESP, dtype=np.uint8, workers=-1)
            m_esp = np.where(m_esp > 0, np.clip(m_esp.astype(np.int16) - DECALAGE_ESP, 0, 100), 0).astype(np.uint8)
            m_max = np.maximum(m_max, m_esp)
        for w, (i, n, extrait, amorce, k_phon, k_son) in enumerate(attente):
            ligne = m_max[w]
            trouves = np.nonzero(ligne)[0]
            if len(trouves) > 60:
                trouves = trouves[np.argsort(-ligne[trouves])[:60]]
            idxs: dict[int, float] = {int(j): float(ligne[j]) for j in trouves}
            noms = dict(idxs)
            # A postal code was said: the towns that carry it are compared too,
            # a partial name allowed.
            for cp in cps_candidates:
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
                # A code backs a town when it is the single reading of its number,
                # or, among several readings, when the name is heard almost exactly:
                # "très bien soixante deux cent cinquante" made Beugin (62150) sure
                # from the word "bien"; "Beauchamps quatre vingt sept cent soixante
                # dix" must still find Beauchamps (80) and not Beauchamp (95).
                s_nom = noms.get(j, 0.0)
                # The first words of the name, said exactly, are the name heard:
                # "Beaumont 95260" is Beaumont-sur-Oise. Not a bare "saint".
                if extrait not in PREFIXES_GENERIQUES and base.norms[j].startswith(extrait + " "):
                    s_nom = 100.0
                par_code = j not in noms or noms[j] < s_phon
                if set(c.cps) & cps_candidates or (set(c.cps) & cps and s_nom >= PHON_EXACT):
                    score += 30
                    par_code = True
                if magasin:
                    score += max(0.0, 20 - distance_km(c, *magasin) / 7.5)
                if departements and c.dep in departements:
                    score += BONUS_DEPARTEMENT
                lectures.append(Lecture(c, score, s_phon, s_ortho, s_nom, par_code))
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
        # Decision of Evan, 2026-09-16: backed by a postal code, a town is sure
        # only when its name was heard almost exactly ("donc soixante mille cent
        # douze" made Maisoncelle-Saint-Pierre sure from the word "donc").
        if sure and codes_postaux is not None and top.par_code and not top.nom_exact:
            sure = False
        prises.append(Detection(
            entendu=_extrait_dorigine(texte, d, f, mots),
            debut=d,
            fin=f,
            statut=SURE if sure else A_CONFIRMER,
            lectures=tuple(lectures[:3]),
            codes_postaux_dits=frozenset(cps),
        ))

    # A postal code said on its own (with the reader, its caller chooses).
    if cps and not prises and codes_postaux is None:
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


# --------------------------------------------------------------------------- #
# V4 (plan voix-et-communes): the town among the communes of a postal code said
# --------------------------------------------------------------------------- #

# Measured by sweep on 2026-09-17 (see the plan's journal): the best commune of
# the code must reach SEUIL_CODE and lead the next one by ECART_CODE. A code
# remembered from an earlier turn asks more: the caller may be naming another
# place by then.
SEUIL_CODE = 60
ECART_CODE = 20
SEUIL_CODE_TRACE = 60
ECART_CODE_TRACE = 20
# Conversation words that never name a town next to a postal code: the words a
# caller says before one ("d'accord soixante mille"), from the sweep of
# 2026-09-16 (``test_balayages_nombres_dictes.AMORCES``).
MOTS_CONVERSATION = frozenset(
    """accord exactement attendez ecoutez normalement crois pense bon hum ouais bah ben donc
    merci beaucoup moi mon ma code postal voila oui non alors euh bien tres sure doit peut faut""".split()
)


def _reponse_entiere(mots: list[str], exclus: set[int]) -> tuple[int, int] | None:
    """The whole answer, conversation words and numbers removed at both ends:
    "c'est un monte-à-terre" -> "monte a terre" (run 264)."""
    utiles = [
        k for k, m in enumerate(mots)
        if k not in exclus and m not in MOTS_CONVERSATION and m not in MOTS_VIDES_REPONSE
        and m not in ("un", "une", "au", "chez", "est", "c")
    ]
    if not utiles:
        return None
    d, f = utiles[0], utiles[-1] + 1
    seg = mots[d:f]
    if f - d > N_MAX or any(k in exclus for k in range(d, f)) or any(m.isdigit() for m in seg):
        return None
    if seg[0] in TYPES_VOIE or len("".join(seg)) < 3:
        return None
    # Grammar words alone are no name: "il y a soixante mille" read Tillé as
    # sure, "je crois que c'est …" Cuts (sweep of 2026-09-16, amorces).
    if all(m in MOTS_OUTILS or m in MOTS_CONVERSATION for m in seg):
        return None
    return d, f


def ville_par_code(
    texte: str,
    base: BaseCommunes,
    codes: set[str] | frozenset[str],
    mots_exclus: set[int] | frozenset[int] = frozenset(),
    seuil: float = SEUIL_CODE,
    ecart: float = ECART_CODE,
    spans_codes: Sequence[tuple[int, int]] = (),
) -> Detection | None:
    """The town named in ``texte`` among the communes of ``codes``, when one is
    NETTEMENT DEVANT the others; None otherwise.

    Decision of Evan, 2026-09-17 (V4): a postal code said makes the town sure
    when its name is the closest among the communes of that code, clearly ahead.
    "Bouvé" said with 60000 is Beauvais: among the eight communes of 60000,
    nothing else comes close. Relaxes the rule of 2026-09-16 (a name heard almost
    exactly) for this case only.

    ``codes``: every existing reading of the postal code said ("soixante sept
    cent quarante" is 60740 or 67140: the town decides between them).
    ``mots_exclus``: word positions of the numbers read; ``spans_codes``: the
    words [debut, fin) of the postal codes, a name next to them is anchored.
    Blocking: worker thread.
    """
    from rapidfuzz import fuzz

    indices = sorted({j for cp in codes for j in base.par_cp.get(cp, [])})
    if not indices:
        return None
    mots = normaliser(texte).split()
    exclus = set(mots_exclus)
    candidats: dict[tuple[int, int], str] = {}
    for i, n, extrait, _amorce in _segments(texte, mots, list(spans_codes), exclus, True):
        if all(m in MOTS_CONVERSATION or m in MOTS_OUTILS for m in mots[i:i + n]):
            continue
        candidats[(i, i + n)] = extrait
    entiere = _reponse_entiere(mots, exclus)
    if entiere is not None:
        candidats.setdefault(entiere, " ".join(mots[entiere[0]:entiere[1]]))
    if not candidats:
        return None
    spans = list(candidats)
    extraits = [candidats[s] for s in spans]
    phons = [cle_phonetique(e) for e in extraits]
    sons_cles = [cle_sonore(e) for e in extraits]
    prononces = sons(extraits) if base.esps else None

    meilleurs: dict[int, tuple[float, tuple[int, int]]] = {}
    for w, span in enumerate(spans):
        for j in indices:
            s = max(
                fuzz.ratio(sons_cles[w], base.sons[j]),
                fuzz.ratio(phons[w], base.phons[j]),
                fuzz.ratio(extraits[w], base.norms[j]),
                fuzz.ratio(prononces[w], base.esps[j]) if prononces is not None and base.esps[j] else 0.0,
            )
            if s > meilleurs.get(j, (-1.0,))[0]:
                meilleurs[j] = (s, span)
    classes = sorted(meilleurs.items(), key=lambda x: (-x[1][0], -base.communes[x[0]].population))
    (j, (score, (debut, fin))), *autres = classes
    second = autres[0][1][0] if autres else 0.0
    if score < seuil or score - second < ecart:
        return None
    commune = base.communes[j]
    lectures = [Lecture(commune, score, score, score, score, True)]
    lectures += [Lecture(base.communes[k], s, s, s, s, True) for k, (s, _) in autres[:2]]
    return Detection(
        entendu=_extrait_dorigine(texte, debut, fin, mots),
        debut=debut,
        fin=fin,
        statut=SURE,
        lectures=tuple(lectures),
        codes_postaux_dits=frozenset(set(codes) & set(commune.cps)),
    )
