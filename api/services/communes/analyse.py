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
from dataclasses import dataclass, replace
from functools import lru_cache
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
# Chantier correctifs-modules, lot 3 (runs 862, 863) : la transcription écrit les
# types au pluriel (« trois rues des Merles », « deux places Victor Hugo ») et
# « Merles », « Hugo » étaient lus comme des communes.
TYPES_VOIE |= {t + "s" for t in TYPES_VOIE if t not in ("lieu", "dit", "cours", "av", "bd", "za", "zac")}
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

# K12 (run 1511, « Vendredi » lu Vendrest, à confirmer) : a reading that starts or ends with a day, a
# month or another word of a date is never a town (« vendredi », « plutôt jeudi » read Puteaux). Calendar
# words of the language, no trade word. A town that bears one (« Mars », « Avril ») is still read when the
# caller says so (« la commune de Mars », « j'habite Mars »), or as a name written in one piece
# (« Mars-la-Tour »).
MOTS_DE_DATE = frozenset(
    """lundi mardi mercredi jeudi vendredi samedi dimanche
    janvier fevrier mars avril mai juin juillet aout septembre octobre novembre decembre
    aujourd hui demain hier matin soir midi prochain prochaine dernier derniere semaine mois annee""".split()
)
AMORCES_DE_COMMUNE_DITE = frozenset({"commune", "ville", "habite", "habitons", "habitent", "situe", "sis"})

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
# Chantier correctifs-apres-banc-v4 (C2, C5): a name WRITTEN as the words heard,
# same value as ``ORTHO_NOM_A_NOMBRE`` of the number reader.
ORTHO_NOM_ECRIT = 90
# A town of a department the caller said ("dans l'Oise").
BONUS_DEPARTEMENT = 15
# V5 (plan voix-et-communes), measured by sweep on 2026-09-17: the pronounced
# sounds count from SEUIL_ESP, lowered by DECALAGE_ESP before joining the
# spelling scores. POIDS_ESP = 0 turns them off.
POIDS_ESP = 1
SEUIL_ESP = 80
DECALAGE_ESP = 0
# Readings longer than this are not listened to (the longest name caught by its
# sounds on the benches, « Verneuil en alerte », is three words).
MOTS_MAX_SONS = 4

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
    # V5: the reading owes its score to the pronounced sounds, not to the spelling.
    par_son: bool = False

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
    # D4 (chantier correctifs-modules) : « lieu », « nom » ou « son », posée par
    # ``communes.force`` quand la fiche est allumée ; None sinon.
    force: str | None = None


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


def _joints(texte: str, mots: list[str], signes: str = "-’'`") -> set[int]:
    """Positions k whose word is glued to word k + 1 by one of ``signes`` in the
    ORIGINAL sentence: a hyphen or an apostrophe by default ("Saint-Le-Destran",
    "l'Isle")."""
    jetons = [m for m in re.finditer(rf"[^{_SEPARATEURS[1:-1]}]+", texte)]
    if len(jetons) != len(mots):
        return set()
    motif = "[" + re.escape(signes) + "]"
    return {
        k for k in range(len(jetons) - 1)
        if re.search(motif, texte[jetons[k].end():jetons[k + 1].start()])
    }


_INDEX_PREMIER_MOT: dict[int, dict[str, list[int]]] = {}


def _par_premier_mot(base: BaseCommunes) -> dict[str, list[int]]:
    """B1 (relecture du 01/10) : les communes rangées par premier mot de leur nom,
    calculé une fois par base, pour ne pas parcourir les 35 000 noms à chaque tour."""
    index = _INDEX_PREMIER_MOT.get(id(base))
    if index is None:
        index = {}
        for j, norm in enumerate(base.norms):
            if norm:
                index.setdefault(norm.split()[0], []).append(j)
        _INDEX_PREMIER_MOT.clear()
        _INDEX_PREMIER_MOT[id(base)] = index
    return index


