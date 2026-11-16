"""[.mark] Mécanisme commun : résoudre une date dite vers l'avenir (lot 6, T-26). Pur : l'instant vient de l'appelant, jamais de l'horloge ici.

« demain », « samedi », « samedi prochain », « le 24 », « le 24 décembre », « dans trois jours », « dans une semaine » : on rend UNE date quand le
texte n'en permet qu'une, sinon les candidats à confirmer. ⛔ Zéro faux sûr : « samedi » dit un samedi est aujourd'hui ou dans huit jours, « le 15 » dit
le 15 est aujourd'hui ou le mois prochain ; deux dates différentes dans le texte ; tout cela est ``AMBIGU``, jamais choisi en silence.

Contrairement à la résolution des dates relatives du passé (``workflow/dates_relatives``), tout est tourné vers l'avenir.
"""

from __future__ import annotations

import calendar
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from api.services.mots_dits import heure_en_lettres, nombre_en_lettres

RETENU = "RETENU"
AMBIGU = "AMBIGU"
INTROUVABLE = "INTROUVABLE"

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MOIS = (
    "janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
)
_MOIS_DITS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre")
_NOMBRES = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12,
    "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16, "vingt": 20, "trente": 30,
}
JOURS_MAX = 366


@dataclass(frozen=True)
class Resolution:
    statut: str  # RETENU | AMBIGU | INTROUVABLE
    jour: date | None = None
    candidats: tuple[date, ...] = field(default_factory=tuple)


def _normaliser(texte: str) -> str:
    sans_accent = "".join(c for c in unicodedata.normalize("NFKD", texte.lower()) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9/: ]", " ", sans_accent)).strip()


def jour_dit(jour: date) -> str:
    """« samedi quatorze novembre » : le jour de la semaine, le quantième en lettres (« premier » le 1er) et le mois."""
    quantieme = "premier" if jour.day == 1 else nombre_en_lettres(jour.day)
    return f"{JOURS[jour.weekday()]} {quantieme} {_MOIS_DITS[jour.month - 1]}"


def _en_chiffres(texte: str) -> str:
    """« le vingt-quatre décembre » devient « le 24 décembre » (les nombres dits en lettres, par la bibliothèque du projet)."""
    from text_to_num import alpha2digit

    return alpha2digit(texte.lower(), "fr")


def _nombre(mot: str) -> int | None:
    return int(mot) if mot.isdigit() else _NOMBRES.get(mot)


def _prochain_jour_de_la_semaine(aujourd_hui: date, voulu: int, *, strict: bool) -> date:
    ecart = (voulu - aujourd_hui.weekday()) % 7
    if strict and ecart == 0:
        ecart = 7
    return aujourd_hui + timedelta(days=ecart)


def _valide(annee: int, mois: int, quantieme: int) -> date | None:
    return date(annee, mois, quantieme) if 1 <= mois <= 12 and 1 <= quantieme <= calendar.monthrange(annee, mois)[1] else None


def _jour_du_mois(aujourd_hui: date, quantieme: int, mois: int | None) -> list[date]:
    """Les dates qui conviennent à « le <quantième> » (et le mois dit), à partir d'aujourd'hui. Un mois dit : la prochaine date valide (cette année ou une
    suivante, pour un 29 février). Sans mois : la prochaine date valide ; si c'est aujourd'hui même, la suivante est aussi proposée (à confirmer)."""
    if mois is not None:
        for annee in range(aujourd_hui.year, aujourd_hui.year + 6):
            d = _valide(annee, mois, quantieme)
            if d is not None and d >= aujourd_hui:
                return [d]
        return []
    trouvees: list[date] = []
    annee, m = aujourd_hui.year, aujourd_hui.month
    for _ in range(30):
        d = _valide(annee, m, quantieme)
        if d is not None and d >= aujourd_hui:
            trouvees.append(d)
            if d > aujourd_hui or len(trouvees) == 2:
                break
        annee, m = (annee + 1, 1) if m == 12 else (annee, m + 1)
    return trouvees[:2] if trouvees and trouvees[0] == aujourd_hui else trouvees[:1]


