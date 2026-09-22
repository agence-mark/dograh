"""[.mark] Build the small street index the tests run on.

Why a separate index
--------------------
The real base is 111 MB compressed, 109 departments. A test suite that depends
on it is slow, and — more to the point — it would put those 111 MB in the
repository's history before Evan has confirmed where the base should live
(Q1 of the plan, revised figures in `A-VALIDER.md`, PROD-20260922-4).

So the tests run on the streets of the **communes the corpus actually names**,
extracted from the real files with the **same keys**: a few hundred kilobytes,
same code path, same verdicts.

⛔ This is not a fixture written by hand: every street, every key and every
number comes from the real base. Only the communes are filtered.

Usage, from the trial folder that holds the full index:
    python -m api.scripts.mark.extraire_index_de_test <dossier de l'index complet>
"""

from __future__ import annotations

import gzip
import json
import shutil
import sqlite3
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]
CORPUS = RACINE / "api" / "tests" / "mark" / "donnees" / "voies_corpus_2026-09-22.json"
SORTIE = RACINE / "api" / "tests" / "mark" / "donnees" / "voies"
# The tests' own export name, so a test file is never mistaken for a real one.
EXPORT_TEST = "test-2026-09-16"


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("usage: extraire_index_de_test.py <dossier de l'index complet>")
    source = Path(sys.argv[1])

    communes = sorted({cas["insee"] for cas in json.loads(CORPUS.read_text(encoding="utf-8"))})
    par_departement: dict[str, list[str]] = {}
    for insee in communes:
        par_departement.setdefault(insee[:3] if insee.startswith("97") else insee[:2], []).append(insee)

    # 🔑 One file per department, gzipped, named exactly as in production: the
    # tests then exercise the real reading path, decompression included.
    SORTIE.mkdir(parents=True, exist_ok=True)
    for ancien in SORTIE.glob("*.gz"):
        ancien.unlink()

    total = octets = 0
    for departement, codes in sorted(par_departement.items()):
        fichiers = sorted(source.glob(f"voies-*-{departement}.sqlite"))
        if not fichiers:
            print(f"⚠️  département {departement} absent de {source}")
            continue
        origine = sqlite3.connect(f"file:{fichiers[-1]}?mode=ro", uri=True)
        try:
            marques = ",".join("?" * len(codes))
            lignes = origine.execute(
                f"select insee, nom, coeur, cle_sonore, cle_phon, son, numeros "
                f"from voies where insee in ({marques})",
                codes,
            ).fetchall()
        finally:
            origine.close()

        brut = SORTIE / f"voies-{EXPORT_TEST}-{departement}.sqlite"
        brut.unlink(missing_ok=True)
        cible = sqlite3.connect(brut)
        cible.execute(
            "create table voies(insee text, nom text, coeur text, cle_sonore text, "
            "cle_phon text, son text, numeros text)"
        )
        cible.executemany("insert into voies values(?,?,?,?,?,?,?)", lignes)
        cible.execute("create index i on voies(insee)")
        cible.commit()
        cible.execute("vacuum")
        cible.close()

        comprime = brut.with_suffix(".sqlite.gz")
        with brut.open("rb") as entree, gzip.open(comprime, "wb", compresslevel=9) as sortie:
            shutil.copyfileobj(entree, sortie, length=1 << 20)
        brut.unlink()

        total += len(lignes)
        octets += comprime.stat().st_size
        print(f"{departement}: {len(codes):>3} communes, {len(lignes):>6} voies, "
              f"{comprime.stat().st_size / 1e6:.2f} Mo compressé")

    print(f"\n{len(communes)} communes, {total} voies, {octets / 1e6:.1f} Mo compressés -> {SORTIE.name}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
