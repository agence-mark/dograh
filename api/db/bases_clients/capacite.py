"""[.mark] Mécanisme commun : la CAPACITÉ d'unités réservables sur des créneaux (module Restauration, lot 2).

Des unités (capacité min et max, assemblables deux à deux), des occupations (début, fin, effectif, unités prises ou
non affectées), des services (jours, heures, pas). Rend les débuts de créneau où l'effectif demandé tient. Aucune
lecture de l'heure ici : ``maintenant`` est fourni par l'appelant (source d'heure de l'organisation, D6).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from api.db.bases_clients.plages import heure


@dataclass(frozen=True)
class Unite:
    id: int
    capacite_min: int
    capacite_max: int
    assemblable_avec: frozenset[int] = frozenset()


@dataclass(frozen=True)
class Occupation:
    debut: datetime
    fin: datetime
    effectif: int
    unites: frozenset[int] = frozenset()   # vide : non affectée, elle consomme seulement la capacité totale


@dataclass(frozen=True)
class Service:
    nom: str
    jours: Sequence[int]
    debut: str
    fin: str
    pas_minutes: int


@dataclass(frozen=True)
class Regles:
    delai_minimal: int = 0
    jours_a_l_avance: int | None = None
    effectif_max: int | None = None
    effectif_max_par_creneau: int | None = None
    pause_jusqu_a: datetime | None = None
    fermetures: Sequence[tuple[datetime, datetime]] = field(default_factory=tuple)


def peut_accueillir(effectif: int, libres: Sequence[Unite], reste_sans_affectation: int) -> bool:
    """Une unité seule, ou deux unités assemblables, accueille l'effectif ; et la capacité totale restante suffit."""
    if reste_sans_affectation < effectif:
        return False
    for u in libres:
        if u.capacite_min <= effectif <= u.capacite_max:
            return True
    par_id = {u.id: u for u in libres}
    for u in libres:
        for autre_id in u.assemblable_avec:
            autre = par_id.get(autre_id)
            if autre is None or u.id >= autre.id:
                continue
            if min(u.capacite_min, autre.capacite_min) <= effectif <= u.capacite_max + autre.capacite_max:
                return True
    return False


def creneaux_libres(
    jour: date,
    effectif: int,
    duree_minutes: int,
    unites: Iterable[Unite],
    occupations: Iterable[Occupation],
    services: Iterable[Service],
    fuseau: ZoneInfo,
    maintenant: datetime,
    regles: Regles,
) -> list[dict]:
    """Les créneaux libres du jour, du plus tôt au plus tard : ``{debut, fin, service}``."""
    unites, occupations = list(unites), list(occupations)
    if regles.effectif_max is not None and effectif > regles.effectif_max:
        return []
    if regles.jours_a_l_avance is not None and jour > (maintenant.astimezone(fuseau) + timedelta(days=regles.jours_a_l_avance)).date():
        return []
    sortie = []
    for s in services:
        if jour.isoweekday() not in s.jours:
            continue
        courant = datetime.combine(jour, heure(s.debut), tzinfo=fuseau)
        fin_service = datetime.combine(jour, heure(s.fin), tzinfo=fuseau)
        while courant < fin_service:
            fin = courant + timedelta(minutes=duree_minutes)
            if _libre(courant, fin, effectif, unites, occupations, maintenant, regles):
                sortie.append({"debut": courant, "fin": fin, "service": s.nom})
            courant += timedelta(minutes=s.pas_minutes)
    return sorted(sortie, key=lambda c: c["debut"])


def _libre(debut, fin, effectif, unites, occupations, maintenant, regles) -> bool:
    if debut < maintenant + timedelta(minutes=regles.delai_minimal):
        return False
    if regles.pause_jusqu_a and debut < regles.pause_jusqu_a:
        return False
    if any(du < fin and debut < au for du, au in regles.fermetures):
        return False
    chevauche = [o for o in occupations if o.debut < fin and debut < o.fin]
    prises = set().union(*(o.unites for o in chevauche)) if chevauche else set()
    libres = [u for u in unites if u.id not in prises]
    sans_affectation = sum(o.effectif for o in chevauche if not o.unites)
    reste = sum(u.capacite_max for u in libres) - sans_affectation
    if regles.effectif_max_par_creneau is not None:
        deja = sum(o.effectif for o in occupations if o.debut == debut)
        if deja + effectif > regles.effectif_max_par_creneau:
            return False
    return peut_accueillir(effectif, libres, reste)
