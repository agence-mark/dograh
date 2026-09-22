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
# ⛔ Only words that ANNOUNCE a street. Several were removed on 2026-09-22 after
# they anchored ordinary sentences on a street nobody had named:
#   - "dit": « je vous l'ai déjà **dit** », the most common French filler there
#     is. It was in the list for "lieu-dit", now handled as a pair below;
#   - "vieux": « un **vieux** conduit de cheminée »;
#   - "batiment": « le **bâtiment** B au deuxième étage ».
# ⚠️ Adjectives ("grande", "petite", "vieille") are NOT types either: they belong
# to the name ("Grande Rue"), and ``sans_type`` keeps them on both sides.
TYPES = frozenset(
    [
        "rue", "ruelle", "avenue", "av", "boulevard", "bd", "chemin", "allee", "impasse",
        "place", "placette", "route", "quai", "square", "residence", "lotissement",
        "cours", "cour", "passage", "sentier", "sente", "venelle", "voie", "hameau",
        "chaussee", "cite", "clos", "mail", "parvis", "promenade", "rond", "point",
        "faubourg", "fg", "montee", "cote", "descente", "esplanade", "traverse",
        "villa", "domaine", "parc", "ferme", "berge", "digue", "liaison", "rampe",
        "terrasse", "porte", "pont", "carrefour", "giratoire",
        # Zones d'activité: the BAN writes them as a prefix ("ZI la Grand
        # Colle"), and the same street also exists without it ("La Grand
        # Colle"). Without them the two keys differ, the search separates two
        # names of the same place, and announces one of them SURE.
        "zi", "za", "zac", "zone", "lieudit",
    ]
)
# "au lieu-dit les Granges" carries no street type: the pair itself is the anchor.
LIEU_DIT = ("lieu", "dit")
# What introduces the TOWN after the street: everything past it is the town,
# not the street's name. Cutting there is what lets the street keep a town's
# name ("12 rue de Creil à Creil").
MARQUEURS_DE_LIEU = frozenset(["a", "au", "aux", "sur", "pres", "vers", "commune", "ville"])
ARTICLES = frozenset(["de", "du", "des", "la", "le", "les", "l", "d"])
# Words of a caller's answer that never belong to a street name.
MOTS_OUTILS = frozenset(
    [
        "j", "habite", "c", "est", "au", "a", "oui", "euh", "alors", "donc", "le",
        "numero", "moi", "je", "suis", "bah", "ben", "voila", "voici", "merci", "l",
        "adresse", "mon", "ma", "et", "ca", "non", "bien", "sur", "dans", "il", "y",
        "pas", "ok", "ouais", "accord", "parfait", "exactement", "effectivement",
    ]
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


def _fenetres(
    norme: str, commune: str | None, autres_communes: tuple[str, ...] = ()
) -> tuple[list[tuple[str, int]], str | None, bool]:
    """The passages to compare — each with the length of the reading it comes
    from — the street type said, and whether the sentence is ANCHORED.

    🔴 The anchor is what separates an address from an ordinary sentence, and
    its absence was a blocking defect (independent review, 2026-09-22):
    **112 of 120 real ordinary sentences** produced a note asking the caller to
    spell a street. "oui d'accord" came back as « « accord » ne correspond à
    aucune rue de la commune. Fais épeler le nom de la rue. » — at every turn of
    the address step, which is exactly the loop Q4 forbids.

    A sentence is anchored when it says a street type ("rue", "chemin"), or a
    number followed by a word ("6 Danton"). Same rule as the town check, which
    learned it on 2026-09-16: reading a whole sentence gave 20 false sure towns
    on 64 sentences.
    """
    mots = CODE_POSTAL.sub(" ", norme).split()

    # 🔴 The town names are blanked FOR THE ANCHOR ONLY, never in the compared
    # passage. A town whose name starts with a street type
    # ("**Pont**-Sainte-Maxence") anchored a sentence on a street nobody named;
    # but removing town names from the passage itself deleted the STREET when
    # the street carries a town's name — "12 rue de Creil à Creil" came back
    # with nothing left to compare, silently (counter-review of 2026-09-22).
    # "rue de Paris", "avenue de Strasbourg", "rue d'Amiens": a very large and
    # very French family.
    masques = list(mots)
    for nom in (commune, *autres_communes):
        if not nom:
            continue
        for mot in normaliser(nom).split():
            masques = ["" if m == mot else m for m in masques]

    place = next((rang + 1 for rang, mot in enumerate(masques) if est_type(mot)), None)
    if place is None:
        paire = next(
            (rang for rang in range(len(masques) - 1) if tuple(masques[rang:rang + 2]) == LIEU_DIT),
            None,
        )
        place = paire + 2 if paire is not None else None
    type_dit = masques[place - 1] if place else None
    numero_suivi = any(
        mot.isdigit()
        and rang + 1 < len(masques)
        and masques[rang + 1]
        and not masques[rang + 1].isdigit()
        and masques[rang + 1] not in MOTS_OUTILS
        for rang, mot in enumerate(masques)
    )
    ancre = place is not None or numero_suivi
    zone = mots[place:] if place is not None else list(mots)

    # 🔑 The town comes AFTER the street, introduced by "à": "12 rue des
    # Tilleuls à Beauvais". Comparing the whole tail penalises the right window
    # ("tilleuls" leaves 3 words out, at PENALITE_MOT each), so the tail is cut.
    # ⛔ But a street name can CONTAIN that same form — the BAN is full of old
    # roads named after both ends ("Chemin … de Warluis à Montreuil-sur-Thérain",
    # 566 such names in four departments). So nothing is thrown away: BOTH
    # readings are compared, each penalised against its own length, and the
    # better one wins (counter-review of 2026-09-22).
    mots_de_ville = {
        mot for nom in (commune, *autres_communes) if nom for mot in normaliser(nom).split()
    }
    coupe = next(
        (
            rang
            for rang, mot in enumerate(zone)
            if rang > 0
            and mot in MARQUEURS_DE_LIEU
            and rang + 1 < len(zone)
            and zone[rang + 1] in mots_de_ville
        ),
        None,
    )
    lectures = [zone] if coupe is None else [zone[:coupe], zone]

    fenetres: dict[str, int] = {}
    for rang_lecture, lecture in enumerate(lectures):
        # ⛔ Tool words go even AFTER a street type: "allée des Mésanges Dorées à
        # Bury" left a stray "a" that made one more window, and the short one won.
        propre = [mot for mot in lecture if mot not in MOTS_OUTILS and not mot.isdigit()]
        while propre and propre[0] in ARTICLES:
            propre = propre[1:]
        if not propre:
            continue
        if rang_lecture and len(lectures) > 1:
            # ⛔ From the UNCUT reading, only the whole passage. Its sub-windows
            # would include the town alone, and a hamlet named after its own
            # commune ("Neuilly En Thelle" in Neuilly-en-Thelle) then came back
            # SURE on "rue des Quatre Vents à Neuilly-en-Thelle". The uncut
            # reading exists for one case only: a street name that CONTAINS
            # "à <town>", and that case needs the whole passage.
            fenetres.setdefault(" ".join(propre), len(propre))
            continue
        for debut in range(min(2, len(propre))):
            for fin in range(debut + 1, min(len(propre), debut + 6) + 1):
                # 🔑 Each window carries the length of ITS OWN reading: the
                # penalty for leaving words out is relative to the reading it
                # comes from, or the cut one would be crushed by the whole one.
                fenetres.setdefault(" ".join(propre[debut:fin]), len(propre))
    return list(fenetres.items()), type_dit, ancre


def analyser(
    texte: str,
    voies: VoiesCommune,
    commune: str | None = None,
    avec_sons: bool = True,
    autres_communes: tuple[str, ...] = (),
) -> Detection:
    """The verdict for the street named in ``texte``. Blocking: worker thread.

    ``autres_communes``: the other town names heard in this same turn, which the
    town check found. They are removed like the settled one.
    """
    lues, type_dit, ancre = _fenetres(normaliser(texte), commune, autres_communes)
    if not len(voies) or not lues:
        return Detection(INTROUVABLE, "")

    fenetres = [fenetre for fenetre, _ in lues]
    # A window that leaves words out is penalised, BEFORE the max between windows.
    penalites = np.array(
        [[PENALITE_MOT * (longueur - len(fenetre.split()))] for fenetre, longueur in lues],
        dtype=float,
    )

    def matrice_de(gauche: list[str], droite: tuple[str, ...]) -> np.ndarray:
        """Windows x streets, penalty applied. ⛔ Kept as a matrix: reducing it
        here lost which window won, and the note quoted the first word of the
        sentence instead ("« accord »", "« n »") — never what was heard."""
        brute = process.cdist(gauche, droite, scorer=fuzz.ratio, workers=-1).astype(float)
        return brute - penalites

    matrice = matrice_de([cle_sonore(f) for f in fenetres], voies.cles_sonores)
    matrice = np.maximum(matrice, matrice_de([cle_phonetique(f) for f in fenetres], voies.cles_phonetiques))

    par_son = False
    if avec_sons:
        prononces = sons(fenetres)
        if prononces:
            par_les_sons = matrice_de([simplifier(p) for p in prononces], voies.sons)
            par_son = bool(par_les_sons.max() > matrice.max())
            matrice = np.maximum(matrice, par_les_sons)

    scores = matrice.max(axis=0)
    # The window that actually won, for the note to quote it.
    fenetre_gagnante = fenetres[int(matrice.max(axis=1).argmax())]

    if type_dit:
        racine = type_dit[:-1] if type_dit.endswith("s") and type_dit[:-1] in TYPES else type_dit
        for rang, type_voie in enumerate(voies.types):
            if type_voie.startswith(racine[:3]):
                scores[rang] += BONUS_TYPE

    # 🔴 A street whose name IS the commune's name can never be "sure".
    # Hamlets carry their commune's name in the BAN ("Neuilly En Thelle" in
    # Neuilly-en-Thelle), so a caller who just says where they live came back
    # with « utilise ce nom » on a street they never named — the more so once
    # the number conversion ate a word ("rue des Quatre Vents" -> "rue des 4
    # Vents" -> only "vents" left to compare). It stays proposable, never sure.
    if commune:
        nom_commune = normaliser(commune)
        for rang, nom in enumerate(voies.noms):
            if sans_type(normaliser(nom)) == nom_commune or normaliser(nom) == nom_commune:
                scores[rang] = min(scores[rang], SEUIL_SURE - 1)

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
    premiere = propositions[0] if propositions else None
    suivante = propositions[1].score if len(propositions) > 1 else 0.0
    sure = (
        premiere is not None
        and premiere.score >= SEUIL_SURE
        and premiere.score - suivante >= ECART_SURE
    )

    # 🔴 Nothing is said about a sentence that is not anchored on an address.
    # NO exception — not even for a sure verdict. A first version spared the
    # sure ones, so that a short answer to "quelle rue ?" ("Victor Hugo") would
    # still be checked; the counter-review of 2026-09-22 asked for that door to
    # be tried against the BIGGEST commune, where collisions are likeliest, and
    # it let three through in Paris: "Strasbourg" became SURE as "Boulevard de
    # Strasbourg", "sans lis" as "Rue de Senlis", "À Saint-Laurent" as "Rue
    # Saint-Laurent". All three are TOWN names — exactly what a caller answers
    # at an address step.
    # Measured cost of closing the door: 0 of the 27 real streets of the runs,
    # 9 of the 300 of the sound bench. Cheap, against the one rule that outranks
    # everything here.
    if not ancre:
        return Detection(INTROUVABLE, "", (), par_son)

    if not propositions:
        # 🔴 « Introuvable » fait réclamer une épellation (Q4). On ne la réclame
        # que si l'appelant a DIT un type de voie : c'est le seul mot qui affirme
        # qu'il parle d'une rue. Un numéro suffit à comparer, jamais à exiger.
        # Sans cette règle, « c'est le bâtiment B au deuxième étage » et un
        # numéro de téléphone dicté faisaient demander d'épeler une rue.
        return Detection(INTROUVABLE, fenetre_gagnante if type_dit else "", (), par_son)
    if sure:
        return Detection(SURE, fenetre_gagnante, propositions, par_son)
    return Detection(A_CONFIRMER, fenetre_gagnante, propositions, par_son)
