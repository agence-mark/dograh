"""[.mark] The national list of French communes, with its sound keys.

Why this module exists
----------------------
On 2026-09-15 and 2026-09-16 a caller said "Beauvais" and the transcription
wrote "Beauvet", then "Bovet". A keyword list per shop does not carry over to
the next client, so the town is recognised against the national list instead,
the same for every organization (see ``analyse.py``).

The data
--------
``api/assets/communes/communes-AAAA-MM.json.gz``, produced by
``api/scripts/mark/generer_base_communes.py`` from the API Géo
(geo.api.gouv.fr: INSEE COG, La Poste postal codes, population; Licence
Ouverte). Current communes only: no former communes, no La Poste place names
(the 2026-09-16 trial measured more false detections with them).

🔑 The sound keys are computed ONCE, by the script, and stored in the file.
Computing them at start-up costs about 7 seconds; reading them back, a
fraction of that. ⛔ Change ``_son_mot`` or ``normaliser`` and the file must be
regenerated: ``test_base_communes.py`` compares stored and recomputed keys.

⛔ Loaded once per process, never on the event loop: ``obtenir_base`` reads
the file in a worker thread, so the audio is never held while it loads.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import math
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# Same folder as ``APP_ROOT_DIR / "assets"``, computed here: ``api.constants``
# requires DATABASE_URL at import, which the generation script does not have.
DOSSIER_BASE = Path(__file__).resolve().parents[2] / "assets" / "communes"
# ⛔ Named explicitly, not "the newest file in the folder": which list a call
# ran on must be readable in the code. Regenerating = new file + this constant.
FICHIER_BASE = DOSSIER_BASE / "communes-2026-09-v2.json.gz"

# Bumped whenever normaliser / cle_phonetique / cle_sonore / the sounds change
# meaning. 2 (2026-09-17): the espeak-ng sounds added (``sons.py``, V5).
VERSION_CLES = 2


def normaliser(texte: str) -> str:
    """Lower case, no accents, punctuation to spaces, "st"/"ste" spelled out."""
    t = unicodedata.normalize("NFKD", texte.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("œ", "oe").replace("æ", "ae")
    t = re.sub(r"[’'`\-_/.,;:!?()\"«»]", " ", t)
    t = re.sub(r"\bste\b", "sainte", t)
    t = re.sub(r"\bst\b", "saint", t)
    return re.sub(r"\s+", " ", t).strip()


def cle_phonetique(norm: str) -> str:
    """``phonetic_fr`` key, words glued: "beau vais" and "beauvais" match."""
    # Imported lazily, like ``text_to_num`` in ``conversion_nombres.py``: a
    # dependency missing from the image must not stop the API from starting.
    from phonetic_fr import phonetic

    return "".join(phonetic(m) for m in norm.split() if m)


def _son_mot(m: str) -> str:
    """Home-made sound key of one normalised word (2026-09-16 trial, v2).

    Catches what ``phonetic_fr`` misses on town names: "beauvet" and
    "beauvais" end on the same sound.
    """
    m = re.sub(r"[^a-z]", "", m)
    if not m:
        return ""
    r = m
    r = re.sub(r"(?<=[eu])x$", "", r)
    r = r.replace("sch", "ch").replace("ph", "f").replace("qu", "k").replace("ck", "k")
    r = r.replace("ch", "§")
    r = re.sub(r"eau|au", "o", r)
    r = re.sub(r"gu(?=[eiy])", "g", r)
    r = re.sub(r"g(?=[eiy])", "j", r)
    r = re.sub(r"ge(?=[aou])", "j", r)
    r = re.sub(r"c(?=[eiy])", "s", r)
    r = r.replace("c", "k").replace("w", "v").replace("x", "ks").replace("y", "i")
    r = re.sub(r"(?<![ks])h", "", r)
    r = re.sub(r"(?<=[aeiou])ill", "i", r)
    r = re.sub(r"ll", "l", r)
    r = re.sub(r"gn", "ni", r)
    r = re.sub(r"(ais|ait|aix|ay|ey|ei|ai|et|ez|er|es)$", "e", r)
    r = re.sub(r"ai|ei", "e", r)
    r = re.sub(r"(en|em|an|am)(?![aeiouy nm])", "an", r)
    r = re.sub(r"(ain|ein|in|im|un|um|yn)(?![aeiouy nm])", "in", r)
    r = re.sub(r"(on|om)(?![aeiouy nm])", "on", r)
    r = re.sub(r"(.)\1+", r"\1", r)
    r = re.sub(r"(?<=[aeiou])[stdxz]$", "", r)
    r = re.sub(r"(?<=[nr])[stdxz]$", "", r)
    r = re.sub(r"(?<=.)e$", "", r)
    return r.replace("§", "ch")


def cle_sonore(norm: str) -> str:
    return "".join(_son_mot(m) for m in norm.split())


@dataclass(frozen=True)
class Commune:
    insee: str
    nom: str
    cps: tuple[str, ...]
    population: int
    dep: str
    lon: float | None
    lat: float | None


@dataclass
class BaseCommunes:
    communes: list[Commune]
    norms: list[str]
    phons: list[str]
    sons: list[str]
    departements: dict[str, str]
    entete: dict
    # espeak-ng sounds (``sons.py``); "" for a commune without them.
    esps: list[str] = field(default_factory=list)
    par_cp: dict[str, list[int]] = field(default_factory=dict)
    par_insee: dict[str, int] = field(default_factory=dict)
    # Communes by normalised name: « Saint-Just » is carried by 12 of them.
    par_nom: dict[str, list[int]] = field(default_factory=dict)

    # The sounds with one plain character per sound: rapidfuzz compares
    # one-byte strings about a third faster than the phonetic alphabet.
    esps_cles: list[str] = field(default_factory=list)
    _table_sons: dict[int, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for i, c in enumerate(self.communes):
            self.par_insee[c.insee] = i
            self.par_nom.setdefault(self.norms[i], []).append(i)
            for cp in c.cps:
                self.par_cp.setdefault(cp, []).append(i)
        caracteres = sorted(set("".join(self.esps)))
        # From "!" upwards; a sound never met in the list keeps its own character.
        self._table_sons = {ord(c): chr(0x21 + k) for k, c in enumerate(caracteres)}
        self.esps_cles = [self.cle_de_son(e) for e in self.esps]

    def cle_de_son(self, son: str) -> str:
        return son.translate(self._table_sons)

    def communes_du_code_postal(self, code_postal: str) -> list[Commune]:
        """The communes that carry this postal code, largest first."""
        communes = [self.communes[i] for i in self.par_cp.get(code_postal, [])]
        return sorted(communes, key=lambda c: (-c.population, c.nom))

    def commune(self, insee: str) -> Commune | None:
        i = self.par_insee.get(insee)
        return None if i is None else self.communes[i]

    def coordonnees(self, insee: str) -> tuple[float, float] | None:
        """(longitude, latitude) of a commune's centre, or None."""
        c = self.commune(insee)
        if c is None or c.lon is None or c.lat is None:
            return None
        return (c.lon, c.lat)

    def nom_departement(self, code: str) -> str:
        return self.departements.get(code, code)


