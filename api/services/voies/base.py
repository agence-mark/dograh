"""[.mark] The streets of a commune, read from the national address base (BAN).

Why this module exists
----------------------
The town check of 2026-09-16 fixed the town; the street stayed whatever the
transcription wrote. On the runs: "rue Danton" heard "rue d'antan", "Rue
John-Fitzgerald Kennedy" heard "rue Jones-phyrole-Canédie". A per-client list
of streets does not carry to the next client, so the street is searched in the
**streets of that commune** in the BAN, exactly as the town is searched in the
national list of communes.

The data
--------
``api/assets/voies/voies-AAAA-MM-JJ-XX.sqlite.gz``, one file per department,
produced by ``api/scripts/mark/generer_base_voies.py`` from the BAN weekly
export (Licence Ouverte). Adresses and lieux-dits both (Q3): the Oise is full
of hamlets, and "au lieu-dit les Granges" carries no street type.

⛔ Q1 = A (Evan, 2026-09-22): the files live IN this repository, one per
department, the largest 2.6 MB. Nothing to host beside the service.

🔑 The three comparison keys are computed ONCE, by the generation script, and
stored. Computing them on the call cost 1.9 s for Paris; reading them back, 64 ms.
⛔ Change ``sans_type``, ``normaliser`` or the sound keys and the files must be
regenerated: ``test_recherche_voie.py`` compares stored and recomputed keys.

⛔ Never on the event loop: a department is decompressed once, on first use, and
a commune is read from SQLite — both belong in a worker thread.
"""

from __future__ import annotations

import gzip
import shutil
import sqlite3
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from api.services.communes.base import normaliser

# Same folder as ``APP_ROOT_DIR / "assets"``, computed here like
# ``communes/base.py`` does: ``api.constants`` requires DATABASE_URL at import,
# which the generation script does not have.
DOSSIER_BASE = Path(__file__).resolve().parents[2] / "assets" / "voies"
# ⛔ Named explicitly, not "the newest file in the folder": which base a call ran
# on must be readable in the code. Regenerating = new files + this constant.
EXPORT = "2026-09-16"

# Where a department is decompressed on first use. Inside the container, wiped
# with it; nothing to clean up, nothing to mount.
DOSSIER_TRAVAIL = Path("/tmp/mark-voies")

# At most this many communes kept in memory per process: about 0.7 MB each,
# 11 MB for Paris (measured 2026-09-22).
COMMUNES_EN_CACHE = 32

_verrou = threading.Lock()


@dataclass(frozen=True)
class VoiesCommune:
    """Everything the search needs for one commune, keys already computed."""

    noms: tuple[str, ...]
    # First word of each name, normalised: the type said ("chemin") is a tie-break.
    types: tuple[str, ...]
    cles_sonores: tuple[str, ...]
    cles_phonetiques: tuple[str, ...]
    sons: tuple[str, ...]
    numeros: tuple[frozenset[str], ...]

    def __len__(self) -> int:
        return len(self.noms)


def departement_de(insee: str) -> str:
    """"60175" -> "60", "97411" -> "974". The file is named after it."""
    return insee[:3] if insee.startswith("97") else insee[:2]


def fichier_departement(departement: str) -> Path:
    """The decompressed file, decompressing it on first use. Blocking."""
    cible = DOSSIER_TRAVAIL / f"voies-{EXPORT}-{departement}.sqlite"
    if cible.exists():
        return cible
    source = DOSSIER_BASE / f"voies-{EXPORT}-{departement}.sqlite.gz"
    if not source.exists():
        raise FileNotFoundError(source)
    with _verrou:
        if cible.exists():
            return cible
        DOSSIER_TRAVAIL.mkdir(parents=True, exist_ok=True)
        # Written aside then renamed: two workers decompressing at once must not
        # leave a half-written file that the other one opens.
        provisoire = cible.with_suffix(f".sqlite.{threading.get_ident()}")
        with gzip.open(source, "rb") as entree, provisoire.open("wb") as sortie:
            shutil.copyfileobj(entree, sortie, length=1 << 20)
        provisoire.replace(cible)
    return cible


@lru_cache(maxsize=COMMUNES_EN_CACHE)
def voies_de(insee: str) -> VoiesCommune:
    """The streets of this commune. Blocking: call it off the event loop."""
    fichier = fichier_departement(departement_de(insee))
    connexion = sqlite3.connect(f"file:{fichier}?mode=ro", uri=True)
    try:
        lignes = connexion.execute(
            "select nom, coeur, cle_sonore, cle_phon, son, numeros from voies where insee=?",
            (insee,),
        ).fetchall()
    finally:
        connexion.close()
    return VoiesCommune(
        noms=tuple(l[0] for l in lignes),
        types=tuple(_premier_mot(l[0]) for l in lignes),
        cles_sonores=tuple(l[2] for l in lignes),
        cles_phonetiques=tuple(l[3] for l in lignes),
        sons=tuple(l[4] or "" for l in lignes),
        numeros=tuple(frozenset(l[5].split(",")) if l[5] else frozenset() for l in lignes),
    )


def _premier_mot(nom: str) -> str:
    mots = normaliser(nom).split()
    return mots[0] if mots else ""


# ⛔ No ``precharger`` here, on purpose. The plan foresaw loading a commune's
# streets at the turn that settles the town, to make the address turn free. It
# turns out the two are the SAME turn: a step that collects ``commune`` is a
# step that collects an address (Q7), so the streets are already loaded there —
# in a worker thread, never on the audio loop — and every later turn of the call
# hits the cache. A preload function would only be dead code pretending the
# problem was handled. Measured 2026-09-22: 2-9 ms for an Oise commune, 64 ms
# for Paris, once per commune per process.