def _homonyme_plus_proche(base: BaseCommunes, top: Lecture, magasin: tuple[float, float]) -> Commune | None:
    """B1 : la commune la plus proche de l'établissement dont le nom est celui de
    ``top`` suivi d'un complément, si elle est au moins DEUX FOIS plus proche que ``top``
    (comparaison entre les deux, jamais un rayon) ET au moins aussi peuplée ; None
    sinon. « poêle à bois » pour un établissement de Marseille ne fait pas proposer
    Bois-d'Amont (400 km) contre Bois (550 km). « Beauvais » reste Beauvais pour un établissement de
    Marseille, même si Beauvais-sur-Tescou est plus proche (corpus réel : Bordeaux,
    Beauvais, Soissons). Seulement pour un nom entendu exactement, jamais sur un
    préfixe générique."""
    nom = normaliser(top.commune.nom)
    if not nom or nom in PREFIXES_GENERIQUES or top.ortho < 100:
        return None
    debut = nom + " "
    distance_top = distance_km(top.commune, *magasin)
    meilleure, meilleure_distance = None, distance_top / 2
    for j in _par_premier_mot(base).get(nom.split()[0], ()):
        norm = base.norms[j]
        if norm.startswith(debut) and base.communes[j].population >= top.commune.population:
            d = distance_km(base.communes[j], *magasin)
            if d < meilleure_distance:
                meilleure, meilleure_distance = base.communes[j], d
    return meilleure


def _lettres_epelees(mots: list[str]) -> set[int]:
    """B3 : les positions des lettres seules qui se suivent à trois ou plus."""
    positions: set[int] = set()
    serie: list[int] = []
    for k, m in enumerate([*mots, ""]):
        if len(m) == 1 and m.isalpha():
            serie.append(k)
            continue
        if len(serie) >= 3:
            positions.update(serie)
        serie = []
    return positions


def _segments(texte: str, mots: list[str], spans_cp, mots_cp: set[int], avec_lecteur: bool,
              apres_rue: bool = False):
    """The readings of a sentence a town may hide in: (start, length, words, after an amorce).

    ``apres_rue`` (C4): also the readings that end the sentence after a street,
    each tuple then carrying a fifth element, the rank of that street's type
    (None for an ordinary reading)."""
    joints = _joints(texte, mots)
    tirets = _joints(texte, mots, "-")
    # B3 (chantier fiabilite-fiche-et-renvoi, run 935) : les lettres d'une épellation
    # (trois lettres seules d'affilée ou plus) ne sont pas des mots de la réponse.
    # « Oui, Montataire. Et mon nom c'est Meunier, m e u n i e r » comptait les lettres
    # et perdait « Montataire ». ⛔ Pas les lettres isolées d'une élision (« l'appel »).
    epelees = _lettres_epelees(mots)
    reponse_courte = sum(
        1 for k, m in enumerate(mots) if m not in MOTS_HORS_COMPTE and not m.isdigit() and k not in epelees
    ) <= 5
    for i in range(len(mots)):
        # A name right after a street type is a street name, not a town.
        avant = mots[max(0, i - 3):i]
        voies = [k for k, m in enumerate(avant) if m in TYPES_VOIE]
        # Chantier correctifs-apres-banc-v4, C1 (question n° 383) : un code
        # postal entre le type de voie et ce mot clôt le nom de la rue. « 12
        # avenue Foch, 60000 Beauvais » ne lisait pas Beauvais (le type était à
        # trois mots), et le code partagé restait « à confirmer » entre Beauvais
        # et Allonne. ⛔ Le code seulement : un nombre peut être dans un nom de
        # rue (« rue du 8 Mai 1945 »), un code postal jamais.
        apres_le_code = voies and any(
            d <= k < f for d, f in spans_cp for k in range(i - len(avant) + voies[-1] + 1, i)
        )
        bloque = bool(
            voies and not apres_le_code and not any(m in AMORCES for m in avant[voies[-1]:])
        )
        # C4 (question n° 209) : la commune dite juste après la rue, sans « à »
        # ni code (« 5 rue du vieux moulin pont saint maxence »), n'était jamais
        # lue : trop près du type, ou sans amorce. Une lecture qui FINIT la
        # phrase, après un type de voie et au moins un mot de nom, est proposée
        # quand même, marquée du rang de ce type : ``analyser`` ne la garde que
        # si les mots entre le type et elle sont une rue SÛRE de cette commune
        # (module des rues). Sinon elle disparaît : rien ne change.
        # Même règle pour une lecture que seul le code postal qui la SUIT
        # ancre : « 12 Rue du Général de Gaulle, 60180 Nogent-sur-Oise »
        # proposait « Gaulle » comme Gauville, mot de la rue collé au code.
        # La rue est « ouverte » : un type plus haut, ni amorce ni code entre.
        rue = None
        for k in range(i - 1, -1, -1):
            if mots[k] in AMORCES or any(d <= k < f for d, f in spans_cp):
                break
            if mots[k] in TYPES_VOIE:
                rue = k if k <= i - 2 else None
                break
        if not apres_rue:
            rue = None
        if bloque and rue is None:
            continue
        # T8 (plan voix-et-communes): the rest of a name that opens on a generic
        # prefix is not a town of its own. "Saint-Le-Destran" read "Le-Destran"
        # as Lestrem (62), sure (run 265). An article counts only when glued.
        if i > 0 and mots[i - 1] in PREFIXES_GENERIQUES and (
            mots[i - 1] not in ARTICLES or (i - 1) in joints
        ):
            continue
        # Same motif inside a name written with hyphens: no reading starts in its
        # middle ("Lachapelle-sous-Chanéac" is not Chanéac, France-wide sweep of
        # 2026-09-17). Hyphens only: "je viens d'Amiens" is Amiens.
        if i > 0 and (i - 1) in tirets:
            continue
        for n in range(1, N_MAX + 1):
            seg = mots[i:i + n]
            if len(seg) < n:
                break
            # ... nor ends in its middle ("Saint-Paul-sur-Ubaye" is not "Saint" -> Saint-Ay).
            if (i + n - 1) in tirets:
                continue
            if (seg[0] in MOTS_OUTILS and not (n > 1 and seg[0] in ARTICLES)) or seg[-1] in MOTS_OUTILS or seg[-1] in LIAISONS:
                continue
            debut_utile = all(m in MOTS_VIDES_REPONSE for m in mots[:i])
            ancre = (
                (i > 0 and mots[i - 1] in AMORCES)
                or (reponse_courte and debut_utile)
                or any(f == i or d == i + n for d, f in spans_cp)
            )
            ancre_propre = (
                (i > 0 and mots[i - 1] in AMORCES)
                or (reponse_courte and debut_utile)
                or any(f == i for d, f in spans_cp)
            )
            a_valider = (
                rue is not None
                and not ancre_propre
                and (i + n == len(mots) or any(d == i + n for d, f in spans_cp))
            )
            if a_valider:
                ancre, bloque_ici = True, False
            else:
                bloque_ici = bloque
            if bloque_ici or not ancre:
                continue
            if any(m.isdigit() for m in seg) or any(m in TYPES_VOIE for m in seg):
                continue
            if (
                (seg[0] in MOTS_DE_DATE or seg[-1] in MOTS_DE_DATE)
                and not (n > 1 and all((i + k) in joints for k in range(n - 1)))
                and not any(m in AMORCES_DE_COMMUNE_DITE for m in mots[max(0, i - 2):i])
            ):
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
            amorce = i > 0 and mots[i - 1] in AMORCES
            if apres_rue:
                yield i, n, extrait, amorce, rue if a_valider else None
            else:
                yield i, n, extrait, amorce


