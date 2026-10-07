"""[.mark] The record checked at the end of the call (chantier l-agent-collegue, L7; plan
qualite-des-donnees, lot 3, QD1 to QD3, QD8; Q-2).

Pure: no database, no model. ``controler`` reads the record as the extraction left it and
returns a VERDICT next to it -- it never changes a value (QD8):

    {"statut": "complete" | "a_reprendre" | "non_controle",
     "problemes": [{"champ", "code", "valeur", "detail"}]}

| Check (field recognized by its NAME, QD1)                        | ``code``                          |
|------------------------------------------------------------------|-----------------------------------|
| Phone: 10 digits starting with 0 once normalised (+33 -> 0)      | ``telephone_invalide``            |
| Postcode: exists in the list of communes                         | ``code_postal_inconnu``           |
| Town and postcode both filled: the town carries that postcode    | ``commune_code_postal_incoherents`` |
| E-mail: syntax (``email-validator``, no network)                 | ``courriel_invalide``             |
| E-mail: domain close to a common one but not it (QD3)            | ``courriel_domaine_douteux``      |
| Date: readable, between the call -30 years and the call +2 years | ``date_invalide`` / ``date_improbable`` |
| Field of a step the call went through left empty (QD2)           | ``champ_vide``                    |

⛔ Never raises: a failure of the check gives ``non_controle`` and the record goes on.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from datetime import date, datetime

from loguru import logger

COMPLETE = "complete"
A_REPRENDRE = "a_reprendre"
NON_CONTROLE = "non_controle"

# QD3: the common domains (generic list, written once).
DOMAINES_COURANTS = (
    "gmail.com", "hotmail.fr", "hotmail.com", "outlook.fr", "outlook.com", "live.fr",
    "yahoo.fr", "yahoo.com", "orange.fr", "wanadoo.fr", "free.fr", "sfr.fr", "neuf.fr",
    "laposte.net", "icloud.com", "bbox.fr", "aol.com",
)
SEUIL_DOMAINE = 85.0
MOIS = {
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "decembre": 12, "décembre": 12,
}


def correspond(nom: str, motifs: Iterable[str]) -> bool:
    """QD1: the grammar of ``variables_commune``: a final ``*`` means « starts with »."""
    nom = (nom or "").strip().lower()
    for motif in motifs:
        motif = motif.strip().lower()
        if motif.endswith("*") and nom.startswith(motif[:-1]):
            return True
        if nom == motif:
            return True
    return False


def _probleme(champ: str, code: str, valeur, detail: str | None = None) -> dict:
    return {"champ": champ, "code": code, "valeur": None if valeur is None else str(valeur), "detail": detail}


def _telephone(champ: str, valeur: str) -> list[dict]:
    chiffres = re.sub(r"[^\d+]", "", valeur)
    if chiffres.startswith("+33"):
        chiffres = "0" + chiffres[3:]
    elif chiffres.startswith("0033"):
        chiffres = "0" + chiffres[4:]
    if re.fullmatch(r"0\d{9}", chiffres):
        return []
    n = len(re.sub(r"\D", "", chiffres))
    return [_probleme(champ, "telephone_invalide", valeur, f"{n} chiffres au lieu de 10")]


def _courriel(champ: str, valeur: str) -> list[dict]:
    from email_validator import EmailNotValidError, validate_email

    try:
        validate_email(valeur.strip(), check_deliverability=False)
    except EmailNotValidError as erreur:
        return [_probleme(champ, "courriel_invalide", valeur, str(erreur)[:120])]
    domaine = valeur.strip().rsplit("@", 1)[-1].lower()
    if domaine in DOMAINES_COURANTS:
        return []
    from rapidfuzz import fuzz

    proche = max(DOMAINES_COURANTS, key=lambda d: fuzz.ratio(domaine, d))
    if fuzz.ratio(domaine, proche) >= SEUIL_DOMAINE:
        return [_probleme(champ, "courriel_domaine_douteux", valeur, f"{domaine}, peut-être {proche}")]
    return []


def lire_date(valeur: str) -> date | None:
    """A date as the extraction writes it: ISO, dd/mm/yyyy, « octobre 2025 », « 2025 »."""
    texte = valeur.strip().lower()
    for forme in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m"):
        try:
            return datetime.strptime(texte[:10] if forme == "%Y-%m-%d" else texte, forme).date()
        except ValueError:
            continue
    m = re.fullmatch(r"(?:(\d{1,2})\s+)?([a-zéû]+)\s+(\d{4})", texte)
    if m and m.group(2) in MOIS:
        try:
            return date(int(m.group(3)), MOIS[m.group(2)], int(m.group(1) or 1))
        except ValueError:
            return None
    if re.fullmatch(r"(19|20)\d{2}", texte):
        return date(int(texte), 1, 1)
    return None


def _date(champ: str, valeur: str, jour_appel: date) -> list[dict]:
    lue = lire_date(valeur)
    if lue is None:
        return [_probleme(champ, "date_invalide", valeur)]
    if not (date(jour_appel.year - 30, jour_appel.month, 1) <= lue <= date(jour_appel.year + 2, 12, 31)):
        return [_probleme(champ, "date_improbable", valeur, lue.isoformat())]
    return []


def controler(
    fiche: dict,
    *,
    noms: dict[str, tuple[str, ...]],
    champs_attendus: Iterable[str] = (),
    jour_appel: date,
    base_communes=None,
    normaliser: Callable[[str], str] | None = None,
) -> dict:
    """The verdict. ``noms``: the recognised names by type (``telephone``, ``code_postal``,
    ``courriel``, ``date``, ``commune``); ``champs_attendus``: the fields of the steps the call
    went through (QD2). Never raises, never changes ``fiche``."""
    try:
        problemes: list[dict] = []
        remplis = {k: str(v).strip() for k, v in (fiche or {}).items() if v not in (None, "", [], {})}
        cps: list[tuple[str, str]] = []
        communes: list[tuple[str, str]] = []
        for champ, valeur in remplis.items():
            if correspond(champ, noms.get("telephone", ())):
                problemes += _telephone(champ, valeur)
            elif correspond(champ, noms.get("code_postal", ())):
                cp = re.sub(r"\D", "", valeur)
                cps.append((champ, cp))
                if base_communes is not None and (len(cp) != 5 or not base_communes.communes_du_code_postal(cp)):
                    problemes.append(_probleme(champ, "code_postal_inconnu", valeur))
            elif correspond(champ, noms.get("courriel", ())):
                problemes += _courriel(champ, valeur)
            elif correspond(champ, noms.get("date", ())):
                problemes += _date(champ, valeur, jour_appel)
            if correspond(champ, noms.get("commune", ())):
                communes.append((champ, valeur))
        if base_communes is not None and normaliser is not None and len(cps) == 1 and len(communes) == 1:
            (champ_cp, cp), (champ_commune, commune) = cps[0], communes[0]
            portees = base_communes.communes_du_code_postal(cp) if len(cp) == 5 else []
            # Only a value that IS a town's name (an address field is not compared: that is the
            # town check's work during the call).
            connue = bool(getattr(base_communes, "par_nom", {}).get(normaliser(commune)))
            if portees and connue and normaliser(commune) not in {normaliser(c.nom) for c in portees}:
                problemes.append(_probleme(champ_commune, "commune_code_postal_incoherents", commune, f"{commune} / {cp}"))
        for champ in dict.fromkeys(champs_attendus):
            if champ not in remplis:
                problemes.append(_probleme(champ, "champ_vide", None))
        return {"statut": A_REPRENDRE if problemes else COMPLETE, "problemes": problemes}
    except Exception as erreur:  # noqa: BLE001 -- QD8: never costs the record
        logger.warning(f"[.mark] Record not checked: {erreur!r}")
        return {"statut": NON_CONTROLE, "problemes": []}
