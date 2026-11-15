"""[.mark] Mécanisme commun : la zone d'un lieu parmi des zones réglées (lot 6, E-04, zéro faux sûr). Pur : ni base de données, ni réseau.

Une zone se règle de deux façons : une LISTE de communes (codes INSEE), ou un RAYON autour du centre de l'établissement. Une liste d'exclues
retire des communes de la zone, quelle que soit sa forme. Les zones sont lues par ordre : la première qui contient la commune gagne.

⛔ Zéro faux sûr : une commune dont on ne connaît pas les coordonnées n'est jamais « dans le rayon » ; un lieu entendu à confirmer, ou deux
communes différentes entendues, ne donnent jamais une zone : le verdict est « à confirmer », avec les candidats et la zone de chacun.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from api.services.communes.base import BaseCommunes, Commune, distance_km

RETENU = "RETENU"
HORS_ZONE = "HORS_ZONE"
AMBIGU = "AMBIGU"
INTROUVABLE = "INTROUVABLE"
CANDIDATS_MAX = 3


@dataclass(frozen=True)
class Zone:
    id: int
    nom: str
    forme: str  # "communes" | "rayon"
    communes: tuple[str, ...] = ()
    rayon_km: float | None = None
    exclues: tuple[str, ...] = ()
    ordre: int = 0


@dataclass(frozen=True)
class Candidat:
    commune: Commune
    zone: Zone | None  # None : hors de toute zone


@dataclass(frozen=True)
class Verdict:
    statut: str  # RETENU | HORS_ZONE | AMBIGU | INTROUVABLE
    commune: Commune | None = None
    zone: Zone | None = None
    candidats: tuple[Candidat, ...] = field(default_factory=tuple)


def communes_autour(base: BaseCommunes, lon: float, lat: float, rayon_km: float) -> list[Commune]:
    """Les communes dont le centre est à ``rayon_km`` ou moins du point, les plus proches d'abord. Sans coordonnées : jamais."""
    trouvees = [(distance_km(c, lon, lat), c) for c in base.communes if c.lon is not None and c.lat is not None]
    return [c for d, c in sorted(trouvees, key=lambda t: t[0]) if d <= rayon_km]


def commune_dans_la_zone(zone: Zone, commune: Commune, centre: tuple[float, float] | None) -> bool:
    if commune.insee in zone.exclues:
        return False
    if zone.forme == "communes":
        return commune.insee in zone.communes
    if zone.forme == "rayon" and zone.rayon_km is not None and centre is not None:
        return distance_km(commune, centre[0], centre[1]) <= zone.rayon_km
    return False


def zone_de_la_commune(zones: Sequence[Zone], commune: Commune, centre: tuple[float, float] | None) -> Zone | None:
    for zone in sorted(zones, key=lambda z: (z.ordre, z.id)):
        if commune_dans_la_zone(zone, commune, centre):
            return zone
    return None


def verdict_de_l_adresse(zones: Sequence[Zone], detections: Sequence, centre: tuple[float, float] | None, sure: str) -> Verdict:
    """Le verdict pour les communes détectées dans l'adresse (``detections`` : ce que rend ``communes.analyse.analyser``, ``sure`` : son statut sûr).

    - aucune commune entendue : ``INTROUVABLE`` ;
    - une seule détection, sûre : ``RETENU`` (sa zone) ou ``HORS_ZONE`` ;
    - tout le reste (à confirmer, ou plusieurs communes différentes) : ``AMBIGU``, jamais une zone.
    """
    if not detections:
        return Verdict(INTROUVABLE)
    sures = [d for d in detections if d.statut == sure and d.lectures]
    if len(detections) == 1 and len(sures) == 1:
        commune = sures[0].lectures[0].commune
        zone = zone_de_la_commune(zones, commune, centre)
        return Verdict(RETENU if zone else HORS_ZONE, commune, zone)
    vus: dict[str, Candidat] = {}
    for d in detections:
        for lecture in d.lectures[:CANDIDATS_MAX]:
            vus.setdefault(lecture.commune.insee, Candidat(lecture.commune, zone_de_la_commune(zones, lecture.commune, centre)))
    return Verdict(AMBIGU, candidats=tuple(list(vus.values())[:CANDIDATS_MAX]))
