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
import os
import shutil
import sqlite3
import tempfile
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from api.services.communes.base import normaliser
from loguru import logger

# Same folder as ``APP_ROOT_DIR / "assets"``, computed here like
# ``communes/base.py`` does: ``api.constants`` requires DATABASE_URL at import,
# which the generation script does not have.
DOSSIER_BASE = Path(__file__).resolve().parents[2] / "assets" / "voies"
# ⛔ Named explicitly, not "the newest file in the folder": which base a call ran
# on must be readable in the code. Regenerating = new files + this constant.
EXPORT = "2026-09-16"

# Where a department is decompressed on first use. Inside the container, wiped
# with it; nothing to clean up, nothing to mount. ⛔ Not "/tmp" hard-coded: on a
# Windows workstation that becomes a folder at the root of C:, outside the
# temporary folder the system actually cleans.
DOSSIER_TRAVAIL = Path(tempfile.gettempdir()) / "mark-voies"

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
    """"60175" -> "60", "97411" -> "974", "98818" -> "988".

    ⛔ The 98 prefix counts too: New Caledonia, French Polynesia, Wallis and
    Futuna and the TAAF are numbered 984 to 989. Reading only "97" sent their
    90 communes to a file named "98" that does not exist — the error was
    swallowed and the street simply never checked (counter-review of 2026-09-22).
    """
    return insee[:3] if insee[:2] in ("97", "98") else insee[:2]


def base_disponible() -> tuple[int, str | None]:
    """(how many department files match ``EXPORT``, what is wrong if anything).

    🔴 Without this, a production with no files at all is INVISIBLE: the tests
    point ``DOSSIER_BASE`` at their own folder and stay green, every address
    turn raises ``FileNotFoundError``, the reader swallows it, and the screen
    keeps offering a switch for something that never runs (independent review,
    2026-09-22). Called once at start-up, and by a test.
    """
    if not DOSSIER_BASE.is_dir():
        return 0, f"dossier absent : {DOSSIER_BASE}"
    attendus = sorted(DOSSIER_BASE.glob(f"voies-{EXPORT}-*.sqlite.gz"))
    if attendus:
        # Files for ANOTHER export sitting next to them: the constant moved and
        # the old files were not deleted, or the reverse.
        autres = [f for f in DOSSIER_BASE.glob("voies-*.sqlite.gz") if f not in attendus]
        return len(attendus), (
            f"{len(autres)} fichier(s) d'un autre export à côté de {EXPORT}" if autres else None
        )
    presents = sorted({f.name.split("-")[1] for f in DOSSIER_BASE.glob("voies-*-*.sqlite.gz")})
    return 0, (
        f"aucun fichier pour l'export {EXPORT}"
        + (f" ; présents : {', '.join(presents)}" if presents else " (dossier vide)")
    )


def journaliser_etat() -> None:
    """Say ONCE, at start-up, whether the street base is really there."""
    combien, souci = base_disponible()
    if combien and not souci:
        logger.info(f"[.mark] Street base {EXPORT}: {combien} department files")
        return
    logger.error(
        f"[.mark] 🔴 Street base unusable ({souci}). Every address turn will go "
        f"unchecked, silently, while the agents' switch stays on."
    )


def fichier_departement(departement: str) -> Path:
    """The decompressed file, decompressing it on first use. Blocking.

    🔴 The file is CHECKED before being served, not merely found. Without that
    check, one truncated file meant no street verified for that department until
    the next deploy: every later read failed, ``_lire_voie`` swallowed it, and
    nothing said so anywhere (independent review, 2026-09-22).

    ⛔ ``_verrou`` only holds inside ONE process, and the API runs one uvicorn
    process per worker on the same ``/tmp``. So the temporary name carries the
    **pid** as well as the thread id, and the check above catches whatever a
    race still leaves behind.
    """
    cible = DOSSIER_TRAVAIL / f"voies-{EXPORT}-{departement}.sqlite"
    if _lisible(cible):
        return cible
    source = DOSSIER_BASE / f"voies-{EXPORT}-{departement}.sqlite.gz"
    if not source.exists():
        raise FileNotFoundError(source)
    with _verrou:
        if _lisible(cible):
            return cible
        DOSSIER_TRAVAIL.mkdir(parents=True, exist_ok=True)
        # Written aside then renamed: two workers decompressing at once must not
        # leave a half-written file that the other one opens.
        provisoire = cible.with_suffix(f".sqlite.{os.getpid()}.{threading.get_ident()}")
        try:
            with gzip.open(source, "rb") as entree, provisoire.open("wb") as sortie:
                shutil.copyfileobj(entree, sortie, length=1 << 20)
            provisoire.replace(cible)
        finally:
            provisoire.unlink(missing_ok=True)
    return cible


def _lisible(fichier: Path) -> bool:
    """Is this file a SQLite base we can actually read? Never raises."""
    if not fichier.exists():
        return False
    try:
        connexion = sqlite3.connect(f"file:{fichier}?mode=ro", uri=True)
        try:
            connexion.execute("select count(*) from voies limit 1").fetchone()
        finally:
            connexion.close()
        return True
    except Exception as erreur:  # noqa: BLE001 -- a bad file is rebuilt, not fatal
        logger.warning(f"[.mark] Street file {fichier.name} unusable, rebuilding it: {erreur!r}")
        fichier.unlink(missing_ok=True)
        return False


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
