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
from api.services.nombres.mots import DIZAINES, MOTS_NOMBRE, UNITES

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

_UNITES = UNITES
_DIZAINES = DIZAINES


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
    # Also an ordinary number under five digits ("cent quatre-vingt", "quinze
    # cents", "soixante deux cents"): a postal code only with a context
    # (decision of Evan, 2026-09-16), decided by ``analyser_message``.
    ordinaire: bool = False

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
            # "mille ..." with nothing before it only opens a number (decision of
            # Evan, 2026-09-16): "deux mille" is not 2 | 1000 = 21000 (Dijon).
            if i > 0 and mots[i] == "mille":
                break
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


def _declencheur_reference(p: "_Phrase", i: int) -> bool:
    """Does word i announce a reference? "n'" elided is not "n°"; "bon" counts
    only in "bon de ..." or "bon numéro" (decision of Evan, 2026-09-16: "euh bon,
    Saint-Maximin soixante sept cent quarante" made the postal code a reference)."""
    m = p.mots[i]
    if m not in _AVANT_REFERENCE:
        return False
    if m == "n":
        return not p.elide(i)
    if m == "bon":
        suivant = p.mots[i + 1] if i + 1 < len(p.mots) and not p.coupure(i) else None
        return suivant in ("de", "d", "numero", "n")
    return True


_APRES_NUMERO_DE_VOIE = frozenset(
    """rue avenue av boulevard bd chemin allee impasse place route quai square residence
    lotissement cours passage sentier ruelle voie bis ter""".split()
)


def _forme_ordinaire(mots: tuple[str, ...]) -> bool:
    """Is this run also an ordinary number under five digits?"""
    v = _valeur(mots)
    if v is not None and v[0] < 10000:
        return True
    # "quinze cents", "onze cent dix": hundreds counted past ten.
    if "cent" in mots:
        k = mots.index("cent")
        x = _TABLE.get(" ".join(mots[:k]))
        y = _TABLE.get(" ".join(mots[k + 1:])) if k + 1 < len(mots) else 0
        return x is not None and 11 <= x <= 99 and y is not None and 0 <= y <= 99
    return False


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
            # "en somme" means "in short"; the department is said "dans la Somme".
            amorce = (avant[-1:] == ["en"] and nom != ("somme",)) or avant in (
                ["dans", "l"], ["dans", "le"], ["dans", "la"], ["dans", "les"]
            )
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
    # Words that name a department ("dans la Somme"): decision of Evan, 2026-09-16,
    # "somme" there is not an amount word.
    mots_departement = (
        {k for n in _departements_nommes(p, departements, set()) for k in range(n.debut, n.fin)}
        if departements
        else set()
    )

    for d0, f0 in suites:
        if d0 in absorbees:
            continue
        mots = tuple(p.mots[d0:f0])
        avant3 = p.avant(d0, 3)
        apres2 = p.apres(f0, 2)
        entendu = p.extrait(d0, f0)

        # 1. Phone ("plus trente-trois ..." takes its "plus").
        if _est_telephone(p, d0, f0):
            d = d0 - 1 if d0 > 0 and p.mots[d0 - 1] == "plus" and not p.coupure(d0 - 1) else d0
            lus.append(NombreLu(d, f0, p.extrait(d, f0), TELEPHONE, _alpha2digit(p.extrait(d, f0))))
            continue

        # 2. Amount.
        debut_avant = d0 - len(avant3)
        if (
            any(m in _APRES_MONTANT for m in apres2)
            or any(
                m in _AVANT_MONTANT and not (m == "somme" and debut_avant + k in mots_departement)
                for k, m in enumerate(avant3)
            )
            or avant3[-2:] in (["facture", "de"], ["devis", "de"])
        ):
            lus.append(NombreLu(d0, f0, entendu, MONTANT, _alpha2digit(entendu), montants=_montants(mots)))
            continue

        # 3. Reference.
        d, f, joint = _reference_etendue(p, d0, f0, suites)
        if (
            joint
            or any(_declencheur_reference(p, debut_avant + k) for k, m in enumerate(avant3))
            or (d0 > 0 and _lettre_isolee(p, d0 - 1) and not p.coupure(d0 - 1))
        ):
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
        # A house number is never a postal code: "au cent quatre-vingt rue …",
        # a comma between them too ("le cent quatre-vingt, rue des Lilas").
        numero_de_voie = not code_postal_dit and any(m in _APRES_NUMERO_DE_VOIE for m in p.mots[f0:f0 + 1])
        if (code_postal_dit or lectures) and not numero_de_voie:
            ecrit = lectures[0] if len(lectures) == 1 else _alpha2digit(entendu)
            lus.append(NombreLu(d0, f0, entendu, CODE_POSTAL, ecrit, lectures_cp=lectures,
                                lectures_cp_zero=lectures_zero,
                                ordinaire=not code_postal_dit and _forme_ordinaire(mots)))
            continue
        if numero_de_voie:
            lectures_zero = ()

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