def resoudre_une_date(texte: str, maintenant: datetime) -> Resolution:
    """La date dite dans ``texte``, vue d'``maintenant`` (aware, déjà à l'heure du lieu). Voir l'en-tête du module."""
    if maintenant.tzinfo is None:
        raise ValueError("L'instant doit être aware.")
    aujourd_hui = maintenant.date()
    t = _normaliser(_en_chiffres(texte))
    if not t:
        return Resolution(INTROUVABLE)
    trouvees: list[tuple[date, ...]] = []  # chaque mention = ses dates possibles

    def mention(*jours: date) -> None:
        trouvees.append(tuple(jours))

    if re.search(r"\bapres demain\b", t):
        mention(aujourd_hui + timedelta(days=2))
        t = t.replace("apres demain", " ")
    if re.search(r"\bdemain\b", t):
        mention(aujourd_hui + timedelta(days=1))
    if re.search(r"\b(aujourd hui|aujourdhui|ce soir|ce midi|tout a l heure)\b", t):
        mention(aujourd_hui)
    for m in re.finditer(r"\bdans (\w+) (jour|jours|semaine|semaines)\b", t):
        n = _nombre(m.group(1))
        if n is not None and 0 < n <= JOURS_MAX:
            mention(aujourd_hui + timedelta(days=n * (7 if m.group(2).startswith("semaine") else 1)))
    for m in re.finditer(r"(?<!dans )\b(huit|8|quinze|15) jours\b", t):  # « dans huit jours » est lu plus haut ; seul, « huit jours » dit la même chose
        mention(aujourd_hui + timedelta(days=_nombre(m.group(1)) or 0))
    for numero, nom in enumerate(JOURS):
        for m in re.finditer(rf"\b{nom}( prochain| en (?:huit|8))?\b", t):
            suffixe = (m.group(1) or "").strip()
            premier = _prochain_jour_de_la_semaine(aujourd_hui, numero, strict=False)
            if suffixe.startswith("en "):
                mention(_prochain_jour_de_la_semaine(aujourd_hui, numero, strict=True) + timedelta(days=7) if premier == aujourd_hui else premier + timedelta(days=7))
            elif premier == aujourd_hui:
                mention(aujourd_hui, aujourd_hui + timedelta(days=7))  # le jour même : aujourd'hui ou dans huit jours
            elif suffixe == "prochain":
                mention(premier, premier + timedelta(days=7))  # « prochain » se dit des deux façons : on confirme
            else:
                mention(premier)
    mois_alternance = "|".join(MOIS)
    pris = False
    for m in re.finditer(rf"\b(?:le )?(\w+|1er) (?:de )?({mois_alternance})\b", t):
        q = 1 if m.group(1) == "1er" else _nombre(m.group(1))
        if q is not None:
            pris = True  # un mois est dit : le quantième ne se lit jamais seul (« le 30 février » n'est pas « le 30 »)
            if valides := _jour_du_mois(aujourd_hui, q, MOIS.index(m.group(2)) + 1):
                mention(*valides)
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})\b", t):
        if (valides := _jour_du_mois(aujourd_hui, int(m.group(1)), int(m.group(2)))) and 1 <= int(m.group(2)) <= 12:
            mention(*valides)
            pris = True
    if not pris:
        for m in re.finditer(r"\ble (\w+|1er)\b", t):
            q = 1 if m.group(1) == "1er" else _nombre(m.group(1))
            if q is not None and 1 <= q <= 31 and (valides := _jour_du_mois(aujourd_hui, q, None)):
                mention(*valides)
    if not trouvees:
        return Resolution(INTROUVABLE)
    ensembles = {tuple(sorted(j)) for j in trouvees}
    if len(ensembles) == 1:
        (jours,) = ensembles
        return Resolution(RETENU, jours[0], jours) if len(jours) == 1 else Resolution(AMBIGU, None, jours)
    tous = tuple(sorted({d for j in ensembles for d in j}))
    return Resolution(AMBIGU, None, tous)


@dataclass(frozen=True)
class HeureResolue:
    statut: str  # RETENU | AMBIGU | INTROUVABLE
    heure: time | None = None
    candidats: tuple[time, ...] = field(default_factory=tuple)


def heure_dite(heure: time) -> str:
    """« dix-neuf heures trente », « dix-neuf heures »."""
    return heure_en_lettres(heure.hour, heure.minute)


