"""[.mark] Read the numbers a caller dictates, keeping every possible reading.

Why this module exists
----------------------
The bench of 2026-09-16 showed the town check never saw a postal code: said
in words, it did not look like five digits, and ``text2num`` picks ONE
reading, without context, often the wrong one. In the Oise, 60740 said
"soixante sept cent quarante" comes out 67140 (Barr); measured on every
postal code of the department said that way, ``text2num`` is wrong 69 % of
the time, and for 61 codes out of 94 both readings are real codes.

🔑 The principle: never freeze a reading when the diction is ambiguous.
Compute every reading, keep those that exist, decide by context (a town said,
a department said, the shop's location), otherwise have the caller confirm.

What it does
------------
1. Cuts the message into runs of number words ("suites").
2. Classifies each run, first rule that applies: phone, amount, reference,
   postal code, department, other. A run classified amount, reference or
   phone is NEVER a postal code (N6).
3. Computes what the model reads: ``text2num`` for everything, as the
   conversion did before this module, except postal codes (the code kept)
   and references (groups kept, "tiret" -> "-").

Pure: no Pipecat, no I/O. The list of postal codes and departments is passed
in. Measured at about 0.06 ms per sentence.

⛔ The rules below are those of the plan, word for word (section « Les règles
de lecture »). A change here changes what the model is told: the bench decides.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

from api.services.communes.base import normaliser

TELEPHONE = "telephone"
MONTANT = "montant"
REFERENCE = "reference"
CODE_POSTAL = "code_postal"
DEPARTEMENT = "departement"
AUTRE = "autre"

# Same separators as ``communes.analyse``: one original token = one word of
# ``normaliser(texte).split()``, so word positions mean the same in both.
_SEPARATEURS = "’'`\\-_/.,;:!?()\"«»\\s"
_JETON = re.compile(rf"[^{_SEPARATEURS}]+")
# Punctuation that ends a clause: a run, or a context window, never crosses it.
_PONCTUATION = re.compile(r"[.,;:!?()«»\"]")
_APOSTROPHES = "’'`"

_UNITES = (
    "zero un deux trois quatre cinq six sept huit neuf dix onze douze treize "
    "quatorze quinze seize"
).split()
_DIZAINES = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}
MOTS_NOMBRE = frozenset(_UNITES) | frozenset(_DIZAINES.values()) | {"cent", "mille"}


def _en_lettres_100(n: int) -> str:
    if n < 17:
        return _UNITES[n]
    if n < 20:
        return "dix " + _UNITES[n - 10]
    if n < 70:
        d, u = divmod(n, 10)
        return _DIZAINES[d] + ("" if u == 0 else (" et un" if u == 1 else " " + _UNITES[u]))
    if n < 80:
        return "soixante " + ("et onze" if n == 71 else _en_lettres_100(n - 60))
    return "quatre vingt" + ("" if n == 80 else " " + _en_lettres_100(n - 80))


def _en_lettres_1000(n: int) -> str:
    c, r = divmod(n, 100)
    if c == 0:
        return _en_lettres_100(r)
    t = "cent" if c == 1 else _UNITES[c] + " cent"
    return t if r == 0 else t + " " + _en_lettres_100(r)


# Every well-formed French number from 0 to 999, normalised ("quatre vingt dix").
_TABLE = {_en_lettres_1000(n): n for n in range(1000)}

# Fixed expressions left in words (N8): "tout neuf" is not 9.
_FIGEES = (
    ("remis", "a", "neuf"),
    ("quoi", "de", "neuf"),
    ("tout", "neuf"),
    ("du", "neuf"),
    ("mille", "mercis"),
    ("mille", "excuses"),
    ("mille", "fois"),
    ("a", "neuf"),
)
# "à neuf heures" IS a number: "a neuf" is fixed unless a unit or a number follows.
_UNITES_APRES_A_NEUF = frozenset(
    """heure heures h minute minutes an ans jour jours mois semaine semaines euro euros
    centime centimes km kilometre kilometres metre metres m pour degre degres
    personne personnes""".split()
)

_APRES_MONTANT = frozenset({"euro", "euros", "€", "centime", "centimes", "balles"})
_AVANT_MONTANT = frozenset(
    """montant prix cout coute coutait paye payer regle regler acompte total somme
    faisait eleve ttc ht""".split()
)
_AVANT_REFERENCE = frozenset(
    "numero n reference ref facture devis commande dossier bon contrat client".split()
)
_SEPARATEURS_REFERENCE = {"tiret": "-", "slash": "/", "barre": "/"}
_REMPLISSAGE = frozenset("oui non euh alors c est bah ben voila dans l le la les en ca".split())


@dataclass(frozen=True)
class Jeton:
    debut: int  # character offsets in the original text
    fin: int
    mot: str  # normalised


@dataclass(frozen=True)
class NombreLu:
    debut: int  # word positions [debut, fin), same as ``normaliser(texte).split()``
    fin: int
    entendu: str  # the original words
    type: str
    ecrit: str  # what the model reads when no postal code has been chosen
    lectures_cp: tuple[str, ...] = ()  # existing postal-code readings
    montants: tuple[int, ...] = ()  # usual reading first when two
    departement: str | None = None
    # 4-digit readings that exist with a leading zero ("mille deux cents" ->
    # 01200): usable only when a town carrying that code is said (plan).
    lectures_cp_zero: tuple[str, ...] = ()

    @property
    def montant_ambigu(self) -> bool:
        return len(self.montants) == 2


def _norm_mot(brut: str) -> str:
    m = normaliser(brut).replace(" ", "").replace("°", "")
    if m == "cents":
        return "cent"
    if m == "vingts":
        return "vingt"
    return m


def jetons(texte: str) -> list[Jeton]:
    return [Jeton(j.start(), j.end(), _norm_mot(j.group())) for j in _JETON.finditer(texte)]


def _alpha2digit(texte: str) -> str:
    # ⛔ Imported lazily, like the conversion always was: a dependency missing
    # from the image must not stop the API from starting.
    from text_to_num import alpha2digit

    return alpha2digit(texte, "fr")


@lru_cache(maxsize=4096)
def _chiffres_de(texte: str) -> str:
    return re.sub(r"\D", "", _alpha2digit(texte))


def _valeur(mots: tuple[str, ...]) -> tuple[int, str] | None:
    """(value, digits) of one well-formed group, or None."""
    if len(mots) == 1 and mots[0].isdigit():
        return int(mots[0]), mots[0]
    if any(m.isdigit() for m in mots):
        return None
    s = " ".join(mots)
    if s in _TABLE:
        return _TABLE[s], str(_TABLE[s])
    if "mille" in mots:
        i = mots.index("mille")
        a, b = mots[:i], mots[i + 1:]
        va = 1 if not a else _TABLE.get(" ".join(a))
        vb = 0 if not b else _TABLE.get(" ".join(b))
        if va is None or vb is None or (a and va < 2) or (b and vb == 0):
            return None
        v = va * 1000 + vb
        return v, str(v)
    return None


def _lectures_code_postal(mots: tuple[str, ...]) -> tuple[set[str], set[str]]:
    """(5-digit readings, 4-digit single-group readings with a leading zero).

    Every cut into 1 to 5 well-formed groups whose digits, end to end, make
    5 digits. Not filtered on the list of codes: the caller does it.
    """
    n = len(mots)
    cinq: set[str] = set()
    zero: set[str] = set()

    def parcourir(i: int, chiffres: str, groupes: int) -> None:
        if len(chiffres) > 5 or groupes > 5:
            return
        if i == n:
            if len(chiffres) == 5:
                cinq.add(chiffres)
            elif len(chiffres) == 4 and groupes == 1:
                zero.add("0" + chiffres)
            return
        # 12 words is the longest 5-digit number ("quatre vingt dix sept mille
        # neuf cent quatre vingt dix neuf" is 11).
        for j in range(i + 1, min(n, i + 12) + 1):
            v = _valeur(mots[i:j])
            if v is not None:
                parcourir(j, chiffres + v[1], groupes + 1)

    if n <= 20:
        parcourir(0, "", 0)
    return cinq, zero


def _montants(mots: tuple[str, ...]) -> tuple[int, ...]:
    """N3: "X mille Y" with Y a single digit said is 3 500 OR 3 005."""
    if "mille" in mots:
        i = mots.index("mille")
        a, b = mots[:i], mots[i + 1:]
        if len(b) == 1 and b[0] in _UNITES[1:10]:
            va = 1 if not a else _TABLE.get(" ".join(a))
            if va is not None and (not a or va >= 2):
                y = _UNITES.index(b[0])
                return (va * 1000 + y * 100, va * 1000 + y)
    v = _valeur(mots)
    return (v[0],) if v else ()


def _positions_figees(mots: list[str]) -> set[int]:
    figees: set[int] = set()
    i = 0
    while i < len(mots):
        for expression in _FIGEES:
            k = len(expression)
            if tuple(mots[i:i + k]) != expression:
                continue
            suivant = mots[i + k] if i + k < len(mots) else None
            if expression == ("a", "neuf") and suivant is not None and (
                suivant in _UNITES_APRES_A_NEUF or suivant in MOTS_NOMBRE or suivant.isdigit()
            ):
                continue
            figees.update(range(i, i + k))
            i += k - 1
            break
        i += 1
    return figees


class _Phrase:
    """The tokens of one message and the helpers the rules need."""

    def __init__(self, texte: str):
        self.texte = texte
        self.jetons = jetons(texte)
        self.mots = [j.mot for j in self.jetons]
        self.figees = _positions_figees(self.mots)

    def coupure(self, i: int) -> bool:
        """Is there clause punctuation between word i and word i + 1?"""
        if i < 0 or i + 1 >= len(self.jetons):
            return True
        return bool(_PONCTUATION.search(self.texte[self.jetons[i].fin:self.jetons[i + 1].debut]))

    def virgule_seule(self, i: int) -> bool:
        entre = self.texte[self.jetons[i].fin:self.jetons[i + 1].debut]
        return re.fullmatch(r"\s*,\s*", entre) is not None

    def elide(self, i: int) -> bool:
        fin = self.jetons[i].fin
        return self.texte[fin:fin + 1] in tuple(_APOSTROPHES) if fin < len(self.texte) else False

    def avant(self, debut: int, k: int) -> list[str]:
        """Up to k words before ``debut``, nearest last, not across punctuation."""
        res: list[str] = []
        i = debut - 1
        while i >= 0 and len(res) < k and not self.coupure(i):
            res.insert(0, self.mots[i])
            i -= 1
        return res

    def apres(self, fin: int, k: int) -> list[str]:
        res: list[str] = []
        i = fin
        while i < len(self.mots) and len(res) < k and not self.coupure(i - 1):
            res.append(self.mots[i])
            i += 1
        return res

    def extrait(self, debut: int, fin: int) -> str:
        return self.texte[self.jetons[debut].debut:self.jetons[fin - 1].fin]

    def est_nombre(self, i: int) -> bool:
        m = self.mots[i]
        return i not in self.figees and (m in MOTS_NOMBRE or m.isdigit())


def _suites(p: _Phrase) -> list[tuple[int, int]]:
    """Runs of number words, [debut, fin), not across punctuation."""
    suites: list[tuple[int, int]] = []
    i, n = 0, len(p.mots)
    while i < n:
        if not p.est_nombre(i):
            i += 1
            continue
        j = i + 1
        while j < n and not p.coupure(j - 1):
            if p.est_nombre(j):
                j += 1
            elif (
                p.mots[j] == "et"
                and j + 1 < n
                and not p.coupure(j)
                and p.est_nombre(j + 1)
                and not p.mots[j - 1].isdigit()
                and not p.mots[j + 1].isdigit()
            ):
                j += 2
            else:
                break
        if not (j - i == 1 and p.mots[i] == "un"):
            suites.append((i, j))
        i = j
    return suites


def _est_telephone(p: _Phrase, debut: int, fin: int) -> bool:
    # The original words: ``text2num`` does not know "zero" without its accent.
    chiffres = _chiffres_de(p.extrait(debut, fin))
    if len(chiffres) == 10 and chiffres.startswith("0"):
        return True
    return (
        debut > 0
        and p.mots[debut - 1] == "plus"
        and p.mots[debut:debut + 2] == ["trente", "trois"]
    )


def _telephones_regroupes(p: _Phrase, suites: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """A phone said with commas ("zéro trois, quarante-quatre, …") is ONE run;
    a run that ends on a phone ("soixante deux cents zéro six …") is cut."""
    coupees: list[tuple[int, int]] = []
    for d, f in suites:
        for k in range(d + 1, f):
            if p.mots[k] == "zero" and _est_telephone(p, k, f):
                coupees.extend([(d, k), (k, f)])
                break
        else:
            coupees.append((d, f))
    res: list[tuple[int, int]] = []
    i = 0
    while i < len(coupees):
        d, f = coupees[i]
        meilleur = i
        j = i
        while j + 1 < len(coupees) and coupees[j + 1][0] == coupees[j][1] and p.virgule_seule(coupees[j][1] - 1):
            j += 1
            if _est_telephone(p, d, coupees[j][1]):
                meilleur = j
        res.append((d, coupees[meilleur][1]))
        i = meilleur + 1
    return res


def _code_postal_avant(avant: list[str]) -> bool:
    return any(avant[k:k + 2] == ["code", "postal"] for k in range(len(avant) - 1))


def _departement_de(valeur: int, departements: dict[str, str] | None) -> str | None:
    if 1 <= valeur <= 95 or 971 <= valeur <= 976:
        code = f"{valeur:02d}"
        if departements is None or code in departements:
            return code
    return None


def _noms_departements(departements: dict[str, str]) -> list[tuple[tuple[str, ...], str]]:
    noms = [(tuple(normaliser(nom).split()), code) for code, nom in departements.items()]
    return sorted(noms, key=lambda x: -len(x[0]))


def _departements_nommes(
    p: _Phrase, departements: dict[str, str], occupes: set[int]
) -> list[NombreLu]:
    """Department names: "dans l'Oise", "en Seine-et-Marne", or the whole answer."""
    trouves: list[NombreLu] = []
    pris: set[int] = set(occupes)
    utiles = [k for k, m in enumerate(p.mots) if m not in _REMPLISSAGE]
    for nom, code in _noms_departements(departements):
        k = len(nom)
        for i in range(len(p.mots) - k + 1):
            if tuple(p.mots[i:i + k]) != nom or any(x in pris for x in range(i, i + k)):
                continue
            avant = p.avant(i, 2)
            amorce = avant[-1:] == ["en"] or avant in (["dans", "l"], ["dans", "le"], ["dans", "la"], ["dans", "les"])
            reponse_entiere = utiles == list(range(i, i + k))
            suivant = p.apres(i + k, 1)
            if not (amorce or reponse_entiere) or suivant in (["de"], ["des"], ["du"], ["d"]):
                continue
            pris.update(range(i, i + k))
            trouves.append(NombreLu(
                debut=i, fin=i + k, entendu=p.extrait(i, i + k), type=DEPARTEMENT,
                ecrit=p.extrait(i, i + k), departement=code,
            ))
    return trouves


def _reference_etendue(p: _Phrase, debut: int, fin: int, suites: list[tuple[int, int]]) -> tuple[int, int, bool]:
    """A reference takes the spoken letters before it ("D", "F A") and the runs
    joined to it by "tiret", "slash" or "barre". Returns (debut, fin, joined)."""
    joint = False
    departs = dict(suites)
    while fin < len(p.mots) and p.mots[fin] in _SEPARATEURS_REFERENCE and not p.coupure(fin - 1):
        joint = True
        if fin + 1 in departs and not p.coupure(fin):
            fin = departs[fin + 1]
        else:
            fin += 1
            break
    # Spelled letters, "a" and "y" included ("F A"), but not a leading "à".
    lettres = debut
    while lettres > 0 and _lettre_isolee(p, lettres - 1, a_et_y=True) and not p.coupure(lettres - 1):
        lettres -= 1
    while lettres < debut and p.mots[lettres] in ("a", "y"):
        lettres += 1
    return lettres, fin, joint


def _lettre_isolee(p: _Phrase, i: int, a_et_y: bool = False) -> bool:
    """A spelled letter ("D", "F"), not an elided article ("d'", "l'")."""
    m = p.mots[i]
    return (
        len(m) == 1 and m.isalpha() and (a_et_y or m not in ("a", "y")) and not p.elide(i)
    )


def _ecrire_reference(texte: str) -> str:
    ecrit = _alpha2digit(texte)
    for mot, signe in _SEPARATEURS_REFERENCE.items():
        ecrit = re.sub(rf"\s*\b{mot}\b\s*", signe, ecrit, flags=re.IGNORECASE)
    return ecrit


def lire_nombres(
    texte: str,
    codes_postaux_connus: Iterable[str] | None = None,
    departements: dict[str, str] | None = None,
) -> list[NombreLu]:
    """Every number of ``texte``, classified, in order.

    ``codes_postaux_connus``: the postal codes that exist (``base.par_cp``);
    None keeps every 5-digit reading. ``departements``: code -> name
    (``base.departements``), for "dans l'Oise"; None skips names.
    """
    if not texte:
        return []
    connus = codes_postaux_connus
    if connus is not None and not isinstance(connus, (set, frozenset, dict)):
        connus = set(connus)
    p = _Phrase(texte)
    suites = _telephones_regroupes(p, _suites(p))
    lus: list[NombreLu] = []
    absorbees: set[int] = set()

    for d0, f0 in suites:
        if d0 in absorbees:
            continue
        mots = tuple(p.mots[d0:f0])
        avant3 = p.avant(d0, 3)
        apres2 = p.apres(f0, 2)
        entendu = p.extrait(d0, f0)

        # 1. Phone.
        if _est_telephone(p, d0, f0):
            lus.append(NombreLu(d0, f0, entendu, TELEPHONE, _alpha2digit(entendu)))
            continue

        # 2. Amount.
        if (
            any(m in _APRES_MONTANT for m in apres2)
            or any(m in _AVANT_MONTANT for m in avant3)
            or avant3[-2:] in (["facture", "de"], ["devis", "de"])
        ):
            lus.append(NombreLu(d0, f0, entendu, MONTANT, _alpha2digit(entendu), montants=_montants(mots)))
            continue

        # 3. Reference.
        d, f, joint = _reference_etendue(p, d0, f0, suites)
        if joint or any(m in _AVANT_REFERENCE for m in avant3) or (d0 > 0 and _lettre_isolee(p, d0 - 1) and not p.coupure(d0 - 1)):
            absorbees.update(s for s, _ in suites if d0 < s < f)
            extrait = p.extrait(d, f)
            lus.append(NombreLu(d, f, extrait, REFERENCE, _ecrire_reference(extrait)))
            continue

        # 4. Postal code.
        cinq, zero = _lectures_code_postal(mots)
        code_postal_dit = _code_postal_avant(avant3)
        if code_postal_dit:
            cinq |= zero
        existe = (lambda cp: True) if connus is None else (lambda cp: cp in connus)
        lectures = tuple(sorted(cp for cp in cinq if existe(cp)))
        lectures_zero = tuple(sorted(cp for cp in zero if existe(cp) and cp not in lectures))
        if code_postal_dit or lectures:
            ecrit = lectures[0] if len(lectures) == 1 else _alpha2digit(entendu)
            lus.append(NombreLu(d0, f0, entendu, CODE_POSTAL, ecrit, lectures_cp=lectures,
                                lectures_cp_zero=lectures_zero))
            continue

        # 5. Department, by its number.
        valeur = _valeur(mots)
        dep = _departement_de(valeur[0], departements) if valeur else None
        avant2 = p.avant(d0, 2)
        if dep and (
            avant2 == ["dans", "le"]
            or avant2[-1:] == ["departement"]
            or avant2 in (["departement", "du"], ["departement", "de"])
        ):
            lus.append(NombreLu(d0, f0, entendu, DEPARTEMENT, _alpha2digit(entendu), departement=dep))
            continue

        # 6. Anything else.
        lus.append(NombreLu(d0, f0, entendu, AUTRE, _alpha2digit(entendu), lectures_cp_zero=lectures_zero))

    if departements:
        occupes = {k for n in lus for k in range(n.debut, n.fin)}
        lus.extend(_departements_nommes(p, departements, occupes))
    return sorted(lus, key=lambda n: n.debut)


def reecrire(texte: str, nombres: list[NombreLu], choix_cp: dict[int, str] | None = None) -> str:
    """What the model reads: ``text2num`` on everything, as the conversion did,
    except postal codes (the code chosen, keyed by ``debut``), references
    (groups kept) and fixed expressions (left in words)."""
    if not texte:
        return texte
    p = _Phrase(texte)
    choix_cp = choix_cp or {}
    remplaces: list[tuple[int, int, str]] = []
    for n in nombres:
        if n.type == CODE_POSTAL:
            ecrit = choix_cp.get(n.debut, n.ecrit)
        elif n.type == REFERENCE:
            ecrit = n.ecrit
        else:
            continue
        remplaces.append((p.jetons[n.debut].debut, p.jetons[n.fin - 1].fin, ecrit))
    for i in sorted(p.figees):
        j = p.jetons[i]
        remplaces.append((j.debut, j.fin, texte[j.debut:j.fin]))
    remplaces.sort()
    morceaux: list[str] = []
    curseur = 0
    for debut, fin, ecrit in remplaces:
        if debut < curseur:
            continue
        morceaux.append(_alpha2digit(texte[curseur:debut]) if debut > curseur else "")
        morceaux.append(ecrit)
        curseur = fin
    if curseur < len(texte):
        morceaux.append(_alpha2digit(texte[curseur:]))
    return "".join(morceaux)
