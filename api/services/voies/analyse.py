"""[.mark] Find the street a caller named, among the streets of THEIR commune.

Why the rules below are what they are — each was bought by a measured failure
on the corpora of 2026-09-22 (75 real sentences from the runs, 63 invented
streets, 300 real streets spoken at 8 kHz and transcribed).

The rule that outranks all the others
-------------------------------------
🔴 **Zero wrong "sure".** Saying "use this name" for a street the caller did
not say puts a wrong address in the record, and the agent repeats it without
hesitating. Everything else — coverage, how often the street is found first
try — comes after.

What the corpora taught
-----------------------
- ⛔ Compare the name WITHOUT its type: "rue de la République" is an avenue in
  Beauvais, and a caller never gets the type right.
- ⛔ A window that leaves words out is penalised (``PENALITE_MOT``). Without it,
  "allée des Mésanges Dorées" (which does not exist) came out SURE as "Rue des
  Mésanges": the single word "mésanges" matches it at 100. 15 wrong sures on
  156 cases came from this alone.
- ⛔ Plurals are types too ("79 **rues** de la mairie"): the transcription's most
  frequent slip, and without it nothing anchors.
- A street whose name is only a type keeps its whole name: "Grande Rue" is a
  name, not a type followed by a name.
- The commune and the postal code are removed from the compared passage:
  "rue des Tilleuls à Beauvais" was compared as "tilleuls a beauvais".
- 🔑 ``rapidfuzz.process.cdist`` compares every window in one call, which
  releases the Python lock — same reason as the town check. Still off the loop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
from api.services.communes.base import cle_phonetique, cle_sonore, normaliser
from api.services.communes.sons import simplifier, sons
from api.services.voies.base import VoiesCommune
from rapidfuzz import fuzz, process

SURE = "sure"
A_CONFIRMER = "a_confirmer"
INTROUVABLE = "introuvable"

# --- Thresholds, set on the corpora (`regler_voies.py` of the trial) -------
# A street is SURE above this score AND if it leads the next one by ÉCART.
# ⛔ Both conditions count: "rue de Senlis" looks like fifteen streets in a big
# commune, and picking one of them at random is exactly the failure to avoid.
# Chosen on the sweep of 2026-09-22: the whole plateau seuil >= 90 and
# ecart >= 6 holds zero wrong sures on both corpora, and this corner keeps the
# most "sure" verdicts (fewest questions asked of the caller). ⛔ 94/3 scored
# slightly better but sits on a cliff — 94/0 brings three wrong sures back.
SEUIL_SURE = 90.0
ECART_SURE = 6.0
# Below this, nothing is proposed at all: introuvable.
SEUIL_PROPOSITION = 72.0
# A street type said right is worth this much.
BONUS_TYPE = 3.0
# What each word left out by a window costs.
PENALITE_MOT = 15.0
# At most this many proposals in a note, like the town check.
PROPOSITIONS_MAXIMUM = 3

# 🔑 ONE list, shared with the generation script
# (``api/scripts/mark/generer_base_voies.py`` imports ``sans_type`` from here).
# Two diverging lists cost us a wrong sure in silence: "cour" was missing from
# the script's list, so "Cour d'Alger" kept its type in its key while "Rue
# d'Alger" did not, and the wrong one was announced sure.
TYPES = frozenset(
    ["rue", "ruelle", "avenue", "av", "boulevard", "bd", "chemin", "allee", "impasse", "place", "placette", "route", "quai", "square", "residence", "lotissement", "cours", "cour", "passage", "sentier", "sente", "venelle", "voie", "hameau", "lieu", "dit", "chaussee", "cite", "clos", "mail", "parvis", "promenade", "rond", "point", "faubourg", "fg", "montee", "cote", "descente", "esplanade", "traverse", "villa", "domaine", "parc", "ferme", "berge", "digue", "liaison", "rampe", "terrasse", "porte", "pont", "carrefour", "giratoire", "batiment", "grande", "grand", "petite", "petit", "vieille", "vieux", "ancienne", "ancien"]
)
ARTICLES = frozenset(["de", "du", "des", "la", "le", "les", "l", "d"])
# Words of a caller's answer that never belong to a street name.
MOTS_OUTILS = frozenset(
    ["j", "habite", "c", "est", "au", "a", "oui", "euh", "alors", "donc", "le", "numero", "moi", "je", "suis", "bah", "ben", "voila", "merci", "l", "adresse", "mon", "ma", "et", "ca", "non", "bien", "sur", "dans", "il", "y", "pas"]
)

NUMERO = re.compile(r"\b(\d+)\s*(bis|ter|quater)?\b", re.IGNORECASE)
CODE_POSTAL = re.compile(r"\b\d{5}\b")


@dataclass(frozen=True)
class Proposition:
    nom: str
    score: float
    # Does the number the caller said exist on this street? None if none said.
    # Q5: never told to the model, only recorded.
    numero_present: bool | None = None


@dataclass(frozen=True)
class Detection:
    statut: str
    entendu: str
    propositions: tuple[Proposition, ...] = field(default_factory=tuple)
    # Did the pronounced sounds decide? Without it an A/B of the sounds cannot
    # be read back (same reason as the town check's ``par_son``).
    par_son: bool = False

    @property
    def retenue(self) -> str:
        return self.propositions[0].nom if self.statut == SURE and self.propositions else ""


def est_type(mot: str) -> bool:
    """"rue", "rues", "impasses": the transcription writes plurals."""
    return mot in TYPES or (mot.endswith("s") and mot[:-1] in TYPES)


def sans_type(norme: str) -> str:
    """"rue de la République" -> "republique": the type does not discriminate.

    ⛔ A street left with nothing keeps its whole name: "Grande Rue".
    """
    mots = norme.split()
    reste = mots
    while reste and est_type(reste[0]):
        reste = reste[1:]
    while reste and reste[0] in ARTICLES and len(reste) > 1:
        reste = reste[1:]
    return " ".join(reste) if reste else " ".join(mots)


def _fenetres(norme: str, commune: str | None) -> tuple[list[str], str | None]:
    """The passages to compare, and the street type said if there is one."""
    norme = CODE_POSTAL.sub(" ", norme)
    if commune:
        norme = re.sub(rf"\b{re.escape(normaliser(commune))}\b", " ", norme)
    mots = norme.split()

    place = next((rang + 1 for rang, mot in enumerate(mots) if est_type(mot)), None)
    type_dit = mots[place - 1] if place else None
    zone = mots[place:] if place is not None else mots
    # ⛔ Tool words go even AFTER a street type: "allée des Mésanges Dorées à
    # Bury" left a stray "a" that made one more window, and the short window won.
    zone = [mot for mot in zone if mot not in MOTS_OUTILS and not mot.isdigit()]
    while zone and zone[0] in ARTICLES:
        zone = zone[1:]
    if not zone:
        return [], type_dit

    return [
        " ".join(zone[debut:fin])
        for debut in range(min(2, len(zone)))
        for fin in range(debut + 1, min(len(zone), debut + 6) + 1)
    ], type_dit


def analyser(
    texte: str,
    voies: VoiesCommune,
    commune: str | None = None,
    avec_sons: bool = True,
) -> Detection:
    """The verdict for the street named in ``texte``. Blocking: worker thread."""
    fenetres, type_dit = _fenetres(normaliser(texte), commune)
    if not len(voies) or not fenetres:
        return Detection(INTROUVABLE, "")

    # A window that leaves words out is penalised, BEFORE the max between windows.
    mots_zone = max(len(f.split()) for f in fenetres)
    penalites = np.array([[PENALITE_MOT * (mots_zone - len(f.split()))] for f in fenetres], dtype=float)

    def meilleur(gauche: list[str], droite: tuple[str, ...]) -> np.ndarray:
        matrice = process.cdist(gauche, droite, scorer=fuzz.ratio, workers=-1).astype(float)
        return (matrice - penalites).max(axis=0)

    scores = meilleur([cle_sonore(f) for f in fenetres], voies.cles_sonores)
    scores = np.maximum(scores, meilleur([cle_phonetique(f) for f in fenetres], voies.cles_phonetiques))

    par_son = False
    if avec_sons:
        prononces = sons(fenetres)
        if prononces:
            par_les_sons = meilleur([simplifier(p) for p in prononces], voies.sons)
            par_son = bool(par_les_sons.max() > scores.max())
            scores = np.maximum(scores, par_les_sons)

    if type_dit:
        racine = type_dit[:-1] if type_dit.endswith("s") and type_dit[:-1] in TYPES else type_dit
        for rang, type_voie in enumerate(voies.types):
            if type_voie.startswith(racine[:3]):
                scores[rang] += BONUS_TYPE

    numero = NUMERO.search(texte)
    dit = (numero.group(1) + (numero.group(2) or "")).lower() if numero else None

    ordre = np.argsort(-scores)[:PROPOSITIONS_MAXIMUM]
    propositions = tuple(
        Proposition(
            nom=voies.noms[rang],
            score=float(scores[rang]),
            numero_present=None if dit is None else (dit in voies.numeros[rang]),
        )
        for rang in ordre
        if scores[rang] >= SEUIL_PROPOSITION
    )
    entendu = fenetres[0]

    if not propositions:
        return Detection(INTROUVABLE, entendu, (), par_son)
    premiere = propositions[0]
    suivante = propositions[1].score if len(propositions) > 1 else 0.0
    if premiere.score >= SEUIL_SURE and premiere.score - suivante >= ECART_SURE:
        return Detection(SURE, entendu, propositions, par_son)
    return Detection(A_CONFIRMER, entendu, propositions, par_son)
