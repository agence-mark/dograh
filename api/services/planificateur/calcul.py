"""[.mark] The slots, computed (chantier l-agent-collegue, L5, P3 to P7, P10). Pure: no network,
no database; every input is given, so a corpus can pose the truth by hand (R7).

A slot of person P starting at T holds when:

1. T is on the grid (every ``pas_min`` from the start of an open range), at or after the first
   moment allowed (now + minimal notice) and before the horizon;
2. the appointment [T, T + length] lies inside one open range (the establishment's hours, or the
   planner's own ranges), on a day that is not a public holiday (P10);
3. the caller's wish accepts T (``Souhait.accepte``);
4. P's agenda is free on [T - margin before - journey, T + length + margin after + journey]
   (the journey counted only when it could be, P5, P6). The journey is one number both ways
   (``Candidat.trajet_min``, from the establishment), or -- R-6 -- what ``Candidat.trajets``
   says for THIS slot: from the previous appointment of P's agenda that day, to the next one,
   each falling back on the establishment. The slot keeps what was counted (``Creneau.trajets``).

The distribution (P7) orders the people:

- ``premier_libre``: the earliest slots; at each moment the first person free, in the team's order;
- ``tour_de_role``: the one with the fewest appointments of this type lately goes first; when
  he has nothing, the next takes -- and since nothing was given to him, he keeps his priority
  for the next call (fair over a series);
- ``charge``: the least busy over the horizon first;
- ``zone``: the nearest to the caller first.

Outside ``premier_libre``, the first person in that order gives his slots, then the next for what
is missing. Offers are spread: no offer starts inside another one (T to T + length).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from api.services.planificateur.feries import est_ferie
from api.services.planificateur.souhaits import Souhait

Intervalle = tuple[datetime, datetime]


@dataclass
class Trajets:
    """The journeys counted around ONE slot (R-6): minutes before and after, and for each side
    where it started from and why (``origine``, ``libelle``, ``pourquoi``: see ``action.py``)."""

    avant_min: int = 0
    apres_min: int = 0
    avant: dict = field(default_factory=dict)
    apres: dict = field(default_factory=dict)


@dataclass
class Candidat:
    cle: str
    prenom: str = ""
    agenda: str = ""
    occupe: list[Intervalle] = field(default_factory=list)
    trajet_min: int = 0  # one way from the establishment, 0 when journeys are not counted
    # R-6: the journeys of a slot [start, end] given the person's agenda; None = ``trajet_min`` both ways.
    trajets: Callable[[datetime, datetime], Trajets] | None = None
    distance_km: float | None = None
    attributions: int = 0
    charge_min: int = 0


@dataclass
class Creneau:
    debut: datetime
    fin: datetime
    cle: str
    rang: int  # place of the person in the order of distribution (1 = first)
    trajets: Trajets | None = None  # what was counted around it (only when ``Candidat.trajets`` is set)


@dataclass
class Regles:
    duree_min: int
    marge_avant_min: int = 0
    marge_apres_min: int = 0
    nombre: int = 3
    pas_min: int = 30
    repartition: str = "premier_libre"
    jours_feries: str = "metropole"


def ordonner(candidats: list[Candidat], repartition: str) -> list[Candidat]:
    """The order of distribution (P7). Ties keep the team's order (priority of the subject)."""
    rangs = {c.cle: i for i, c in enumerate(candidats)}
    if repartition == "tour_de_role":
        return sorted(candidats, key=lambda c: (c.attributions, rangs[c.cle]))
    if repartition == "charge":
        return sorted(candidats, key=lambda c: (c.charge_min, rangs[c.cle]))
    if repartition == "zone":
        return sorted(
            candidats,
            key=lambda c: (c.distance_km if c.distance_km is not None else float("inf"), rangs[c.cle]),
        )
    return list(candidats)


def _libre(occupe: list[Intervalle], debut: datetime, fin: datetime) -> bool:
    return not any(debut < b and fin > a for a, b in occupe)


def moments(ouvertures: list[Intervalle], regles: Regles, premier: datetime, horizon: datetime):
    """Every candidate start, in order: on the grid of each open range."""
    longueur = timedelta(minutes=regles.duree_min)
    pas = timedelta(minutes=regles.pas_min)
    feries: dict[date, bool] = {}
    for debut, fin in sorted(ouvertures):
        jour = debut.date()
        if jour not in feries:
            feries[jour] = est_ferie(jour, regles.jours_feries)
        if feries[jour]:
            continue
        t = debut
        if t < premier:
            sauts = -(-(premier - t) // pas)  # ceil
            t = t + sauts * pas
        while t + longueur <= fin and t < horizon:
            yield t
            t += pas


def calculer(
    candidats: list[Candidat],
    ouvertures: list[Intervalle],
    regles: Regles,
    souhait: Souhait,
    premier: datetime,
    horizon: datetime,
) -> list[Creneau]:
    ordre = ordonner(candidats, regles.repartition)
    longueur = timedelta(minutes=regles.duree_min)
    avant = timedelta(minutes=regles.marge_avant_min)
    apres = timedelta(minutes=regles.marge_apres_min)
    instants = [t for t in moments(ouvertures, regles, premier, horizon) if souhait.accepte(t)]

    def tient(c: Candidat, t: datetime) -> Trajets | None:
        """The journeys counted when P holds the slot, None when P does not."""
        if c.trajets is not None:
            compte = c.trajets(t, t + longueur)
        else:
            compte = Trajets(c.trajet_min, c.trajet_min)
        libre = _libre(
            c.occupe,
            t - avant - timedelta(minutes=compte.avant_min),
            t + longueur + apres + timedelta(minutes=compte.apres_min),
        )
        return compte if libre else None

    def retenu(c: Candidat, t: datetime, rang: int, compte: Trajets) -> Creneau:
        return Creneau(t, t + longueur, c.cle, rang, compte if c.trajets is not None else None)

    retenus: list[Creneau] = []
    if regles.repartition == "premier_libre":
        prochain = None
        for t in instants:
            if len(retenus) >= regles.nombre:
                break
            if prochain is not None and t < prochain:
                continue
            for rang, c in enumerate(ordre, start=1):
                compte = tient(c, t)
                if compte is not None:
                    retenus.append(retenu(c, t, rang, compte))
                    prochain = t + longueur
                    break
        return retenus

    for rang, c in enumerate(ordre, start=1):
        prochain = None
        for t in instants:
            if len(retenus) >= regles.nombre:
                break
            # Spread: never inside a slot already offered, whoever it is with.
            if (prochain is not None and t < prochain) or any(r.debut <= t < r.fin for r in retenus):
                continue
            compte = tient(c, t)
            if compte is not None:
                retenus.append(retenu(c, t, rang, compte))
                prochain = t + longueur
        if len(retenus) >= regles.nombre:
            break
    return sorted(retenus, key=lambda x: x.debut)