# --------------------------------------------------------------------------- #
# Choosing a postal code between readings (N2), with the town analysis
# --------------------------------------------------------------------------- #

SURE = "sure"
A_CONFIRMER = "a_confirmer"

PAR_COMMUNE_DITE = "commune_dite"
PAR_TRACE = "trace_de_lappel"
PAR_DEPARTEMENT = "departement"
PAR_LECTURE_UNIQUE = "lecture_unique"
PAR_PROXIMITE = "proximite"


@dataclass(frozen=True)
class ChoixCodePostal:
    code: str | None
    statut: str  # SURE | A_CONFIRMER
    par: str  # which branch of N2 decided
    communes: tuple = ()  # Commune: the town identified, or the towns to propose
    detection: object | None = None  # branch ①: the town detection that carries the code


def _communes_de_la_trace(trace_appel, base) -> tuple[list, object | None]:
    """(towns proposed to confirm since the last sure one, the last sure town)."""
    derniere_sure = None
    en_attente: list = []
    for entree in trace_appel or []:
        if not isinstance(entree, dict) or entree.get("provisoire"):
            continue
        if entree.get("statut") == "sure" and entree.get("commune_retenue"):
            derniere_sure = base.commune(entree["commune_retenue"].get("code_insee") or "")
            en_attente = []
        elif entree.get("statut") == "a_confirmer" and not entree.get("code_postal_entendu"):
            # Proposals born of a postal code heard are not excluded from
            # everything, only from confirming that same code again (review of 2026-09-16).
            for proposition in entree.get("propositions") or []:
                commune = base.commune(proposition.get("code_insee") or "")
                if commune is not None:
                    en_attente.append(commune)
    return en_attente, derniere_sure


def _distance_au_magasin(cp: str, magasin, base) -> float:
    """Distance from the business to the nearest town of ``cp``, in km."""
    from api.services.communes.base import distance_km

    return min(distance_km(c, *magasin) for c in base.communes_du_code_postal(cp))


