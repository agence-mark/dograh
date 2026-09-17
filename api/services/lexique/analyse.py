"""[.mark] Find the names of the trade vocabulary in a transcribed sentence, with a verdict.

Why this module exists
----------------------
On the 2026-09-15 and 16 benches the transcription wrote "édile camembert",
then "Edilcamin" for Edilkamin; the model repeated what it read. The names of a
trade (brands) are compared here with what was heard, before the model reads
it: a SURE reading is replaced by the official name, a doubtful one is left to
confirm (``correction.py``). Decisions L5, L6 of 2026-09-16.

The rules and thresholds are those of the 2026-09-16 trial, taken as they are
(``_AUTONOMIE/essais/2026-09-16-lexique-metier/code/lexique_espeak.py``, mode
``ESP=C``). Reference on its bench (136 brands, Windows voice at 8 kHz,
Whisper large-v3 without vocabulary): 160 sure and right, 32 right to confirm,
1 sure and wrong on 272 sentences; 0 false brand on 81 sentences without one.
⚠️ A synthetic voice: only the measure on real calls decides.

What the trial taught, and the code keeps
-----------------------------------------
- A reading may cover several words ("Edil camin"); function words never start
  or end one.
- ⛔ Common French words ("royal", "devis", "cheminée") are read as a brand
  ONLY after a strong cue ("poêle", "marque"...), and a brand made of common
  words ("Philippe", "Supra") likewise.
- Three comparisons, the best one counts: the home-made sound key (``_son_mot``),
  the ``phonetic_fr`` key, and the sounds of espeak-ng (T5, L17). 🔑 The sounds
  FIND a name; the spelling DECIDES: a name found by its sound alone is capped
  under "sure" unless its spelling scores 85 ("Easy Flamme" is never Rhea Flam
  for sure).
- A heard word sharing the start of a long name but longer ("Edilcamina") is
  capped under "sure".
- Sure needs 88 and 6 points ahead of another name; 78 is left to confirm.
- 🆕 T16 (2026-09-17): a heard passage that IS the name of a French commune
  ("Chazelles", "Deville", "Barbas") never becomes a brand: "j'habite à
  Chazelles" must stay a town. Without the list of communes, nothing is read.

🔑 Every reading of the sentence is compared in one ``rapidfuzz.process.cdist``
call per key, and the choices are made on the score matrices (numpy): the
trial's loop over every name froze the event loop up to 32 ms. Still run
``analyser`` in a worker thread (T6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Collection

import numpy as np
from rapidfuzz import fuzz, process

from api.schemas.lexique_metier import LexiqueMetier, normaliser_terme
from api.services.communes.base import cle_phonetique
from api.services.communes.sons import sons

DOSSIER = Path(__file__).resolve().parents[2] / "assets" / "lexique"
# ⛔ Named explicitly: which list a call ran on must be readable in the code.
FICHIER_MOTS_COURANTS = DOSSIER / "mots-courants-fr-2026-09.txt"

MOTS_OUTILS = frozenset(
    """a au aux c ce cet cette ces d de des du dans en et est il elle j je l la le les ma mon mes me m n ne
    nous on ou par pas pour qu que qui s sa se son sur ses t ta te tu un une vous y oui non bah ben euh hein alors voila merci
    bonjour c est ca j ai avec chez""".split()
)
# A function word that may start a name ("La Nordica", "Le Droff").
ARTICLES_DE_DEBUT = frozenset({"la", "le"})
# The words before a name that let a common word be read as one.
AMORCES_FORTES = frozenset(
    {"marque", "poele", "poeles", "poil", "insert", "foyer", "chaudiere", "cuisiniere", "modele", "chez",
     "granules", "bois", "fabricant"}
)
MOTS_AVANT = 3

SEUIL_SURE = 88
SEUIL_A_CONFIRMER = 78
MARGE_SURE = 6
# The sounds may make a name sure only when its spelling scores this much.
ORTHO_POUR_SON_SUR = 85
# Readings the sounds listen to: at most this many words, and not already well spelled.
MOTS_MAX_SONS = 4
ORTHO_SANS_SONS = 90
SEUIL_SON = 80
# Start of a long name: at least this many letters in its key, first 3 shared.
LONGUEUR_DEBUT_COMMUN = 6
POIDS_DEBUT_COMMUN = 0.9
MAX_PROPOSITIONS = 3

SURE = "sure"
A_CONFIRMER = "a_confirmer"
HOMONYME_COMMUNE = "homonyme_commune"

# A word of the ORIGINAL sentence: what ``normaliser`` separates on, plus "+" and "&".
_MOT_DORIGINE = re.compile(r"&|[^\s’'`\-_/.,;:!?()\"«»+&]+")
# espeak-ng marks a word it reads in another language: « (en)ɪn(fr)vikta ».
_DRAPEAU_DE_LANGUE = re.compile(r"\([a-z]+\)")


def _son_mot(m: str) -> str:
    """Home-made sound key of one normalised word (trial of 2026-09-16).

    ⚠️ Not ``communes.base._son_mot``: the trial's version for names ("zz" read
    "ts", "z" read "s"); the communes' key is stored in their file and cannot
    change without regenerating it.
    """
    r = re.sub(r"[^a-z]", "", m)
    if not r:
        return ""
    r = re.sub(r"(?<=[eu])x$", "", r)
    r = r.replace("sch", "ch").replace("ph", "f").replace("qu", "k").replace("ck", "k").replace("zz", "ts")
    r = r.replace("ch", "§")
    r = re.sub(r"eau|au", "o", r)
    r = re.sub(r"gu(?=[eiy])", "g", r)
    r = re.sub(r"g(?=[eiy])", "j", r)
    r = re.sub(r"c(?=[eiy])", "s", r)
    r = r.replace("c", "k").replace("w", "v").replace("x", "ks").replace("y", "i").replace("z", "s")
    r = re.sub(r"(?<![ks])h", "", r)
    r = re.sub(r"ll", "l", r)
    r = re.sub(r"gn", "ni", r)
    r = re.sub(r"(ais|ait|ay|ey|ei|ai|et|ez|er|es)$", "e", r)
    r = re.sub(r"ai|ei", "e", r)
    r = re.sub(r"(en|em|an|am)(?![aeiouy nm])", "an", r)
    r = re.sub(r"(ain|ein|in|im|un|um|yn)(?![aeiouy nm])", "in", r)
    r = re.sub(r"(on|om)(?![aeiouy nm])", "on", r)
    r = re.sub(r"(.)\1+", r"\1", r)
    r = re.sub(r"(?<=[aeiou])[stdxz]$", "", r)
    r = re.sub(r"(?<=[nr])[stdxz]$", "", r)
    r = re.sub(r"(?<=.)e$", "", r)
    return r.replace("§", "ch")


def cle_sonore(norm: str) -> str:
    return "".join(_son_mot(m) for m in norm.split())


def sons_sans_drapeaux(textes: list[str]) -> list[str] | None:
    """The espeak-ng sounds, without the language marks; None without the library."""
    prononces = sons(textes)
    if prononces is None:
        return None
    return [_DRAPEAU_DE_LANGUE.sub("", s) for s in prononces]


_mots_courants: frozenset[str] | None = None


def mots_courants() -> frozenset[str]:
    """The common words, normalised like the analysed text (T4). Read once per process."""
    global _mots_courants
    if _mots_courants is None:
        lignes = FICHIER_MOTS_COURANTS.read_text(encoding="utf-8").splitlines()
        _mots_courants = frozenset(normaliser_terme(m) for m in lignes if m and not m.startswith("#"))
    return _mots_courants


def mots_dorigine(texte: str) -> list[tuple[str, int, int]]:
    """The normalised words of a sentence, each with its span in the ORIGINAL sentence."""
    mots = []
    for trouve in _MOT_DORIGINE.finditer(texte):
        for mot in normaliser_terme(trouve.group()).split():
            mots.append((mot, trouve.start(), trouve.end()))
    return mots


@dataclass(frozen=True)
class Forme:
    terme: str
    categorie: str | None
    norm: str
    cle_sonore: str
    cle_phonetique: str
    banale: bool  # made of common words only
    homonyme_commune: bool  # the name of a French commune


@dataclass(frozen=True)
class Proposition:
    terme: str
    categorie: str | None
    score: float


@dataclass(frozen=True)
class Detection:
    entendu: str  # the words as the transcription wrote them
    debut: int  # character span in the original sentence
    fin: int
    statut: str  # SURE | A_CONFIRMER | HOMONYME_COMMUNE
    terme: str
    categorie: str | None
    score: float
    propositions: tuple[Proposition, ...]  # best first, distinct names
    par_son: bool  # the espeak-ng sounds decided the score of the name retained
    exact: bool  # heard exactly as one of the name's spellings


class Index:
    """The names of a vocabulary, their keys and sounds, ready to compare (T7)."""

    def __init__(
        self, formes: list[Forme], sons_des_formes: list[str] | None, noms_des_communes: Collection[str] | None
    ):
        self.formes = formes
        self.sons_des_formes = sons_des_formes
        # None: the list of communes could not be read, and nothing is read (T16).
        self.noms_des_communes = noms_des_communes
        self.cles_sonores = [f.cle_sonore for f in formes]
        self.cles_phonetiques = [f.cle_phonetique for f in formes]
        self.longueurs = np.array([len(k) for k in self.cles_sonores], dtype=np.int32)
        self.debuts = np.array([k[:3] for k in self.cles_sonores], dtype="<U3")
        self.debut_possible = self.longueurs >= LONGUEUR_DEBUT_COMMUN
        noms = {t: n for n, t in enumerate(dict.fromkeys(f.terme for f in formes))}
        normes = {t: n for n, t in enumerate(dict.fromkeys(f.norm for f in formes))}
        self.id_terme = np.array([noms[f.terme] for f in formes], dtype=np.int32)
        self.id_norme = np.array([normes[f.norm] for f in formes], dtype=np.int32)
        self.mots_max = (max(len(f.norm.split()) for f in formes) + 1) if formes else 0

    @property
    def vide(self) -> bool:
        return not self.formes

    @property
    def sons_disponibles(self) -> bool:
        return self.sons_des_formes is not None

    @classmethod
    def construire(
        cls,
        lexique: LexiqueMetier,
        noms_des_communes: Collection[str] | None,
        avec_sons: bool = True,
    ) -> Index:
        """Blocking (keys, and espeak-ng when ``avec_sons``): call it off the event loop.

        ``noms_des_communes``: the normalised names of the French communes
        (``BaseCommunes.par_nom``); None when the list could not be read, and
        then the index reads nothing (T16).
        """
        courants = mots_courants()
        communes = noms_des_communes if noms_des_communes is not None else ()
        formes = []
        for terme in lexique.termes:
            if terme.type != "nom":
                continue  # a trade word is only listened for, never corrected
            for ecrit in dict.fromkeys(terme.formes()):
                norm = normaliser_terme(ecrit)
                if any(f.norm == norm and f.terme == terme.terme for f in formes):
                    continue
                formes.append(
                    Forme(
                        terme=terme.terme,
                        categorie=terme.categorie,
                        norm=norm,
                        cle_sonore=cle_sonore(norm),
                        cle_phonetique=cle_phonetique(norm),
                        banale=all(m in courants for m in norm.split()),
                        homonyme_commune=norm in communes,
                    )
                )
        sons_des_formes = sons_sans_drapeaux([f.norm for f in formes]) if (avec_sons and formes) else None
        return cls(formes, sons_des_formes, noms_des_communes)


def _passages(mots: list[str], mots_max: int) -> list[tuple[int, int, str]]:
    passages = []
    for i in range(len(mots)):
        for n in range(1, mots_max + 1):
            if i + n > len(mots):
                break
            premier, dernier = mots[i], mots[i + n - 1]
            if premier in MOTS_OUTILS and premier not in ARTICLES_DE_DEBUT:
                continue
            if dernier in MOTS_OUTILS:
                continue
            passages.append((i, n, " ".join(mots[i : i + n])))
    return passages


def analyser(texte: str, index: Index, avec_sons: bool = True) -> list[Detection]:
    """The names read in ``texte``, without overlap, best first. Blocking: worker thread.

    ``avec_sons=False`` (the agent's switch, T15): spelling keys only, espeak-ng never called.
    """
    noms_des_communes = index.noms_des_communes
    if index.vide or noms_des_communes is None:
        return []
    mots_et_places = mots_dorigine(texte)
    mots = [m for m, _, _ in mots_et_places]
    passages = _passages(mots, index.mots_max)
    if not passages:
        return []
    courants = mots_courants()

    cles = [cle_sonore(p[2]) for p in passages]
    s_sonore = process.cdist(cles, index.cles_sonores, scorer=fuzz.ratio, workers=-1)
    s_phon = process.cdist(
        [cle_phonetique(p[2]) for p in passages], index.cles_phonetiques, scorer=fuzz.ratio, workers=-1
    )
    s_partiel = process.cdist(cles, index.cles_sonores, scorer=fuzz.partial_ratio, workers=-1)
    scores = np.maximum(s_sonore, s_phon).astype(np.float64)
    par_son = np.zeros(scores.shape, dtype=bool)

    if avec_sons and index.sons_disponibles:
        meilleur = scores.max(axis=1)
        a_ecouter = [j for j, p in enumerate(passages) if p[1] <= MOTS_MAX_SONS and meilleur[j] < ORTHO_SANS_SONS]
        entendus = sons_sans_drapeaux([passages[j][2] for j in a_ecouter]) if a_ecouter else None
        if entendus is not None:
            s_son = process.cdist(
                entendus, index.sons_des_formes, scorer=fuzz.ratio, score_cutoff=SEUIL_SON, workers=-1
            ).astype(np.float64)
            lignes = np.array(a_ecouter)
            ortho = scores[lignes]
            plus_haut = s_son > ortho
            retenu = np.where(ortho >= ORTHO_POUR_SON_SUR, s_son, np.minimum(s_son, SEUIL_SURE - 1))
            scores[lignes] = np.where(plus_haut, retenu, ortho)
            par_son[lignes] = plus_haut & (retenu > ortho)

    # Start of a long name, heard with syllables in excess: capped under "sure".
    longueurs = np.array([len(k) for k in cles], dtype=np.int32)
    debuts = np.array([k[:3] for k in cles], dtype="<U3")
    debut_commun = (
        index.debut_possible[None, :]
        & (debuts[:, None] == index.debuts[None, :])
        & (longueurs[:, None] > index.longueurs[None, :])
    )
    par_debut = np.where(debut_commun, np.minimum(POIDS_DEBUT_COMMUN * s_partiel, SEUIL_SURE - 1), 0.0)
    releve = par_debut > scores
    scores = np.where(releve, par_debut, scores)
    par_son &= ~releve

    candidats = []
    for j, (i, n, passage) in enumerate(passages):
        ligne = scores[j]
        meilleure = int(np.argmax(ligne))
        forme = index.formes[meilleure]
        if len(forme.cle_sonore) < 3:
            continue
        autres = (index.id_terme != index.id_terme[meilleure]) & (index.id_norme != index.id_norme[meilleure])
        score = float(ligne[meilleure])
        second = float(ligne[autres].max()) if autres.any() else None
        exact = passage == forme.norm
        avant = mots[max(0, i - MOTS_AVANT) : i]
        forte = any(m in AMORCES_FORTES for m in avant)
        banal = all(m in courants for m in passage.split())
        # ⛔ Common words become a name only after a STRONG cue.
        if (banal or forme.banale) and not forte:
            continue
        cle = cles[j]
        if len(cle) < 3:
            continue
        # Comparable length: no 3-sound name in a 12-sound reading.
        if abs(len(cle) - len(forme.cle_sonore)) > max(3, len(forme.cle_sonore) // 2):
            continue
        if exact or (score >= SEUIL_SURE and (second is None or score - second >= MARGE_SURE)):
            statut = SURE
        elif score >= SEUIL_A_CONFIRMER:
            statut = A_CONFIRMER
        else:
            continue
        if passage in noms_des_communes:
            statut = HOMONYME_COMMUNE  # T16: a town said, never rewritten
        debut, fin = mots_et_places[i][1], mots_et_places[i + n - 1][2]
        candidats.append(
            (
                statut == HOMONYME_COMMUNE,
                statut == SURE,
                score,
                n,
                i,
                Detection(
                    entendu=texte[debut:fin],
                    debut=debut,
                    fin=fin,
                    statut=statut,
                    terme=forme.terme,
                    categorie=forme.categorie,
                    score=round(score, 1),
                    propositions=_propositions(ligne, index, meilleure),
                    par_son=bool(par_son[j, meilleure]),
                    exact=exact,
                ),
            )
        )

    # The best readings that do not overlap; a commune's name claims its words first.
    candidats.sort(key=lambda c: (not c[0], not c[1], -c[2], -c[3]))
    pris: set[int] = set()
    retenues = []
    for _, _, _, n, i, detection in candidats:
        if any(k in pris for k in range(i, i + n)):
            continue
        pris.update(range(i, i + n))
        retenues.append(detection)
    return retenues


def _propositions(ligne: np.ndarray, index: Index, meilleure: int) -> tuple[Proposition, ...]:
    """The retained name, then up to two other names that could also be it."""
    forme = index.formes[meilleure]
    propositions = [Proposition(forme.terme, forme.categorie, round(float(ligne[meilleure]), 1))]
    vus = {forme.terme}
    for k in np.argsort(-ligne, kind="stable"):
        if len(propositions) >= MAX_PROPOSITIONS or ligne[k] < SEUIL_A_CONFIRMER:
            break
        autre = index.formes[int(k)]
        if autre.terme in vus:
            continue
        vus.add(autre.terme)
        propositions.append(Proposition(autre.terme, autre.categorie, round(float(ligne[k]), 1)))
    return tuple(propositions)