def resoudre_l_heure(texte: str) -> HeureResolue:
    """L'heure dite : « 19 h 30 », « sept heures et demie du soir », « midi », « 20 heures moins le quart ». ⛔ Zéro faux sûr : « sept heures » sans
    « du matin » ni « du soir » vaut sept ou dix-neuf heures, donc ``AMBIGU`` ; au-delà de douze, ou avec le moment dit, elle est sûre."""
    t = _normaliser(_en_chiffres(texte))
    if not t:
        return HeureResolue(INTROUVABLE)
    if re.search(r"\bmidi\b", t):
        return HeureResolue(RETENU, time(12, 0), (time(12, 0),))
    if re.search(r"\bminuit\b", t):
        return HeureResolue(RETENU, time(0, 0), (time(0, 0),))
    m = re.search(r"\b(\d{1,2}) ?(?:h|heures?|:) ?(\d{2})?\b(?: ?(et demie?|et quart|moins le quart|moins (\d{1,2})))?", t)
    if not m:
        return HeureResolue(INTROUVABLE)
    heures, minutes = int(m.group(1)), int(m.group(2) or 0)
    suite = m.group(3) or ""
    if suite.startswith("et dem"):
        minutes = 30
    elif suite == "et quart":
        minutes = 15
    elif suite == "moins le quart":
        heures, minutes = heures - 1, 45
    elif suite.startswith("moins"):
        heures, minutes = heures - 1, 60 - int(m.group(4))
    if not (0 <= heures <= 24 and 0 <= minutes < 60):
        return HeureResolue(INTROUVABLE)
    heures %= 24
    soir, matin = re.search(r"\b(du soir|de l apres midi|apres midi)\b", t), re.search(r"\bdu matin\b", t)
    if soir and 1 <= heures <= 11:
        heures += 12
    elif matin or heures >= 12 or heures == 0:
        pass
    else:
        deux = (time(heures, minutes), time(heures + 12, minutes))
        return HeureResolue(AMBIGU, None, deux)
    return HeureResolue(RETENU, time(heures, minutes), (time(heures, minutes),))


# --------------------------------------------------------------------------- #
# Le moment de la journée dit avec le jour (« demain soir ») est GARDÉ, puis lu avec l'heure dite ensuite (M85, appels 2570 et 2572).
# --------------------------------------------------------------------------- #

CLE_DU_MOMENT = "moment_du_jour"
_MOMENTS = (
    ("apres-midi", r"\bapres ?-?midi\b"), ("midi", r"\bmidi\b"), ("matin", r"\bmatin(?:ee)?\b"), ("soir", r"\bsoir(?:ee)?\b"),
)
_SUFFIXES = {"soir": "du soir", "matin": "du matin", "apres-midi": "de l apres midi"}


def moment_du_jour(texte: str | None) -> str | None:
    """Le moment de la journée dit dans ce texte : ``matin``, ``midi``, ``apres-midi``, ``soir`` (« ce soir », « demain matin »), ou ``None``."""
    t = _normaliser(texte or "")
    return next((nom for nom, motif in _MOMENTS if re.search(motif, t)), None)


def _jour_sans_le_moment(texte: str) -> str:
    t = _normaliser(texte)
    for _, motif in _MOMENTS:
        t = re.sub(motif, " ", t)
    return re.sub(r"\b(ce|cette|en)\b", " ", re.sub(r"\s+", " ", t)).strip()


def retenir_le_moment(etat: dict, jour: str | None) -> None:
    """Garde dans ``etat`` (panier, brouillon) le moment dit avec ce texte de jour. Un autre jour dit sans moment l'efface ; une heure seule (jour vide)
    ne touche à rien. Pur : ne résout rien."""
    if not jour or not jour.strip():
        return
    sans = _jour_sans_le_moment(jour)
    if (moment := moment_du_jour(jour)) is not None:
        etat[CLE_DU_MOMENT] = {"moment": moment, "jour": sans, "texte": jour.strip()}
    elif (garde := etat.get(CLE_DU_MOMENT)) and garde.get("jour") != sans:
        etat.pop(CLE_DU_MOMENT, None)


def heure_avec_le_moment(etat: dict, heure: str | None) -> str | None:
    """L'heure dite, complétée par le moment gardé : « huit heures et demie » + soir = « huit heures et demie du soir ». Un moment dit dans l'heure
    l'emporte ; sans moment gardé, ou sans nombre dans l'heure, rien n'est changé (le doute reste une question, jamais deviné)."""
    garde = etat.get(CLE_DU_MOMENT) or {}
    moment = garde.get("moment")
    if not heure or not moment or moment_du_jour(heure) is not None:
        return heure
    nombre = re.search(r"\d{1,2}", _normaliser(_en_chiffres(heure)))
    if nombre is None:
        return heure
    suffixe = _SUFFIXES.get(moment) or ("de l apres midi" if moment == "midi" and 1 <= int(nombre.group()) <= 4 else None)
    return f"{heure} {suffixe}" if suffixe else heure