def choisir_code_postal(nombre, detections, trace_appel, departements, magasin, base) -> ChoixCodePostal:
    """N2, in order: ① a town said in the message that carries a reading;
    ② a town proposed to confirm earlier in the call, or the last town kept
    sure; ③ the department said; ④ a single reading exists. Sure in these four
    cases. Otherwise the reading nearest the business, TO CONFIRM.

    ⛔ Proximity alone never makes a code sure: Calais is 150 km from the shop,
    and a call from Calais is still possible. It can only withhold ②'s last sure
    town (decision of Evan, 2026-09-17).
    """
    from api.services.communes.analyse import SURE as COMMUNE_SURE

    lectures = list(nombre.lectures_cp)
    zero = [cp for cp in nombre.lectures_cp_zero if cp not in lectures]

    # ① A town said in this message, the nearest to the number first.
    def ecart(d) -> int:
        if d.debut < 0:
            return 10**6
        return min(abs(d.debut - nombre.fin), abs(nombre.debut - d.fin))

    for detection in sorted(detections, key=ecart):
        # A postal code heard is not a town said: it would confirm itself
        # ("soixante deux cents, soixante deux cents" made Compiègne sure).
        if getattr(detection, "code_postal_entendu", False):
            continue
        # A sure town is taken as it is: a lower reading never replaces it. A
        # town still to confirm is promoted only by a number with a SINGLE
        # reading: with two, any word near the number could carry the wrong one.
        if detection.statut == COMMUNE_SURE:
            candidates = detection.lectures[:1]
        else:
            # Decision of Evan, 2026-09-16: promoted only when ONE of its readings
            # carries the code and that name was heard almost exactly.
            porteuses = [l for l in detection.lectures if any(cp in l.commune.cps for cp in lectures + zero)]
            candidates = tuple(l for l in porteuses if l.nom_exact) if len(porteuses) == 1 else ()
        for lecture in candidates:
            communs = [cp for cp in lectures + zero if cp in lecture.commune.cps]
            if communs:
                return ChoixCodePostal(communs[0], SURE, PAR_COMMUNE_DITE, (lecture.commune,), detection)

    # ② The call so far: towns waiting for a confirmation, then the last sure one.
    # The leading-zero reading counts here as in ① (decision of Evan, 2026-09-16:
    # « Abbécourt » then « deux mille trois cents » is 02300, not Chenôve 21300).
    toutes = lectures + zero
    en_attente, derniere_sure = _communes_de_la_trace(trace_appel, base)
    portes: dict[str, list] = {}
    for commune in en_attente:
        for cp in commune.cps:
            if cp in toutes and commune not in portes.get(cp, []):
                portes.setdefault(cp, []).append(commune)
    # Sure only when ONE reading is carried, by ONE proposed town: three proposed
    # towns of 60120 do not make the first of them the caller's.
    if len(portes) == 1:
        ((cp, communes),) = portes.items()
        if len(communes) == 1:
            # Decision of Evan, 2026-09-16: the code is sure, the town is named
            # only if it is the code's only town ("chez mes parents" proposed
            # Esches, then "soixante cent dix": 60110 is also Méru).
            autres = tuple(c for c in base.communes_du_code_postal(cp) if c != communes[0])
            return ChoixCodePostal(cp, SURE, PAR_TRACE, (communes[0], *autres))
    if derniere_sure is not None:
        communs = [cp for cp in toutes if cp in derniere_sure.cps]
        if len(communs) == 1:
            # Named sure only if alone in its code, as for the proposed towns: a
            # town kept wrongly earlier ("à la campagne") must not spread to the code.
            autres = tuple(c for c in base.communes_du_code_postal(communs[0]) if c != derniere_sure)
            # Decision of Evan, 2026-09-17 (bench run 266): the town kept earlier
            # makes the code sure only if it carries the reading nearest the
            # business. "Clermont-Ferrand, soixante-trois mille" then "Senlis
            # (heard « cent lis »), soixante trois cents" made 63100 and
            # Clermont-Ferrand sure; 60300 is nearer, so both are proposed, the
            # town kept first. "Senlis" then "soixante trois cents" stays sure.
            # Without the business address there is nothing to compare: unchanged.
            if magasin and len(toutes) > 1:
                plus_proche = min(toutes, key=lambda cp: _distance_au_magasin(cp, magasin, base))
                if plus_proche != communs[0]:
                    return ChoixCodePostal(
                        communs[0],
                        A_CONFIRMER,
                        PAR_TRACE,
                        (derniere_sure, base.communes_du_code_postal(plus_proche)[0]),
                    )
            return ChoixCodePostal(communs[0], SURE, PAR_TRACE, (derniere_sure, *autres))

    if not lectures:
        return ChoixCodePostal(None, A_CONFIRMER, PAR_PROXIMITE)

    # ③ The department said.
    if departements:
        dans = [
            cp for cp in lectures
            if any(c.dep in departements for c in base.communes_du_code_postal(cp))
        ]
        if len(dans) == 1:
            return ChoixCodePostal(
                dans[0], SURE, PAR_DEPARTEMENT, tuple(base.communes_du_code_postal(dans[0]))
            )

    # ④ A single reading exists, the leading-zero one included.
    if len(lectures) == 1 and not zero:
        return ChoixCodePostal(
            lectures[0], SURE, PAR_LECTURE_UNIQUE, tuple(base.communes_du_code_postal(lectures[0]))
        )

    # Otherwise: the reading nearest the business first (the largest town first
    # without it), to confirm. Each reading is proposed as its largest town
    # ("Senlis", not the village of the same code that happens to be nearer).
    def cle(cp):
        if magasin:
            return _distance_au_magasin(cp, magasin, base)
        return -base.communes_du_code_postal(cp)[0].population

    ordonnees = sorted(lectures, key=cle)
    return ChoixCodePostal(
        ordonnees[0],
        A_CONFIRMER,
        PAR_PROXIMITE,
        tuple(base.communes_du_code_postal(cp)[0] for cp in ordonnees),
    )