@lru_cache(maxsize=256)
def _rue_de_la_commune(rue: str, insee: str, nom: str) -> bool:
    """C4 : ``rue`` (« rue du vieux moulin ») est-elle une rue SÛRE de ``commune``
    pour le module des rues ? Lecture locale de l'annuaire, comme le module des
    rues en appel. ⛔ Tout échec (annuaire absent, département sans fichier)
    vaut non : la lecture est alors écartée, comme avant le chantier."""
    try:
        from api.services.voies import base as base_voies
        from api.services.voies.analyse import SURE as VOIE_SURE
        from api.services.voies.analyse import analyser as analyser_voie

        return analyser_voie(rue, base_voies.voies_de(insee), nom).statut == VOIE_SURE
    except Exception:  # noqa: BLE001 -- une lecture de plus ne coûte jamais l'appel
        return False


def _une_commune_du_code_ressemble(base: BaseCommunes, cps: set[str], extrait: str) -> bool:
    """C5 : une commune d'une des lectures du code ressemble-t-elle aux mots ?"""
    from rapidfuzz import fuzz

    son = cle_sonore(extrait)
    return any(
        max(fuzz.partial_ratio(son, base.sons[j]), fuzz.partial_ratio(extrait, base.norms[j])) >= SEUIL_PHON
        for cp in cps
        for j in base.par_cp.get(cp, [])
    )


