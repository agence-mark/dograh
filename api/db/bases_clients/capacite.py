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
    membres: frozenset[int] = frozenset()   # une unité RASSEMBLÉE (plan du soir) : les unités d'origine qu'elle réunit ; vide : une unité simple

    @property
    def ids(self) -> frozenset[int]:
        """Les identifiants qu'une occupation peut porter pour cette unité (elle-même, ou toutes celles qu'elle réunit)."""
        return self.membres or frozenset({self.id})


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
    # Plan du soir : des fenêtres ``(du, au, groupes)`` ; dans la fenêtre (``du`` inclus, ``au`` exclu), chaque groupe d'unités est UNE unité.
    plans_du_soir: Sequence[tuple[datetime, datetime, Sequence[Sequence[int]]]] = field(default_factory=tuple)


def rassembler(unites: Iterable[Unite], groupes: Iterable[Sequence[int]]) -> list[Unite]:
    """Le plan du soir : chaque groupe d'au moins deux unités PRÉSENTES devient une seule unité (identifiant = le plus petit des membres, couverts
    min = le plus petit, couverts max = la somme). Un groupe dont un membre manque (table retirée, désactivée) ou déjà pris par un autre groupe est
    ignoré. Rejouer sur le résultat ne change rien."""
    unites = list(unites)
    par_id = {u.id: u for u in unites}
    pris: set[int] = set()
    fusions: list[Unite] = []
    for groupe in groupes:
        ids = sorted(set(groupe))
        if len(ids) < 2 or any(i not in par_id or i in pris for i in ids):
            continue
        membres = [par_id[i] for i in ids]
        pris |= set(ids)
        fusions.append(
            Unite(ids[0], min(m.capacite_min for m in membres), sum(m.capacite_max for m in membres),
                  frozenset().union(*(m.assemblable_avec for m in membres)) - set(ids), frozenset(ids))
        )
    return [u for u in unites if u.id not in pris] + fusions


def unites_du_creneau(unites: Iterable[Unite], debut: datetime, regles: Regles) -> list[Unite]:
    """Les unités telles que le plan du soir les range à ``debut`` (sans plan qui couvre ce moment : telles quelles)."""
    unites = list(unites)
    for du, au, groupes in regles.plans_du_soir:
        if du <= debut < au:
            unites = rassembler(unites, groupes)
    return unites


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
    return _la_place_tient(debut, fin, effectif, unites, occupations, regles)


def _la_place_tient(debut, fin, effectif, unites, occupations, regles) -> bool:
    """La capacité seule : les unités encore libres sur le créneau, la capacité totale restante, le plafond par créneau."""
    unites = unites_du_creneau(unites, debut, regles)
    chevauche = [o for o in occupations if o.debut < fin and debut < o.fin]
    prises = set().union(*(o.unites for o in chevauche)) if chevauche else set()
    libres = [u for u in unites if not (u.ids & prises)]
    sans_affectation = sum(o.effectif for o in chevauche if not o.unites)
    reste = sum(u.capacite_max for u in libres) - sans_affectation
    if regles.effectif_max_par_creneau is not None:
        deja = sum(o.effectif for o in occupations if o.debut == debut)
        if deja + effectif > regles.effectif_max_par_creneau:
            return False
    return peut_accueillir(effectif, libres, reste)


# --------------------------------------------------------------------------- #
# Lot 8 : placer un effectif (attribution automatique d'unités), règles puis capacité, créneaux les plus proches
# --------------------------------------------------------------------------- #

PASSE = "passe"
TROP_TOT = "trop_tot"
TROP_LOIN = "trop_loin"
HORS_SERVICE = "hors_service"
GROUPE_TROP_GRAND = "groupe_trop_grand"
FERME = "ferme"
COMPLET = "complet"


def _convient_seule(u: Unite, effectif: int) -> bool:
    return u.capacite_min <= effectif <= u.capacite_max


def attribuer(effectif: int, libres: Sequence[Unite]) -> tuple[int, ...] | None:
    """Les unités à donner à ``effectif`` personnes parmi les ``libres`` : la plus juste (la plus petite capacité maximale qui convient,
    puis le plus petit identifiant), sinon la paire assemblable la plus juste ; ``None`` si aucune. Déterministe : même entrée, même sortie."""
    seules = sorted((u for u in libres if _convient_seule(u, effectif)), key=lambda u: (u.capacite_max, u.id))
    if seules:
        return (seules[0].id,)
    par_id = {u.id: u for u in libres}
    paires = []
    for u in libres:
        for autre_id in u.assemblable_avec:
            autre = par_id.get(autre_id)
            if autre is None or u.id >= autre.id:
                continue
            if min(u.capacite_min, autre.capacite_min) <= effectif <= u.capacite_max + autre.capacite_max:
                paires.append((u.capacite_max + autre.capacite_max, u.id, autre.id))
    if not paires:
        return None
    _, a, b = min(paires)
    return (a, b)