@dataclass(frozen=True)
class LectureMessage:
    nombres: list[NombreLu]
    detections: list  # communes.analyse.Detection, as the model will be told
    choix: dict[int, ChoixCodePostal]  # keyed by NombreLu.debut

    @property
    def choix_cp(self) -> dict[int, str]:
        return {debut: c.code for debut, c in self.choix.items() if c.code}


# Spelling needed to take a town whose name carries a number word (0 to 100).
ORTHO_NOM_A_NOMBRE = 90


def _mots_de(nombres: Iterable[NombreLu]) -> set[int]:
    return {k for n in nombres for k in range(n.debut, n.fin)}


def _analyser_avec_noms_a_nombre(texte, base, magasin, spans, departements, mots_nombres, mots_autres):
    """The towns, the words of ordinary numbers excluded.

    Without them, 75 towns whose name carries a number word would never be
    found ("j'habite à Six-Fours-les-Plages"). They are taken from a second
    analysis only when the number word is spelled with the rest of the name,
    exactly: "le cinq rue des Lilas" never reads Cinqueux, "vers vingt heures"
    never Vervins.
    """
    from api.services.communes.analyse import MOTS_OUTILS, analyser

    detections = analyser(
        texte, base, magasin, codes_postaux=spans, departements=departements,
        mots_nombres=mots_nombres | mots_autres,
    )
    if not mots_autres:
        return detections
    mots = normaliser(texte).split()
    retenues = []
    for d in analyser(texte, base, magasin, codes_postaux=spans, departements=departements, mots_nombres=mots_nombres):
        positions = range(d.debut, d.fin)
        top = d.lectures[0]
        if not (
            any(k in mots_autres for k in positions)
            and any(k not in mots_autres and mots[k] not in MOTS_OUTILS for k in positions)
            and set(normaliser(top.commune.nom).split()) & set(MOTS_NOMBRE)
            and top.ortho >= ORTHO_NOM_A_NOMBRE
        ):
            continue
        detections = [x for x in detections if x.fin <= d.debut or x.debut >= d.fin]
        retenues.append(d)
    return sorted(detections + retenues, key=lambda x: x.debut) if retenues else detections


def _derniere_entree(trace) -> dict | None:
    for entree in reversed(trace or []):
        if isinstance(entree, dict) and not entree.get("provisoire"):
            return entree
    return None


def _debut_dun_nom_plus_proche(commune, base, magasin) -> bool:
    """« Pont » opens Pont-Sainte-Maxence; « Marseille » opens Marseille-en-Beauvaisis,
    nearer the shop than Marseille (13): said twice, it names none of them for sure
    (counter-review of 2026-09-17, 13 such towns within 60 km of the shop).
    Without the shop's location, any longer name opening on it is enough."""
    from api.services.communes.base import distance_km

    nom = normaliser(commune.nom)
    debut = nom + " "
    plus_longues = [base.communes[j] for j, n in enumerate(base.norms) if n.startswith(debut)]
    if not plus_longues:
        return False
    if magasin is None:
        return True
    ici = distance_km(commune, *magasin)
    return any(distance_km(c, *magasin) < ici for c in plus_longues)