def distance_km(c: Commune, lon: float, lat: float) -> float:
    if c.lon is None or c.lat is None:
        return 9999.0
    p1, p2 = math.radians(c.lat), math.radians(lat)
    dp, dl = p2 - p1, math.radians(lon - c.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def lire_fichier(chemin: Path) -> BaseCommunes:
    """Read a generated file. Synchronous: call it off the event loop."""
    with gzip.open(chemin, "rt", encoding="utf-8") as f:
        donnees = json.load(f)
    communes, norms, phons, sons, esps = [], [], [], [], []
    for insee, nom, cps, population, dep, lon, lat, norm, phon, son, *esp in donnees["communes"]:
        communes.append(Commune(insee, nom, tuple(cps), population, dep, lon, lat))
        norms.append(norm)
        phons.append(phon)
        sons.append(son)
        esps.append(esp[0] if esp else "")
    return BaseCommunes(
        communes=communes,
        norms=norms,
        phons=phons,
        sons=sons,
        departements=donnees["departements"],
        entete=donnees["entete"],
        esps=esps,
    )


_base: BaseCommunes | None = None
_verrou = threading.Lock()


def charger_base() -> BaseCommunes:
    """The process-wide list, read on first use. Blocking: see ``obtenir_base``."""
    global _base
    if _base is None:
        with _verrou:
            if _base is None:
                _base = lire_fichier(FICHIER_BASE)
    return _base


def base_si_chargee() -> BaseCommunes | None:
    """The process-wide list if already read, else None. Never reads the file."""
    return _base


async def obtenir_base() -> BaseCommunes:
    """The process-wide list, read in a worker thread the first time."""
    if _base is not None:
        return _base
    return await asyncio.to_thread(charger_base)