def unites_libres(debut: datetime, fin: datetime, unites: Iterable[Unite], occupations: Iterable[Occupation]) -> list[Unite]:
    """Les unités qu'aucune occupation ne prend sur ``[debut, fin[``."""
    prises: set[int] = set()
    for o in occupations:
        if o.debut < fin and debut < o.fin:
            prises |= set(o.unites)
    return [u for u in unites if not (u.ids & prises)]


def verifier_les_regles(
    debut: datetime, effectif: int, services: Iterable[Service], fuseau: ZoneInfo, maintenant: datetime, regles: Regles
) -> str | None:
    """Les règles AVANT la capacité : rend la raison fermée du premier défaut, ``None`` si le créneau est permis.
    Un début passé (ou plus proche que le délai minimal), un début hors de la grille d'un service (jour, heure, pas), un effectif trop
    grand, une pause ou une fermeture, un jour trop lointain."""
    if debut <= maintenant:
        return PASSE
    if debut < maintenant + timedelta(minutes=regles.delai_minimal):
        return TROP_TOT
    if regles.jours_a_l_avance is not None and debut.astimezone(fuseau).date() > (maintenant.astimezone(fuseau) + timedelta(days=regles.jours_a_l_avance)).date():
        return TROP_LOIN
    if regles.effectif_max is not None and effectif > regles.effectif_max:
        return GROUPE_TROP_GRAND
    local = debut.astimezone(fuseau)
    sur_la_grille = False
    for s in services:
        if local.isoweekday() not in s.jours:
            continue
        ouverture = datetime.combine(local.date(), heure(s.debut), tzinfo=fuseau)
        fermeture = datetime.combine(local.date(), heure(s.fin), tzinfo=fuseau)
        ecart = (local - ouverture).total_seconds() / 60
        if ouverture <= local < fermeture and ecart % s.pas_minutes == 0:
            sur_la_grille = True
            break
    if not sur_la_grille:
        return HORS_SERVICE
    if regles.pause_jusqu_a and debut < regles.pause_jusqu_a:
        return FERME
    return None


def placer(
    debut: datetime,
    duree_minutes: int,
    effectif: int,
    unites: Iterable[Unite],
    occupations: Iterable[Occupation],
    services: Iterable[Service],
    fuseau: ZoneInfo,
    maintenant: datetime,
    regles: Regles,
) -> tuple[str, tuple[int, ...]]:
    """Règles d'abord, puis capacité calculée depuis les occupations. Rend ``(raison, unites)`` : ``("ok", (ids…))`` — ``ids`` vide quand
    la place tient sans unité nommée (aucune unité déclarée) — ou ``(raison, ())`` avec ``raison`` dans ``PASSE``, ``TROP_TOT``, ``TROP_LOIN``,
    ``HORS_SERVICE``, ``GROUPE_TROP_GRAND``, ``FERME``, ``COMPLET``. Pour MODIFIER, l'appelant retire sa propre occupation de ``occupations`` :
    ses unités comptent alors comme libres."""
    unites, occupations = list(unites), list(occupations)
    raison = verifier_les_regles(debut, effectif, services, fuseau, maintenant, regles)
    if raison is not None:
        return raison, ()
    if any(du < debut + timedelta(minutes=duree_minutes) and debut < au for du, au in regles.fermetures):
        return FERME, ()
    fin = debut + timedelta(minutes=duree_minutes)
    if not _la_place_tient(debut, fin, effectif, unites, occupations, regles):
        return COMPLET, ()
    unites = unites_du_creneau(unites, debut, regles)
    libres = unites_libres(debut, fin, unites, occupations)
    attribuees = attribuer(effectif, libres)
    if attribuees is None:
        return "ok", ()
    par_id = {u.id: u for u in libres}
    # Une table rassemblée réserve TOUTES les tables qu'elle réunit.
    return "ok", tuple(sorted({i for a in attribuees for i in par_id[a].ids}))


def les_plus_proches(souhaite: datetime, creneaux: Sequence[dict], n: int = 3) -> list[dict]:
    """Au plus ``n`` créneaux libres, les plus proches de l'heure souhaitée (avant ou après), rendus dans l'ordre du temps.
    À égalité d'écart, le plus tôt gagne."""
    proches = sorted(creneaux, key=lambda c: (abs((c["debut"] - souhaite).total_seconds()), c["debut"]))[:n]
    return sorted(proches, key=lambda c: c["debut"])