_NEGATION = re.compile(r"\b(non|pas|ni|nan)\b")


def _repetition_tranche(texte, base, detections, trace_appel, magasin=None):
    """V8 (plan voix-et-communes): the caller repeats the name after a request
    for precision, the commune proposed first is kept.

    « Lyon » said three times stayed to confirm (run 264). When the last town
    check of the call asked for precision, and this message's best reading is
    the same commune again, it is sure.

    ⛔ Not when repeating brings nothing new (review of 2026-09-17): a name that
    several communes carry (« Saint-Just », « Beaumont » said twice made
    Saint-Just (34), Beaumont (63) sure), or a message that says no (« non,
    Angecourt » made Angicourt sure).
    ⛔ Decision of Evan, 2026-09-17: only for a name WRITTEN as the commune
    (« Lyon » twice is Lyon). A badly transcribed name is written the same way
    twice: « Bouvé » twice made Boves sure, the error of run 264. It stays to
    confirm, and the agent asks again with the postal code, which decides (V4).
    """
    from dataclasses import replace

    from api.services.communes.analyse import A_CONFIRMER as COMMUNE_A_CONFIRMER
    from api.services.communes.analyse import SURE as COMMUNE_SURE

    derniere = _derniere_entree(trace_appel)
    if (
        derniere is None
        or derniere.get("statut") != "a_confirmer"
        or derniere.get("code_postal_entendu")
        or not derniere.get("propositions")
    ):
        return detections
    en_tete = (derniere["propositions"][0] or {}).get("code_insee")
    if _NEGATION.search(normaliser(texte)):
        return detections

    def seule_de_son_nom(d) -> bool:
        nom = normaliser(d.lectures[0].commune.nom)
        ecrit_comme_la_commune = normaliser(d.entendu) == nom
        homonymes = len(base.par_nom.get(nom, [])) > 1
        return ecrit_comme_la_commune and not homonymes and not _debut_dun_nom_plus_proche(
            d.lectures[0].commune, base, magasin
        )

    return [
        replace(d, statut=COMMUNE_SURE)
        if d.statut == COMMUNE_A_CONFIRMER and not d.code_postal_entendu and d.lectures
        and d.lectures[0].commune.insee == en_tete and seule_de_son_nom(d)
        else d
        for d in detections
    ]


def _codes_retenus(trace_nombres) -> set[str]:
    """The postal code of the call's last number read as one: the code kept when
    sure, otherwise every reading (V4, a code said at an earlier turn)."""
    for entree in reversed(trace_nombres or []):
        if not isinstance(entree, dict) or entree.get("provisoire") or entree.get("type") != CODE_POSTAL:
            continue
        if entree.get("statut") == SURE and entree.get("retenu"):
            return {entree["retenu"]}
        return set(entree.get("lectures") or [])
    return set()


