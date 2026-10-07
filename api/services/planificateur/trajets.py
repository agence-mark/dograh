"""[.mark] Journeys and positions (chantier l-agent-collegue, L5, P5, P6, repli 7).

- ``duree_trajet_min`` is the ONE function that counts a journey: as the crow flies × a
  coefficient, at an average speed (both the client's settings). The only mode of this chantier;
  a road router (OSRM, decided at the 2nd or 3rd client) plugs in HERE, the planner unchanged.
- ``geocoder``: the position of an address by the Base Adresse Nationale (free, public, via the
  Géoplateforme), asked at the moment of the computation (repli 7: our street lists carry no
  position). Unreachable, unsure (score below ``SCORE_SUR``) or in another commune: None, and the
  journeys are not counted (said in the stamp). Kept a while in memory (the establishment's
  address is asked at every call); the caller's is written in ``adresse`` after the call (H6).
"""

from __future__ import annotations

import math
from collections import OrderedDict

import httpx
from loguru import logger

URL_BAN = "https://data.geopf.fr/geocodage/search"
SCORE_SUR = 0.6
DELAI_S = 1.5
Position = tuple[float, float]  # (latitude, longitude)

_MEMOIRE: OrderedDict[tuple[str, str | None], dict | None] = OrderedDict()
_MAX = 500


def nouveau_client(**options) -> httpx.AsyncClient:
    """The HTTP client of the geocoder (a test gives its stand-in here)."""
    return httpx.AsyncClient(**options)


def distance_km(a: Position, b: Position) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def duree_trajet_min(
    origine: Position, destination: Position, *, coefficient: float, vitesse_kmh: float
) -> int:
    """Minutes of a journey, rounded UP to 5 minutes (P5)."""
    minutes = distance_km(origine, destination) * coefficient / max(vitesse_kmh, 1) * 60
    return int(math.ceil(minutes / 5) * 5)


async def geocoder(texte: str | None, code_insee: str | None = None) -> dict | None:
    """``{latitude, longitude, label, score, code_insee}`` or None. Never raises."""
    texte = " ".join((texte or "").split())
    if len(texte) < 3:
        return None
    cle = (texte.casefold(), code_insee)
    if cle in _MEMOIRE:
        _MEMOIRE.move_to_end(cle)
        return _MEMOIRE[cle]
    params = {"q": texte[:200], "limit": 1, "index": "address"}
    if code_insee:
        params["citycode"] = code_insee
    try:
        async with nouveau_client(timeout=DELAI_S) as client:
            reponse = await client.get(URL_BAN, params=params)
        if reponse.status_code != 200:
            raise RuntimeError(f"HTTP {reponse.status_code}")
        caracteristiques = (reponse.json() or {}).get("features") or []
    except Exception as erreur:  # noqa: BLE001 -- never raises during a call: stamped and logged
        logger.warning(f"[.mark] Base Adresse Nationale unreachable, journeys not counted: {erreur!r}")
        return None  # not remembered: the next call tries again
    resultat = None
    if caracteristiques:
        f = caracteristiques[0]
        proprietes = f.get("properties") or {}
        coordonnees = (f.get("geometry") or {}).get("coordinates") or []
        score = float(proprietes.get("score") or 0)
        commune = proprietes.get("citycode")
        if (
            len(coordonnees) == 2
            and score >= SCORE_SUR
            and (code_insee is None or commune == code_insee)
        ):
            resultat = {
                "latitude": float(coordonnees[1]),
                "longitude": float(coordonnees[0]),
                "label": proprietes.get("label"),
                "score": round(score, 3),
                "code_insee": commune,
            }
    _MEMOIRE[cle] = resultat
    while len(_MEMOIRE) > _MAX:
        _MEMOIRE.popitem(last=False)
    return resultat


def oublier() -> None:
    """Tests only."""
    _MEMOIRE.clear()
