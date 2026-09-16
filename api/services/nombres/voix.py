"""[.mark] Write the numbers of the agent's answer in words, for the voice only.

Why this module exists
----------------------
Bench of 2026-09-17 (runs 264 and 265): the model writes "code postal 60550"
and Voxtral says "zéro six mille cent cinquante". The text is right, the
sound is wrong, and a caller can confirm a wrong postal code. Ten samples
listened to on the same voice (``fr_marie_neutral``): in digits, wrong; in
words, no defect. Best to the ear for a postal code: the short group,
"soixante, cinq cent cinquante".

Decisions of Evan, 2026-09-17 (plan voix-et-communes)
-----------------------------------------------------
- V1: numbers are written in words RIGHT BEFORE the voice. The chat, the
  transcript and the model keep the digits.
- V2: postal codes in a short group: department, then the last three digits
  as a number ("soixante, cent"); "soixante mille" when they are 000; leading
  zeros spelled ("zéro deux, deux cents", "soixante-quinze, zéro zéro un").
- V3: phones by pairs ("zéro six, douze, …"); amounts as said ("quinze mille
  euros"); references by groups, as written ("deux mille vingt-six, tiret,
  huit cent quarante-sept").

🔑 Which kind of number, first rule that applies (T3, same order as the
number reader ``lecture.py``): ① phone, ② amount, ③ reference, ④ postal
code, ⑤ anything else. "la référence 60300" is never read as a postal code.
Hours, dates, ordinals and percentages are said as they are read aloud.

Each rule rewrites its digits into words, so a later rule never sees them
again. Pure: no Pipecat, no I/O; the list of postal codes is passed in.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Container

# Spaces a model writes inside "15 000": plain, no-break, narrow no-break.
_ESPACE = "[ \u00a0\u202f]"
_MOIS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)


@lru_cache(maxsize=4096)
def _cardinal(n: int) -> str:
    # ⛔ Imported lazily: a dependency missing from the image must not stop
    # the API from starting. ``num2words`` is a dependency of Pipecat itself.
    from num2words import num2words

    return num2words(n, lang="fr")


def en_mots(chiffres: str) -> str:
    """Digits as written, leading zeros spelled: "0042" -> "zéro zéro quarante-deux"."""
    zeros = len(chiffres) - len(chiffres.lstrip("0"))
    if zeros == len(chiffres):
        return " ".join(["zéro"] * len(chiffres))
    reste = _cardinal(int(chiffres[zeros:]))
    return " ".join(["zéro"] * zeros + [reste])


def code_postal_en_mots(code: str) -> str:
    """V2, the short group: "60550" -> "soixante, cinq cent cinquante"."""
    departement, fin = code[:2], code[2:]
    if fin == "000":
        # The whole number: "quatre-vingt mille", not "quatre-vingts mille";
        # its leading zero spelled: "zéro six mille".
        return en_mots(code)
    return f"{en_mots(departement)}, {en_mots(fin)}"


def _par_paires(chiffres: str) -> str:
    return ", ".join(en_mots(chiffres[k:k + 2]) for k in range(0, len(chiffres), 2))


# --------------------------------------------------------------------------- #
# The rules, in order. Each one is (pattern, function of the match).
# --------------------------------------------------------------------------- #

# ① Phones. "+33 6 12 34 56 78", "+33 (0)6 …", "06 12 34 56 78", "0612345678".
_TELEPHONE_INTERNATIONAL = re.compile(
    rf"\+{_ESPACE}?33{_ESPACE}?(?:\(0\){_ESPACE}?)?(?P<premier>[1-9])(?P<reste>(?:[{_ESPACE[1:-1]}.\-]?\d{{2}}){{4}})(?!\d)"
)
_TELEPHONE = re.compile(rf"(?<![\d+])(?P<numero>0[1-9](?:[{_ESPACE[1:-1]}.\-]?\d{{2}}){{4}})(?!\d)")


def _telephone_international(m: re.Match) -> str:
    reste = re.sub(r"\D", "", m.group("reste"))
    return f"plus trente-trois, {en_mots(m.group('premier'))}, {_par_paires(reste)}"


def _telephone(m: re.Match) -> str:
    return _par_paires(re.sub(r"\D", "", m.group("numero")))


# Hours: "14h30", "9 h", "18h00".
_HEURE = re.compile(rf"(?<![\d,.])(?P<h>[01]?\d|2[0-3]){_ESPACE}?h{_ESPACE}?(?P<m>[0-5]\d)?(?![\w])")


def _heure(m: re.Match) -> str:
    h = int(m.group("h"))
    heures = _cardinal(h)
    heures = re.sub(r"\bun$", "une", heures)
    mots = f"{heures} {'heure' if h <= 1 else 'heures'}"
    minutes = m.group("m")
    if minutes and int(minutes):
        mots += f" {_cardinal(int(minutes))}"
    return mots


# Dates: "17/09", "1/10/2026". A "day/month" that is not a date is left to the references.
_DATE = re.compile(r"(?<![\d/])(?P<j>\d{1,2})/(?P<m>\d{1,2})(?:/(?P<a>\d{4}|\d{2}))?(?![\d/])")


def _date(m: re.Match) -> str:
    jour, mois = int(m.group("j")), int(m.group("m"))
    if not (1 <= jour <= 31 and 1 <= mois <= 12):
        return m.group(0)
    mots = f"{'premier' if jour == 1 else _cardinal(jour)} {_MOIS[mois - 1]}"
    annee = m.group("a")
    if annee:
        mots += f" {_cardinal(int(annee) if len(annee) == 4 else 2000 + int(annee))}"
    return mots


# ② Amounts. A number with its currency, a number with thousands spaces, or
# a number right after an amount word ("un montant de 15000").
_NOMBRE_MONTANT = rf"\d{{1,3}}(?:{_ESPACE}\d{{3}})+|\d+"
_MONTANT_DEVISE = re.compile(
    rf"(?<![\d,])(?P<valeur>{_NOMBRE_MONTANT})(?:,(?P<centimes>\d{{1,2}}))?{_ESPACE}?"
    rf"(?P<devise>€|euros?\b|EUR\b|centimes?\b)"
)
_MILLIERS = re.compile(rf"(?<![\d,])\d{{1,3}}(?:{_ESPACE}\d{{3}})+(?![\d])")
_MOTS_AVANT_MONTANT = (
    r"montant|prix|co[uû]t|co[uû]te|acompte|total|somme|budget|tarif|TTC|HT"
)
_APRES_MOT_MONTANT = re.compile(
    rf"(?P<avant>\b(?:{_MOTS_AVANT_MONTANT})\b(?:{_ESPACE}+(?:de|d'|du|est|:|total|:{_ESPACE}))*{_ESPACE}*:?{_ESPACE}*)"
    rf"(?P<valeur>\d+)(?![\d,/\-])",
    re.IGNORECASE,
)


def _valeur(texte: str) -> int:
    return int(re.sub(r"\D", "", texte))


def _montant_devise(m: re.Match) -> str:
    valeur = _valeur(m.group("valeur"))
    centimes = m.group("centimes")
    devise = m.group("devise").lower()
    if devise.startswith("centime"):
        return f"{_cardinal(valeur)} {'centime' if valeur <= 1 else 'centimes'}"
    if centimes:
        c = int(centimes.ljust(2, "0"))
        if valeur == 0:
            return f"{_cardinal(c)} {'centime' if c <= 1 else 'centimes'}"
        euros = f"{_cardinal(valeur)} {'euro' if valeur <= 1 else 'euros'}"
        return euros if c == 0 else f"{euros} {_cardinal(c)}"
    return f"{_cardinal(valeur)} {'euro' if valeur <= 1 else 'euros'}"


def _milliers(m: re.Match) -> str:
    return _cardinal(_valeur(m.group(0)))


def _apres_mot_montant(m: re.Match) -> str:
    return m.group("avant") + _cardinal(int(m.group("valeur")))


# ③ References. After a reference word ("la référence 12026-847", "devis
# n° D 2026 0042"), or by their form: letters glued to digits ("FA2026",
# "D-1001") or digit groups joined by a dash or a slash ("12026-847").
_GROUPE_REF = r"(?:[A-Z]{1,4}|[a-z](?![\wÀ-ÿ])|\d+)"
_SEPARATEUR_REF = rf"(?:{_ESPACE}?[\-/]{_ESPACE}?|{_ESPACE})"
_MOTS_REFERENCE = (
    r"r[ée]f[ée]rences?|r[ée]f\.?|factures?|devis|commandes?|dossiers?|contrats?"
    r"|bon de \w+|n°|num[ée]ro de (?:devis|facture|commande|dossier|contrat|client|r[ée]f[ée]rence)"
)
# ⛔ Case-insensitive on the reference WORD only: on the whole pattern,
# "[A-Z]{1,4}" also takes "du", "et", "mars" ("facture 1234 du 12 mars").
_REFERENCE_APRES_MOT = re.compile(
    rf"(?P<avant>\b(?i:{_MOTS_REFERENCE})(?:{_ESPACE}+(?i:client|de devis|de facture|de commande|n°|num[ée]ro))?"
    rf"{_ESPACE}*:?{_ESPACE}*)"
    rf"(?P<ref>(?:{_GROUPE_REF}{_SEPARATEUR_REF})*\d+(?:{_SEPARATEUR_REF}{_GROUPE_REF})*)(?![\w\-/])"
)
_REFERENCE_FORME = re.compile(
    r"(?<![\w\-/])(?P<ref>"
    r"[A-Za-z]{1,4}-?\d+(?:[\-/](?:[A-Za-z]{1,4}|\d+))*[A-Za-z]{0,4}"
    r"|\d+(?:[\-/](?:[A-Za-z]{1,4}|\d+))+"
    r")(?![\w\-/])"
)
_MORCEAU_REF = re.compile(r"[A-Za-z]+|\d+|[\-/]")


def _reference_en_mots(ref: str) -> str:
    mots: list[str] = []
    for morceau in _MORCEAU_REF.findall(ref):
        if morceau == "-":
            mots.append("tiret")
        elif morceau == "/":
            mots.append("slash")
        elif morceau.isdigit():
            mots.append(en_mots(morceau))
        else:
            mots.append(morceau)
    return ", ".join(mots)


def _reference_apres_mot(m: re.Match) -> str:
    # ⛔ The reference word itself may be matched case-insensitively, but the
    # letters of the reference keep their case ("f", "FA").
    return m.group("avant") + _reference_en_mots(m.group("ref"))


def _reference_forme(m: re.Match) -> str:
    return _reference_en_mots(m.group("ref"))


# ④ Postal codes: five digits after "code postal", between quotes or
# brackets, or that exist in the national list.
_CINQ_CHIFFRES = re.compile(r"(?<![\w,.])(?P<code>\d{5})(?![\w]|[,.]\d)")
_CODE_POSTAL_AVANT = re.compile(rf"code{_ESPACE}+postal(?:{_ESPACE}+(?:est|:))?{_ESPACE}*:?{_ESPACE}*[\"«(“]?{_ESPACE}*$", re.IGNORECASE)
_OUVRANTS = ("\"", "«", "(", "“")


def _est_code_postal(texte: str, m: re.Match, codes_postaux: Container[str] | None) -> bool:
    code = m.group("code")
    if _CODE_POSTAL_AVANT.search(texte[max(0, m.start() - 30):m.start()]):
        return True
    avant = texte[:m.start()].rstrip(" \u00a0\u202f")
    if avant.endswith(_OUVRANTS):
        return True
    return codes_postaux is not None and code in codes_postaux


# ⑤ Anything else.
_ORDINAL = re.compile(r"(?<![\w,.])(?P<n>\d+)(?P<suffixe>er|re|ère|e|ème|eme|è)(?![\wÀ-ÿ])")
_POURCENT = re.compile(rf"(?<![\w,.])(?P<n>\d+)(?:,(?P<d>\d+))?{_ESPACE}?%")
_DECIMAL = re.compile(r"(?<![\w,.])(?P<n>\d+),(?P<d>\d+)(?![\d,])")
# Groups of digits separated by one space, not thousands: said with a pause.
_GROUPES = re.compile(rf"(?<![\w,.])\d+(?:{_ESPACE}\d+)+(?![\w,.]\d)")
_ENTIER = re.compile(r"\d+")


def _ordinal(m: re.Match) -> str:
    n, suffixe = int(m.group("n")), m.group("suffixe")
    if n == 1:
        return "première" if suffixe in ("re", "ère") else "premier"
    from num2words import num2words

    return num2words(n, lang="fr", to="ordinal")


def _decimal_en_mots(entier: str, decimales: str) -> str:
    return f"{en_mots(entier)} virgule {en_mots(decimales)}"


def _pourcent(m: re.Match) -> str:
    n = en_mots(m.group("n")) if m.group("d") is None else _decimal_en_mots(m.group("n"), m.group("d"))
    return f"{n} pour cent"


def _groupes(m: re.Match) -> str:
    return ", ".join(en_mots(g) for g in re.split(_ESPACE, m.group(0)))


def _espace_autour(texte: str, debut: int, fin: int, mots: str) -> str:
    """Words glued to letters ("4G") would be read as one word."""
    if debut > 0 and texte[debut - 1].isalpha():
        mots = " " + mots
    if fin < len(texte) and texte[fin].isalpha():
        mots = mots + " "
    return mots


def _appliquer(motif: re.Pattern, fonction, texte: str) -> str:
    def remplacer(m: re.Match) -> str:
        return _espace_autour(texte, m.start(), m.end(), fonction(m))

    return motif.sub(remplacer, texte)


def ecrire_pour_la_voix(texte: str, codes_postaux: Container[str] | None = None) -> str:
    """``texte`` with every number written in words, as the voice must say it.

    ``codes_postaux``: the postal codes that exist (``base.par_cp``). Without
    it, five digits are a postal code only after "code postal" or between
    quotes or brackets. Text without a digit is returned as it is.
    """
    if not texte or not any(c.isdigit() for c in texte):
        return texte
    t = texte
    t = _appliquer(_TELEPHONE_INTERNATIONAL, _telephone_international, t)
    t = _appliquer(_TELEPHONE, _telephone, t)
    t = _appliquer(_HEURE, _heure, t)
    t = _appliquer(_DATE, _date, t)
    t = _appliquer(_MONTANT_DEVISE, _montant_devise, t)
    t = _appliquer(_MILLIERS, _milliers, t)
    t = _appliquer(_APRES_MOT_MONTANT, _apres_mot_montant, t)
    t = _appliquer(_REFERENCE_APRES_MOT, _reference_apres_mot, t)
    t = _appliquer(_REFERENCE_FORME, _reference_forme, t)
    courant = t
    t = _appliquer(
        _CINQ_CHIFFRES,
        lambda m: code_postal_en_mots(m.group("code")) if _est_code_postal(courant, m, codes_postaux) else m.group(0),
        t,
    )
    t = t.replace("n°", "numéro").replace("N°", "numéro")
    t = _appliquer(_ORDINAL, _ordinal, t)
    t = _appliquer(_POURCENT, _pourcent, t)
    t = _appliquer(_DECIMAL, lambda m: _decimal_en_mots(m.group("n"), m.group("d")), t)
    t = _appliquer(_GROUPES, _groupes, t)
    t = _appliquer(_ENTIER, lambda m: en_mots(m.group(0)), t)
    return t