def _ville_par_code(texte, base, detections, candidats, mots_exclus, trace_appel, trace_nombres):
    """V4 (plan voix-et-communes), decision of Evan, 2026-09-17: a postal code
    known, the town is looked for among ITS communes, and sure when clearly ahead.

    Two ways a code is known:
    1. said in this message ("Bouvé, soixante mille");
    2. said at an earlier turn ("soixante mille", then "Bouvé"): the code of
       the call's last postal code read.
    ⛔ Not the town said at the turn BEFORE the code ("Bouvé", then "soixante
    mille"): decision of Evan, 2026-09-17, it stays to confirm as on 2026-09-16.
    Applied, « chez mes parents » then « soixante cent dix » made Esches sure
    (39 false sure towns on the sweep of the third review).
    The town found replaces the readings of the same words; a code is then
    chosen by N2 ① as for a town said.
    """
    from api.services.communes.analyse import ville_par_code
    from api.services.communes.analyse import SURE as COMMUNE_SURE

    codes_message = {cp for n in candidats for cp in n.lectures_cp + n.lectures_cp_zero}
    spans_codes = [(n.debut, n.fin) for n in candidats]
    trouvee = None
    if codes_message:
        codes = codes_message
        trouvee = ville_par_code(texte, base, codes_message, mots_exclus, spans_codes=spans_codes)
    else:
        codes = _codes_retenus(trace_nombres)
        if codes:
            trouvee = ville_par_code(texte, base, codes, mots_exclus)
    # A town SPELLED as said, that does not carry the code, is another place, in
    # both cases: "Arcueil" after 60100; "Chantilly 60230" is not Chambly, the name
    # is right and the code wrong or badly heard (review of 2026-09-17). A sound
    # alone is not enough ("Accueil" is Arcueil by its sound, and was Creil, run 264).
    if trouvee is not None and any(
        l.ortho >= ORTHO_NOM_A_NOMBRE and not set(l.commune.cps) & codes
        # The same words or more: « Lyon » inside « Lyon Court » is not the name said.
        for d in detections if d.debut <= trouvee.debut and d.fin >= trouvee.fin
        for l in d.lectures
    ):
        trouvee = None
    if trouvee is None:
        return detections
    gardees = [d for d in detections if d.fin <= trouvee.debut or d.debut >= trouvee.fin or d.debut < 0]
    return sorted([*gardees, trouvee], key=lambda d: d.debut)


