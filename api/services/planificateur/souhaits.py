"""[.mark] The caller's wish, read by the code (chantier l-agent-collegue, L5, P4).

The model passes the caller's words (« plutôt mardi matin », « après 17 heures », « la semaine
prochaine ») in the parameter ``souhait``; THIS reads them, from a CLOSED list of phrasings, into
constraints on the start of a slot. Nothing is guessed: what is not on the list is not read, and
a wish where nothing was read is « not understood » -- the planner then offers the earliest slots
and tells the model so (P4).

Repli 6 of the plan (constat 6 of L0): a function of its own, called by the planner only;
``dates_relatives.py`` (the dates of the PAST) is not touched by one character.

The closed list (French, accents and case ignored):

- days: aujourd'hui, demain, après-demain, a day of the week (« mardi », « mardi prochain »,
  « ce mardi »: the NEXT one, today excluded), a date (« le 12 », « le 12 octobre », « 12/10 »),
  cette semaine, la semaine prochaine, ce week-end / le week-end, dans quinze jours ;
- moments: matin / matinée, en fin de matinée, tôt le matin, midi, après-midi, en début
  d'après-midi, en fin d'après-midi, fin de journée, soir / soirée ;
- hours: après / à partir de / passé H, avant H, vers / à H (one hour around), entre H et H ;
  H in digits (« 17h », « 17 h 30 », « 17:30 ») or in words up to « vingt ».
- no wish: le plus tôt possible, au plus vite, dès que possible, peu importe, n'importe quand ;
- negation: « pas / sauf » before a day or a moment EXCLUDES it (known red case: « pas le
  lundi » read as « lundi »).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MOIS = ("janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout",
        "septembre", "octobre", "novembre", "decembre")
NOMBRES = {
    "une": 1, "un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7,
    "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14,
    "quinze": 15, "seize": 16, "dix sept": 17, "dix huit": 18, "dix neuf": 19, "vingt": 20,
    "vingt et une": 21, "vingt deux": 22, "vingt trois": 23,
}
NEGATION = r"(?:pas|sauf|surtout pas|jamais|ni)(?: le| la| l| en| un| ce| dans la| dans l)?"


@dataclass
class Souhait:
    texte: str
    compris: bool
    jours: set[date] | None = None  # allowed days (None: any)
    jours_exclus: set[int] = field(default_factory=set)  # weekdays 0..6 excluded
    des_le: date | None = None  # not before this day
    heure_min: time | None = None  # the slot starts at or after
    heure_max: time | None = None  # the slot starts strictly before
    reconnu: list[str] = field(default_factory=list)

    def accepte(self, debut: datetime) -> bool:
        jour = debut.date()
        if self.jours is not None and jour not in self.jours:
            return False
        if debut.weekday() in self.jours_exclus:
            return False
        if self.des_le is not None and jour < self.des_le:
            return False
        heure = debut.timetz().replace(tzinfo=None)
        if self.heure_min is not None and heure < self.heure_min:
            return False
        return not (self.heure_max is not None and heure >= self.heure_max)

    def estampille(self) -> dict:
        return {
            "texte": self.texte,
            "compris": self.compris,
            "reconnu": list(self.reconnu),
            "jours": sorted(d.isoformat() for d in self.jours) if self.jours is not None else None,
            "jours_exclus": sorted(self.jours_exclus),
            "des_le": self.des_le.isoformat() if self.des_le else None,
            "heure_min": self.heure_min.strftime("%H:%M") if self.heure_min else None,
            "heure_max": self.heure_max.strftime("%H:%M") if self.heure_max else None,
        }


def _normaliser(texte: str) -> str:
    t = unicodedata.normalize("NFKD", (texte or "").casefold())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[’'`]", " ", t)
    t = re.sub(r"-", " ", t)
    t = re.sub(r"[^a-z0-9:/ ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_MOT_NOMBRE = "|".join(sorted((re.escape(k) for k in NOMBRES), key=len, reverse=True))
_HEURE = rf"(\d{{1,2}}|{_MOT_NOMBRE}|midi|minuit)(?:\s*(?:h|heures?|:)\s*(\d{{2}})?)?"


def _heure(brut: str, minutes: str | None) -> time | None:
    if brut == "midi":
        h = 12
    elif brut == "minuit":
        h = 0
    elif brut.isdigit():
        h = int(brut)
    else:
        h = NOMBRES.get(brut, -1)
    m = int(minutes) if minutes else 0
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return time(h, m)


def _plus(t: time, minutes: int) -> time:
    total = max(0, min(23 * 60 + 59, t.hour * 60 + t.minute + minutes))
    return time(total // 60, total % 60)


def _min(a: time | None, b: time) -> time:
    return b if a is None else min(a, b)


def _max(a: time | None, b: time) -> time:
    return b if a is None else max(a, b)


def _intersecter(souhait: Souhait, jours: set[date]) -> None:
    souhait.jours = set(jours) if souhait.jours is None else (souhait.jours & set(jours)) or set(jours)


def lire_souhait(texte: str | None, maintenant: datetime) -> Souhait:
    """The caller's wish read from the closed list. ``maintenant`` in the business's time."""
    brut = (texte or "").strip()
    souhait = Souhait(texte=brut[:200], compris=False)
    if not brut:
        souhait.compris = True  # no wish: nothing to read, nothing misunderstood
        return souhait
    t = f" {_normaliser(brut)} "
    aujourd_hui = maintenant.date()
    lus: list[str] = []

    def lu(motif: str) -> None:
        lus.append(motif)

    # --- no wish --------------------------------------------------------------------------
    if re.search(r" (le plus tot possible|au plus vite|des que possible|peu importe|n importe quand|quand vous voulez) ", t):
        lu("aucune contrainte")

    # --- negations first (they consume their words) --------------------------------------
    for i, nom in enumerate(JOURS):
        motif = rf" {NEGATION} {nom}s? "
        if re.search(motif, t):
            souhait.jours_exclus.add(i)
            t = re.sub(motif, " ", t)
            lu(f"pas {nom}")
    if re.search(rf" {NEGATION} matin(ee)? ", t):
        souhait.heure_min = _max(souhait.heure_min, time(12, 0))
        t = re.sub(rf" {NEGATION} matin(ee)? ", " ", t)
        lu("pas le matin")
    if re.search(rf" {NEGATION} apres midi ", t):
        souhait.heure_max = _min(souhait.heure_max, time(12, 0))
        t = re.sub(rf" {NEGATION} apres midi ", " ", t)
        lu("pas l'après-midi")

    # --- days ------------------------------------------------------------------------------
    if " apres demain " in t:
        _intersecter(souhait, {aujourd_hui + timedelta(days=2)})
        t = t.replace(" apres demain ", " ")
        lu("après-demain")
    if " demain " in t:
        _intersecter(souhait, {aujourd_hui + timedelta(days=1)})
        lu("demain")
    if re.search(r" (aujourd hui|aujourdhui|ce jour) ", t):
        _intersecter(souhait, {aujourd_hui})
        lu("aujourd'hui")
    for i, nom in enumerate(JOURS):
        if re.search(rf" {nom}s? ", t):
            ecart = (i - aujourd_hui.weekday()) % 7 or 7
            jour = aujourd_hui + timedelta(days=ecart)
            if re.search(rf" {nom} en huit ", t):
                jour += timedelta(days=7)
            _intersecter(souhait, {jour})
            lu(nom)
    m = re.search(rf" (?:le )?(\d{{1,2}}|1er|premier) ({'|'.join(MOIS)})(?: (\d{{4}}))? ", t)
    if m:
        jour = 1 if m.group(1) in ("1er", "premier") else int(m.group(1))
        mois = MOIS.index(m.group(2)) + 1
        annee = int(m.group(3)) if m.group(3) else aujourd_hui.year
        try:
            d = date(annee, mois, jour)
            if not m.group(3) and d < aujourd_hui:
                d = date(annee + 1, mois, jour)
            _intersecter(souhait, {d})
            lu(f"le {jour} {m.group(2)}")
        except ValueError:
            pass
    else:
        m = re.search(r" (\d{1,2})/(\d{1,2})(?:/(\d{2,4}))? ", t)
        m2 = None if m else re.search(r" le (\d{1,2}|1er) (?!h |heures? )", t)
        if m:
            annee = int(m.group(3)) if m.group(3) else aujourd_hui.year
            annee += 2000 if annee < 100 else 0
            try:
                d = date(annee, int(m.group(2)), int(m.group(1)))
                if not m.group(3) and d < aujourd_hui:
                    d = date(annee + 1, d.month, d.day)
                _intersecter(souhait, {d})
                lu(m.group(0).strip())
            except ValueError:
                pass
        elif m2:
            jour = 1 if m2.group(1) == "1er" else int(m2.group(1))
            annee, mois = aujourd_hui.year, aujourd_hui.month
            if jour < aujourd_hui.day:
                mois += 1
                if mois > 12:
                    annee, mois = annee + 1, 1
            try:
                _intersecter(souhait, {date(annee, mois, jour)})
                lu(f"le {jour}")
            except ValueError:
                pass
    lundi = aujourd_hui - timedelta(days=aujourd_hui.weekday())
    if re.search(r" (la |)semaine prochaine ", t):
        _intersecter(souhait, {lundi + timedelta(days=7 + k) for k in range(7)})
        lu("la semaine prochaine")
    elif re.search(r" cette semaine ", t):
        _intersecter(souhait, {aujourd_hui + timedelta(days=k) for k in range(7 - aujourd_hui.weekday())})
        lu("cette semaine")
    if re.search(r" (ce |le )?week ?end ", t):
        _intersecter(souhait, {lundi + timedelta(days=5), lundi + timedelta(days=6)} if aujourd_hui.weekday() < 6
                     else {aujourd_hui})
        lu("le week-end")
    if re.search(r" dans (quinze|15) jours ", t):
        souhait.des_le = aujourd_hui + timedelta(days=14)
        lu("dans quinze jours")

    # --- hours (before the moments: « après-midi » must not read « après midi » as an hour) --
    sans_moments = re.sub(r" apres midi ", " ", t)
    m = re.search(rf" entre {_HEURE} et {_HEURE} ", sans_moments)
    if m:
        a, b = _heure(m.group(1), m.group(2)), _heure(m.group(3), m.group(4))
        if a and b and a < b:
            souhait.heure_min, souhait.heure_max = _max(souhait.heure_min, a), _min(souhait.heure_max, b)
            lu(m.group(0).strip())
    else:
        for motif, sens in ((r"(?:apres|a partir de|passe|des)", "min"), (r"(?:avant|pas apres)", "max"),
                            (r"(?:vers|aux alentours de|a)", "vers")):
            for m in re.finditer(rf" {motif} {_HEURE}(?= )", sans_moments):
                h = _heure(m.group(1), m.group(2))
                # « à » alone needs a unit (« à 15 h »), never « à deux » or « à midi » read twice.
                if h is None or (sens == "vers" and m.group(0).strip().startswith("a ")
                                 and not re.search(r"(h|heures?|:)", m.group(0)) and m.group(1) != "midi"):
                    continue
                if sens == "min":
                    souhait.heure_min = _max(souhait.heure_min, h)
                elif sens == "max":
                    souhait.heure_max = _min(souhait.heure_max, h)
                else:
                    souhait.heure_min = _max(souhait.heure_min, _plus(h, -60))
                    souhait.heure_max = _min(souhait.heure_max, _plus(h, 61))
                lu(m.group(0).strip())
    # What was read as an hour is not read again as a moment (« avant midi »).
    for motif_lu in lus:
        t = t.replace(f" {motif_lu} ", " ")

    # --- moments of the day ----------------------------------------------------------------
    moments = (
        (r" (tot le matin|de bonne heure|a la premiere heure) ", None, time(10, 0), "tôt le matin"),
        (r" (en )?fin de matinee ", time(10, 30), time(12, 0), "fin de matinée"),
        (r" (en )?debut d apres midi ", time(12, 0), time(15, 0), "début d'après-midi"),
        (r" (en )?fin d apres midi ", time(16, 0), time(19, 0), "fin d'après-midi"),
        (r" (en )?fin de journee ", time(16, 30), None, "fin de journée"),
        (r" (le |en |dans la )?(soir|soiree) ", time(17, 0), None, "le soir"),
        (r" (le |en |dans la |dans l )?(matin|matinee)s? ", None, time(12, 0), "le matin"),
        (r" (l |en |dans l )?apres midi ", time(12, 0), None, "l'après-midi"),
        (r" (vers |a |autour de )?midi ", time(11, 30), time(14, 0), "midi"),
    )
    for motif, debut, fin, nom in moments:
        if re.search(motif, t):
            if debut:
                souhait.heure_min = _max(souhait.heure_min, debut)
            if fin:
                souhait.heure_max = _min(souhait.heure_max, fin)
            t = re.sub(motif, " ", t)
            lu(nom)

    if souhait.heure_min and souhait.heure_max and souhait.heure_min >= souhait.heure_max:
        # Contradictory (« le matin après 14 h »): not understood rather than impossible.
        return Souhait(texte=souhait.texte, compris=False, reconnu=lus)
    souhait.reconnu = lus
    souhait.compris = bool(lus)
    if not souhait.compris:
        return Souhait(texte=souhait.texte, compris=False)
    return souhait