# Revue m8 : l'index vit sur l'objet base lui-même (jamais sous ``id(base)``, réutilisable par une autre base).
_ATTRIBUT_DES_FINS = "_fins_de_nom_par_departement"


def _fins_de_nom(base: BaseCommunes, departements, extrait: str) -> list[int]:
    """C3 : les communes des départements dits dont le nom, en plusieurs mots,
    finit par ``extrait`` (« maxence » -> Pont-Sainte-Maxence). Index construit
    une fois par département et par base."""
    if not departements or extrait in PREFIXES_GENERIQUES or len(extrait.replace(" ", "")) < 4:
        return []
    trouvees: list[int] = []
    par_departement = base.__dict__.setdefault(_ATTRIBUT_DES_FINS, {})
    for dep in departements:
        index = par_departement.get(dep)
        if index is None:
            index = {}
            for j, commune in enumerate(base.communes):
                if commune.dep != dep:
                    continue
                mots = base.norms[j].split()
                for k in range(1, len(mots)):
                    if mots[k] not in LIAISONS:
                        index.setdefault(" ".join(mots[k:]), []).append(j)
            par_departement[dep] = index
        trouvees += index.get(extrait, [])
    return trouvees


def analyser(
    texte: str,
    base: BaseCommunes,
    magasin: tuple[float, float] | None = None,
    codes_postaux: Mapping[str, Sequence[tuple[int, int]]] | None = None,
    departements: set[str] | frozenset[str] | None = None,
    mots_nombres: set[int] | frozenset[int] | None = None,
    *,
    avec_sons: bool = True,
) -> list[Detection]:
    """The towns named in ``texte``, each with a verdict.

    ``magasin`` is the (longitude, latitude) of the business: towns nearby get
    a bonus, which is what separates "Bovet" -> Beauvais (60) from Boves (80).
    ``avec_sons=False`` (the agent's switch, L18 of 2026-09-17): the spelling
    keys alone, exactly as when the pronunciation library is absent.
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
        (i, n, extrait, amorce, cle_phonetique(extrait), cle_sonore(extrait), rue)
        for i, n, extrait, amorce, rue in _segments(
            texte, mots, spans_cp, mots_cp, codes_postaux is not None, apres_rue=True
        )
    ]
    attente = [a for a in attente if len(a[5]) >= 2]

    fenetres: list[tuple[float, int, int, list[Lecture], list[Lecture]]] = []
    if attente:
        import numpy as np
        from rapidfuzz import fuzz, process

        m_phon = process.cdist([t[4] for t in attente], base.phons, scorer=fuzz.ratio,
                               score_cutoff=SEUIL_PHON, dtype=np.uint8, workers=-1)
        m_son = process.cdist([t[5] for t in attente], base.sons, scorer=fuzz.ratio,
                              score_cutoff=SEUIL_PHON, dtype=np.uint8, workers=-1)
        m_max = m_orthographe = np.maximum(m_phon, m_son)
        # V5 (plan voix-et-communes): the pronounced sounds, in one call for the
        # whole sentence, scored on their own threshold and combined by the
        # maximum, so a town already recognised is never lost. The sounds FIND
        # candidates; the spelling decides between towns that sound alike (below).
        # ⏱️ Only the readings the spelling did not already find at a sure level:
        # "Beauvais" needs no sounds. Measured 2026-09-17: the sounds of every
        # reading took the step from 12 to 16 ms (plan ceiling 15).
        a_ecouter = [
            w for w in range(len(attente))
            if attente[w][1] <= MOTS_MAX_SONS and m_orthographe[w].max(initial=0) < PHON_EXACT
        ]
        sons_entendus = (
            sons([attente[w][2] for w in a_ecouter])
            if a_ecouter and base.esps and POIDS_ESP and avec_sons
            else None
        )
        if sons_entendus is not None:
            m_esp = process.cdist([base.cle_de_son(e) for e in sons_entendus], base.esps_cles, scorer=fuzz.ratio,
                                  score_cutoff=SEUIL_ESP, dtype=np.uint8, workers=-1)
            m_esp = np.where(m_esp > 0, np.clip(m_esp.astype(np.int16) - DECALAGE_ESP, 0, 100), 0).astype(np.uint8)
            m_max = m_max.copy()
            m_max[a_ecouter] = np.maximum(m_max[a_ecouter], m_esp)
        for w, (i, n, extrait, amorce, k_phon, k_son, rue) in enumerate(attente):
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
            # Chantier correctifs-apres-banc-v4, C3 (question n° 225) : un
            # département dit, ses communes dont le nom FINIT par les mots
            # entendus sont comparées aussi, comme celles d'un code postal.
            # « Maxence dans l'Oise » ne trouvait que Maxent (Ille-et-Vilaine) :
            # Pont-Sainte-Maxence n'était jamais candidate. Mots entiers
            # seulement, jamais un préfixe générique ; jamais sûre : son nom
            # entendu reste à 0 (``phon_nom``), comme un nom partiel soutenu par
            # un code postal (règle du 16/09 plus bas).
            # ⛔ Zéro perte (filet des 687 phrases) : quand une commune est ÉCRITE
            # comme les mots entendus (« Vers, dans le Lot »), ces communes ne
            # passent pas devant ; elles restent en réserve pour C2 ci-dessous.
            partielles = [j for j in _fins_de_nom(base, departements, extrait) if j not in idxs]
            ecrite = any(fuzz.ratio(extrait, base.norms[j]) >= PHON_EXACT for j in idxs)
            for j in partielles:
                idxs[j] = 100.0
            reserve = {base.communes[j].insee for j in partielles} if ecrite else set()
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
                par_son = float(m_orthographe[w][j]) < s_phon and j in noms and noms[j] == s_phon
                lectures.append(Lecture(c, score, s_phon, s_ortho, s_nom, par_code, par_son))
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
            reservees = [l for l in lectures if l.commune.insee in reserve]
            lectures = [l for l in lectures if l.commune.insee not in reserve]
            if not lectures:
                continue
            # V5, sounds and spelling together (Evan, 2026-09-17): a town that only
            # SOUNDS like the words never beats a town WRITTEN like them. "Angecourt"
            # sounds exactly like Angicourt, nearer the shop: Angecourt goes first,
            # and the two stay to confirm. Without this, the France-wide sweep gained
            # 7 false sure towns, all homophones.
            if lectures[0].par_son:
                ecrites = [l for l in lectures if not l.par_son and l.phon >= PHON_SURE]
                if ecrites:
                    lectures.remove(ecrites[0])
                    lectures.insert(0, ecrites[0])
            # C4 : une lecture après la rue ne vaut que si la rue est une rue SÛRE
            # de la commune lue en tête.
            # ⏱️ Seulement une lecture qui passerait le seuil de détection (plus bas) :
            # le module des rues n'est interrogé que pour elle.
            if rue is not None and (
                lectures[0].score < SEUIL_DETECTION + POIDS_POP * math.log10(1000)
                or not _rue_de_la_commune(" ".join(mots[rue:i]), lectures[0].commune.insee,
                                          lectures[0].commune.nom)
            ):
                continue
            fenetres.append((lectures[0].score, i, i + n, lectures, reservees))

    # Readings that do not overlap, best first. An exact reading over several
    # words goes before the pieces it contains ("Clermont Ferrand" before
    # "Clermont"), whatever the pieces score.
    fenetres.sort(key=lambda f: -f[0])
    exactes = [f for f in fenetres if f[2] - f[1] > 1 and f[3][0].phon >= 90]
    exactes.sort(key=lambda f: (-(f[2] - f[1]), -f[0]))
    fenetres = exactes + [f for f in fenetres if f not in exactes]
    prises: list[Detection] = []
    for score, d, f, lectures, reservees in fenetres:
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
        if sure and (codes_postaux is not None or departements) and top.par_code and not top.nom_exact:
            sure = False
        # Chantier correctifs-apres-banc-v4, C2 (question n° 225) : un
        # département dit, que la commune sûre ne porte pas, alors qu'une commune
        # de ce département porte ces mots en fin de nom : la première n'est plus
        # sûre et la seconde est proposée juste après. « Longueau dans l'Oise »
        # annonçait Longueau (Somme) sûre ; Saint-Martin-Longueau (Oise) vient
        # en second, à confirmer.
        # ⛔ Seulement avec une telle commune : sans elle, le filet des 687
        # phrases perdait « Gisor dans l'Oise » (Gisors, Eure) et « Clairement
        # Ferrand dans l'Oise », sûres en production.
        # Elle passe derrière toute commune écrite comme les mots entendus (« Vers,
        # dans le Lot » garde Vers en Haute-Savoie à son rang, filet des 687).
        if sure and departements and top.commune.dep not in departements and reservees:
            sure = False
            place = 1 + max(
                (k for k, l in enumerate(lectures[:3]) if l.ortho >= ORTHO_NOM_ECRIT), default=0
            )
            lectures = [*lectures[:place], *reservees, *lectures[place:]]
        # C5 (question n° 282) : un code postal dit dans le message, dont AUCUNE
        # lecture n'est un code de la commune, alors qu'une commune de ce code
        # ressemble aux mots entendus (même test que les communes d'un code, plus
        # haut) : la commune n'est pas sûre. « soixante cinq cent cinquante
        # vernayon à la » annonçait Vernon (Eure) sûre ; le code 60550 est celui
        # de Verneuil-en-Halatte, qui ressemble à « vernayon » (83).
        # ⛔ Un nom ÉCRIT comme entendu n'est pas touché par cette règle (même
        # principe que ``_ville_par_code`` du number reader : un nom épelé tel
        # quel ne se laisse pas déplacer par un code mal entendu) ; l'orthographe,
        # pas le son (Vernon sonne à 90 et plus).
        # ⛔ Sans commune du code qui ressemble, rien ne change : « Vers néanalate,
        # soixante mille cinq cent soixante » reste Verneuil-en-Halatte sûre
        # (filet des 687 phrases).
        if (
            sure
            and cps
            and not set(top.commune.cps) & cps
            and top.ortho < ORTHO_NOM_ECRIT
            and _une_commune_du_code_ressemble(base, cps, " ".join(mots[d:f]))
        ):
            sure = False
        # B1 (chantier fiabilite-fiche-et-renvoi, run 935, D1 d'Evan du 01/10) : un nom
        # exact n'est plus sûr quand une autre commune, PLUS PROCHE de l'établissement,
        # porte ce nom suivi d'un complément (« Nogent » : Nogent en Haute-Marne, ou
        # Nogent-sur-Oise à côté). Les deux sont proposées, la plus proche d'abord.
        # Comparaison entre les deux communes, jamais un rayon (décision du 17/09).
        if sure and magasin and not top.par_code:
            proche = _homonyme_plus_proche(base, top, magasin)
            if proche is not None:
                sure = False
                # Le nom dit ouvre exactement celui de la commune proposée : même
                # règle que plus haut (« Beaumont 95260 » est Beaumont-sur-Oise).
                lectures = [Lecture(proche, top.score, top.phon, top.ortho, 100.0), *lectures]
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
# Proposals to confirm: only on words that resemble the commune (2026-09-17)
# --------------------------------------------------------------------------- #

_DE = frozenset({"de", "d", "du", "des"})
# Grammar words that place something relative to a place (review of 2026-09-17):
# « à côté de la gare », « c'est vers Bovet »: followed by more words, they are a
# preposition, not a town.
LIEUX_RELATIFS = frozenset(
    """cote bord bords sortie entree bout pres proximite abords alentours environs centre milieu
    fond face hauteur niveau pied coin limite derriere devant vers nord sud ouest""".split()
)


# B1 (constat du run 1048, plan de réparation globale du 08/10) : « à » seul ne dit pas un lieu
# (« un poêle à granulés » proposait Grandrû). Il en dit un après un verbe d'être ou d'habitation,
# ou en tête de réponse, ou après une adresse (type de voie, numéro) ; après un autre mot, la
# proposition à confirmer qui n'a que lui pour amorce tombe. Revue du 10/10 (zéro perte, décision du
# 17/09) : « je vis à Brel », « j'ai une maison à Brel » perdaient Bresles ; les verbes et les noms qui
# situent sont donc listés largement, et chaque tournure perdue entre au corpus du test.
# ⛔ Aucune règle ne dépend de l'établissement (décision du 17/09, gardée par
# ``test_aucune_regle_ne_depend_du_magasin``) : le rayon et le son proche du plan sont une décision
# d'Evan (ils font perdre « Grand Villiers » -> Grandvilliers, « Abrel dans l'Oise » -> Bresles).
VERBES_DE_LIEU = frozenset(
    """suis es est sommes etes sont etais etait c habite habites habitons habitez habitent habiter
    vis vit vivons vivez vivent vivre loge loges logeons logez logent loger reste restes restons
    restez restent rester reside residons residez resident resider demeure demeurons demeurent
    situe situee situes situees sis sise trouve trouvons trouvez trouvent base basee bases basees
    domicilie domiciliee domicilies domiciliees implante implantee installe installee installes
    installees installer etabli etablie vais va allons allez vont aller viens vient venons venez
    viennent venir travaille travailles travaillons travaillez travaillent travailler livre livrer
    livrez arrive arrivons passer passe passez intervenir intervenez venu venue ne nee""".split()
)
# Les noms qui situent : « une maison à », « le chantier est à » (ce dernier par « est »).
NOMS_DE_LIEU = frozenset(
    """maison maisons appartement logement domicile residence pavillon ferme propriete terrain
    chantier adresse commune ville village quartier secteur coin bureau bureaux atelier local
    locaux entreprise societe magasin boutique agence usine garage siege site habitation gite
    intervention interventions passage livraison installation visite rendez vous nous""".split()
)


SUJETS = frozenset({"il", "elle", "ils", "elles", "y"})


def _a_apres_un_nom(mots: list[str], d: Detection) -> bool:
    """Les mots de ``d`` ne sont-ils introduits que par un « à » qui suit un nom (« poêle à granulés ») ?
    Un code postal dit dans la phrase, une adresse avant lui, ou « à » en tête de réponse ou juste
    après un verbe d'être ou d'habitation (« je suis à », « c'est à », « j'habite à »), garde la
    proposition."""
    i = d.debut
    if d.codes_postaux_dits or i <= 1 or mots[i - 1] != "a":
        return False
    avant = mots[: i - 1]
    # Une adresse avant lui (« douze rue des Lilas à Bovet ») : « à » y dit bien la commune.
    if any(m in TYPES_VOIE or m.isdigit() or (m in MOTS_NOMBRE and m not in ("un", "une")) for m in avant):
        return False
    # Le mot juste avant « à » : un verbe d'être ou d'habitation, un sujet (« il y a ») ou un mot vide
    # dit un lieu ; un nom (« poêle à ») ne le dit pas.
    return avant[-1] not in MOTS_VIDES_REPONSE | VERBES_DE_LIEU | NOMS_DE_LIEU | SUJETS


def _article_du_nom(article: str, nom_normalise: str) -> bool:
    """« la signy » can be Lassigny, « la morley » Lamorlaye: the article may be
    glued in the commune's name. « l'année » is not Anet, « la maison » not Maisons."""
    return nom_normalise.replace(" ", "").startswith(article)


def propositions_fondees(texte: str, detections: list[Detection], base: BaseCommunes) -> list[Detection]:
    """The detections, without the communes proposed on words that name no place.

    Decision of Evan, 2026-09-17 (fiche D, runs 269 to 272): the agent names the
    first commune to confirm aloud, so « L'année dernière » proposed Anet and
    « c'est à côté de la boulangerie » Contay. Rule of Evan for this repair: zero
    loss against production for any shop; what no such rule removes is a known limit.

    1. An article belongs to the commune's name, glued or not: « l'année » is not
       Anet (the article opens the words heard), « la maison » is not Maisons
       (it comes right before them); « la signy » stays Lassigny.
    2. Words that place relative to a place (« côté », « vers »), followed by
       « de » or by words not introduced by a place marker, are a preposition:
       « à côté de la gare » is not Contay, « c'est vers Bovet » not Vers;
       « j'habite à Vers, dans le Lot » is Vers.

    ⛔ No complement rule (final review of 2026-09-17): « passe | aux choses »
    also erased communes said alone then followed by a place, present in
    production: « Grand Villiers, au Moulin. », « Compiagnes, au Clos des
    Roses. », « Bovet. Au revoir. », « Champly, à la zone industrielle. ».

    3. B1 (plan of 2026-10-08, run 1048): a proposal to confirm whose only lead is an « à » that
       follows a noun (``_a_apres_un_nom``) is dropped: « poêle à granulés » is not Grandrû. A
       commune backed by a postal code or written exactly as its name is kept.

    ⛔ No resemblance threshold and no radius around the shop (decision of Evan,
    2026-09-17, option d): measured on the real corpus with five shops, a 40 km
    radius lost « perçant » -> Persan, « Abrel » -> Bresles and « bonsoir Oise »
    -> Beaumont-sur-Oise for Compiègne (17), Coignières (10) and Marseille (7).
    The shop's location keeps its other uses (proximity bonus, nearest postal
    code, last sure town), as in production.

    ⚠️ Known limits: « L'année dernière » still proposes Lanne (Hautes-Pyrénées),
    a lone « Delaunay » Launay (rule 3 closes « poêle à granulés » only). These are said outside the
    address question: the remedy is a dedicated identity step in the agent, not
    this module.

    Only proposals TO CONFIRM are touched: a sure town, a postal code heard, a
    commune backed by a postal code and a name written exactly as the commune
    (« Saint-Laurent », « à Vers, dans le Lot ») are always kept. A detection
    left with no proposal is dropped. No rule depends on the shop's location.
    Blocking: worker thread, like ``analyser``.
    """
    if not any(d.statut == A_CONFIRMER and not d.code_postal_entendu for d in detections):
        return detections
    mots = normaliser(texte).split()
    gardees: list[Detection] = []
    for d in detections:
        if d.statut != A_CONFIRMER or d.code_postal_entendu or d.debut < 0:
            gardees.append(d)
            continue
        extrait = " ".join(mots[d.debut:d.fin])
        # « c'est vers Bovet », « à côté de la gare »: a preposition;
        # « j'habite à Vers, dans le Lot »: a place.
        preposition = (
            d.fin < len(mots)
            and all(m in LIEUX_RELATIFS for m in mots[d.debut:d.fin])
            and (mots[d.fin] in _DE or not (d.debut > 0 and mots[d.debut - 1] in AMORCES))
        ) or (d.fin - d.debut > 1 and mots[d.debut] in LIEUX_RELATIFS and mots[d.debut + 1] in _DE)
        article = mots[d.debut] if d.fin - d.debut > 1 and mots[d.debut] in ARTICLES else None
        article_avant = mots[d.debut - 1] if d.debut > 0 and mots[d.debut - 1] in ARTICLES else None

        def fondee(l: Lecture) -> bool:
            if l.par_code:
                return True
            j = base.par_insee[l.commune.insee]
            exact = extrait == base.norms[j]
            # A name of several words written exactly is never an accident (Bout-du-Pont-de-Larn).
            if exact and d.fin - d.debut > 1:
                return True
            if preposition:
                return False
            if exact:
                return True
            if article is not None and not _article_du_nom(article, base.norms[j]):
                return False
            if article_avant is not None and not _article_du_nom(article_avant, base.norms[j]):
                return False
            return True

        a_apres_un_nom = _a_apres_un_nom(mots, d)

        def hors_contexte(l: Lecture) -> bool:
            # Un nom écrit exactement n'est jamais un accident (deux « Abbécourt » : les deux restent).
            return a_apres_un_nom and not l.par_code and l.ortho < 100

        lectures = tuple(l for l in d.lectures if fondee(l) and not hors_contexte(l))
        if lectures:
            gardees.append(d if lectures == d.lectures else replace(d, lectures=lectures))
    return gardees


# --------------------------------------------------------------------------- #
# V4 (plan voix-et-communes): the town among the communes of a postal code said
# --------------------------------------------------------------------------- #

# Decision of Evan, 2026-09-17, on the sweep of that day (15 badly transcribed
# names of the benches; 68 sentences without a town x the 95 codes of the Oise):
# the best commune of the code must reach SEUIL_CODE and lead the next one by
# ECART_CODE. At 75/30: 11 names of 15 sure, +21 false sure towns (same message)
# and +14 (code at the turn before) on 6 460 sentences. At 60/20: 15 of 15, but
# +143 and +133. The other four stay to confirm, never wrong.
SEUIL_CODE = 75
ECART_CODE = 30
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
    *,
    avec_sons: bool = True,
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
    # ⛔ The switch cuts BOTH uses of the sounds: ``POIDS_ESP`` only ever cut
    # the one in ``analyser`` (review of 2026-09-17), and a measure with the
    # sounds "off" that still used them here would say nothing.
    prononces = sons(extraits) if base.esps and avec_sons else None

    meilleurs: dict[int, tuple[float, tuple[int, int]]] = {}
    for w, span in enumerate(spans):
        for j in indices:
            s = max(
                fuzz.ratio(sons_cles[w], base.sons[j]),
                fuzz.ratio(phons[w], base.phons[j]),
                fuzz.ratio(extraits[w], base.norms[j]),
                fuzz.ratio(base.cle_de_son(prononces[w]), base.esps_cles[j])
                if prononces is not None and base.esps[j] else 0.0,
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