def analyser_message(texte: str, base, magasin=None, trace_appel=None, etape_adresse: bool = True,
                     trace_nombres=None) -> LectureMessage:
    """The numbers and the towns of one message, read together. Blocking.

    The reader gives every existing postal-code reading; the town analysis runs
    once with all of them; N2 chooses. A postal code said without any town gets
    a town note of its own, built here (``code_postal_entendu``).

    At a step that collects a town (plan voix-et-communes): a name repeated
    after a request for precision is sure (V8), and a postal code known, in
    this message or the call's record ``trace_nombres``, decides the town
    among its communes (V4).
    """
    from dataclasses import replace

    from api.services.communes.analyse import A_CONFIRMER as COMMUNE_A_CONFIRMER
    from api.services.communes.analyse import SURE as COMMUNE_SURE
    from api.services.communes.analyse import Detection, Lecture, analyser, propositions_fondees

    nombres = lire_nombres(texte, base.par_cp, base.departements)
    departements = {n.departement for n in nombres if n.type == DEPARTEMENT and n.departement}

    def candidats_et_spans():
        cands = [n for n in nombres if n.type == CODE_POSTAL or (n.type == AUTRE and n.lectures_cp_zero)]
        sp: dict[str, list[tuple[int, int]]] = {}
        for n in cands:
            for cp in n.lectures_cp + n.lectures_cp_zero:
                sp.setdefault(cp, []).append((n.debut, n.fin))
        return cands, sp

    # Words of any number read, or of a fixed expression, are never a town
    # ("zéro six" was proposed as Clairoix at the address step, "mille mercis"
    # read Millay as sure, "c'est le cinq, rue des Lilas" read Cinqueux and
    # "vers vingt heures" Vervins). A town whose name carries a number word
    # (Six-Fours-les-Plages) is recovered below, when spelled out exactly.
    mots_nombres = {
        k for n in nombres if n.type != AUTRE for k in range(n.debut, n.fin)
    } | _positions_figees([j.mot for j in jetons(texte)])

    # Decision of Evan, 2026-09-16: outside a step that collects a town or an
    # address, an ordinary number ("quinze cents") is a postal code only when a
    # town said in the message or earlier in the call, or a department said,
    # carries one of its readings. Decided on an analysis without its readings.
    ordinaires = [n for n in nombres if n.type == CODE_POSTAL and n.ordinaire]
    if ordinaires and not etape_adresse:
        for n in ordinaires:
            nombres[nombres.index(n)] = replace(n, type=AUTRE)
        _, sp = candidats_et_spans()
        sans = _analyser_avec_noms_a_nombre(
            texte, base, magasin, sp, departements, mots_nombres, _mots_de(n for n in nombres if n.type == AUTRE)
        )
        for n in ordinaires:
            c = choisir_code_postal(n, sans, trace_appel, departements, magasin, base)
            i = [k for k, m in enumerate(nombres) if m.debut == n.debut][0]
            if c.par in (PAR_COMMUNE_DITE, PAR_TRACE, PAR_DEPARTEMENT):
                nombres[i] = n
            else:
                nombres[i] = replace(n, type=AUTRE, ecrit=_alpha2digit(n.entendu), lectures_cp=(),
                                     lectures_cp_zero=(), ordinaire=False)
    candidats, spans = candidats_et_spans()
    detections = _analyser_avec_noms_a_nombre(
        texte, base, magasin, spans, departements, mots_nombres, _mots_de(n for n in nombres if n.type == AUTRE)
    )
    if etape_adresse:
        detections = _repetition_tranche(texte, base, detections, trace_appel, magasin)
        detections = _ville_par_code(
            texte, base, detections, candidats, mots_nombres | _mots_de(nombres), trace_appel, trace_nombres
        )
    # A town said is one that will be proposed: a parasite dropped below must not
    # silence the note of a postal code said alone (« C'est la maison au bout du
    # chemin, soixante mille. », review of 2026-09-17).
    communes_dites = bool(propositions_fondees(texte, detections, base))
    choix: dict[int, ChoixCodePostal] = {}
    for n in candidats:
        c = choisir_code_postal(n, detections, trace_appel, departements, magasin, base)
        if n.type == AUTRE:
            # A 4-digit number is a postal code only when a town of that code is
            # said in the message, or earlier in the call (②).
            # Through the call's record (②) only at a step that collects a town:
            # otherwise "deux mille trois cents" would stay a code all call long.
            if not (c.par == PAR_COMMUNE_DITE or (c.par == PAR_TRACE and etape_adresse)):
                continue
            i = nombres.index(n)
            n = nombres[i] = replace(n, type=CODE_POSTAL, lectures_cp=n.lectures_cp_zero, ecrit=c.code)
        choix[n.debut] = c
        if c.detection is not None:
            d = c.detection
            retenue = next(l for l in d.lectures if l.commune == c.communes[0])
            autres = tuple(l for l in d.lectures if l is not retenue)
            detections[detections.index(d)] = replace(
                d, statut=COMMUNE_SURE, lectures=(retenue, *autres), codes_postaux_dits=frozenset({c.code})
            )
        elif c.code and (not communes_dites or c.statut == A_CONFIRMER):
            # Said alone, or uncertain next to a town that does not carry it
            # ("Beauvais soixante deux cents"): the model is told to ask.
            une_seule = c.statut == SURE and len(c.communes) == 1
            dits = frozenset({c.code}) if c.statut == SURE else frozenset(n.lectures_cp)
            # The same code said twice in a message gets one note, not two.
            if any(d.code_postal_entendu and d.codes_postaux_dits == dits for d in detections):
                continue
            detections.append(Detection(
                entendu=n.entendu,
                debut=n.debut,
                fin=n.fin,
                statut=COMMUNE_SURE if une_seule else COMMUNE_A_CONFIRMER,
                lectures=tuple(Lecture(commune, 0, 0, 0) for commune in c.communes[:5]),
                codes_postaux_dits=dits,
                code_postal_entendu=True,
            ))
    # Decision of Evan, 2026-09-17: no commune proposed on words that resemble it
    # badly. Last, so the postal codes above were chosen with every reading.
    detections = propositions_fondees(texte, detections, base)
    return LectureMessage(nombres=nombres, detections=detections, choix=choix)
