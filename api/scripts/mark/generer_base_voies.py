"""[.mark] Build the street base used to recognise the street a caller names.

Run from the repository root, once per BAN export (about every quarter):

    PYTHONPATH=. api/.venv/Scripts/python.exe -m api.scripts.mark.generer_base_voies

Writes ``api/assets/voies/voies-AAAA-MM-JJ-XX.sqlite.gz``, one file per
department. Then point ``EXPORT`` in ``api/services/voies/base.py`` at the new
date, run ``api/tests/mark/test_recherche_voie.py``, regenerate the test index
(``extraire_index_de_test.py``) and delete the old files in the same commit.

Measured on 2026-09-22, France and overseas: 2 443 800 streets, 34 882
communes, 287 MB raw, 111 MB compressed, 13 minutes on a workstation.

⛔ Never called during a call: it downloads ~1 GB and takes minutes.

🔑 Two things this script must keep doing, each bought by a measured failure:

1. **Import ``sans_type`` from the search code** (``services/voies/analyse``),
   never copy it. On 2026-09-22 the two lists of street types diverged —
   "cour" was missing here — so "Cour d'Alger" kept its type in its key while
   "Rue d'Alger" did not, and the wrong one was announced SURE to the model.
   ``test_recherche_voie.py`` compares stored keys with recomputed ones.
2. **Precompute the three keys.** Computing them on the call cost 1.9 s for
   Paris; reading them back, 64 ms.

Why the ``weekly`` export and not ``latest``: ``latest`` changes every day, so
two builds are not comparable and no file can be named after what it holds.

Source: Base Adresse Nationale, https://adresse.data.gouv.fr — addresses and
lieux-dits (Q3 of the plan: the Oise is full of hamlets, and "au lieu-dit les
Granges" carries no street type). Licence Ouverte 2.0; attribution kept here.
"""

from __future__ import annotations

import argparse
import collections
import csv
import email.utils
import gzip
import shutil
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from api.services.communes.base import cle_phonetique, cle_sonore, normaliser
from api.services.communes.sons import simplifier, sons
from api.services.voies.analyse import sans_type
from api.services.voies.base import DOSSIER_BASE

BASE_BAN = "https://adresse.data.gouv.fr/data/ban/adresses/weekly/csv"

# Metropolitan France (Corsica is 2A/2B, never 20) then overseas. Each code is
# CONFIRMED by the download: a 404 is reported, never assumed.
DEPARTEMENTS = (
    [f"{n:02d}" for n in range(1, 20)]
    + ["2A", "2B"]
    + [f"{n:02d}" for n in range(21, 96)]
    + ["971", "972", "973", "974", "975", "976", "977", "978", "984", "986", "987", "988", "989"]
)

# Arrondissements brought back to their commune: the list of communes only
# knows 75056, 69123 and 13055.
ARRONDISSEMENTS = {
    **{f"751{n:02d}": "75056" for n in range(1, 21)},
    **{f"132{n:02d}": "13055" for n in range(1, 17)},
    **{f"6938{n}": "69123" for n in range(1, 10)},
}

# espeak in batches: one call for a whole department holds too much memory on
# the big ones (Nord, Gironde).
PAQUET_SONS = 20_000

csv.field_size_limit(1 << 24)


def telecharger(url: str, vers: Path) -> str | None:
    """The export's date, or None when the file does not exist (404)."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60) as reponse:
            taille = int(reponse.headers.get("Content-Length", 0))
            modifie = reponse.headers.get("Last-Modified")
    except urllib.error.HTTPError:
        return None

    if not (vers.exists() and vers.stat().st_size == taille):
        provisoire = vers.with_suffix(vers.suffix + ".part")
        with urllib.request.urlopen(url, timeout=600) as reponse, provisoire.open("wb") as fichier:
            shutil.copyfileobj(reponse, fichier, length=1 << 20)
        if provisoire.stat().st_size != taille:
            provisoire.unlink(missing_ok=True)
            return None
        provisoire.replace(vers)

    return email.utils.parsedate_to_datetime(modifie).strftime("%Y-%m-%d") if modifie else None


def lire_departement(dossier: Path, departement: str) -> dict[str, dict[str, set[str]]]:
    """{commune: {street name: {numbers}}} — addresses and lieux-dits together."""
    voies: dict[str, dict[str, set[str]]] = collections.defaultdict(lambda: collections.defaultdict(set))

    fichier = dossier / f"adresses-{departement}.csv.gz"
    if fichier.exists():
        with gzip.open(fichier, "rt", encoding="utf-8", newline="") as flux:
            for ligne in csv.DictReader(flux, delimiter=";"):
                insee = ARRONDISSEMENTS.get(ligne["code_insee"], ligne["code_insee"])
                nom = (ligne.get("nom_voie") or "").strip()
                if nom:
                    numero = ((ligne.get("numero") or "") + (ligne.get("rep") or "")).lower()
                    voies[insee][nom].add(numero)

    fichier = dossier / f"lieux-dits-{departement}-beta.csv.gz"
    if fichier.exists():
        with gzip.open(fichier, "rt", encoding="utf-8", newline="") as flux:
            for ligne in csv.DictReader(flux, delimiter=";"):
                insee = ARRONDISSEMENTS.get(ligne["code_insee"], ligne["code_insee"])
                nom = (ligne.get("nom_lieu_dit") or "").strip()
                # A lieu-dit has no number: the street exists, with none known.
                if nom and nom not in voies[insee]:
                    voies[insee][nom] = set()

    return voies


def ecrire(departement: str, voies: dict[str, dict[str, set[str]]], export: str, sortie: Path) -> dict:
    sortie.mkdir(parents=True, exist_ok=True)
    brut = sortie / f"voies-{export}-{departement}.sqlite"
    brut.unlink(missing_ok=True)

    connexion = sqlite3.connect(brut)
    connexion.execute(
        "create table voies(insee text, nom text, coeur text, cle_sonore text, "
        "cle_phon text, son text, numeros text)"
    )

    lignes = [
        (insee, nom, sans_type(normaliser(nom)),
         ",".join(sorted(numeros, key=lambda n: (len(n), n))))
        for insee, par_nom in voies.items()
        for nom, numeros in par_nom.items()
    ]
    prononces: list[str] = []
    for debut in range(0, len(lignes), PAQUET_SONS):
        paquet = [ligne[2] for ligne in lignes[debut:debut + PAQUET_SONS]]
        prononces += sons(paquet) or [""] * len(paquet)

    connexion.executemany(
        "insert into voies values(?,?,?,?,?,?,?)",
        [
            (insee, nom, coeur, cle_sonore(coeur), cle_phonetique(coeur),
             simplifier(son) if son else "", numeros)
            for (insee, nom, coeur, numeros), son in zip(lignes, prononces)
        ],
    )
    connexion.execute("create index i on voies(insee)")
    connexion.commit()
    connexion.execute("vacuum")
    connexion.close()

    comprime = brut.with_suffix(".sqlite.gz")
    with brut.open("rb") as entree, gzip.open(comprime, "wb", compresslevel=9) as flux:
        shutil.copyfileobj(entree, flux, length=1 << 20)
    brut.unlink()

    return {
        "departement": departement,
        "communes": len(voies),
        "voies": len(lignes),
        "octets": comprime.stat().st_size,
    }


def main() -> int:
    parseur = argparse.ArgumentParser()
    parseur.add_argument("--telechargements", default="", help="where the BAN files are kept")
    parseur.add_argument("--sortie", default=str(DOSSIER_BASE))
    parseur.add_argument("departements", nargs="*", help="only these ones")
    arguments = parseur.parse_args()

    telechargements = Path(arguments.telechargements or (DOSSIER_BASE.parent / "_ban"))
    telechargements.mkdir(parents=True, exist_ok=True)
    sortie = Path(arguments.sortie)
    departements = arguments.departements or DEPARTEMENTS

    debut = time.perf_counter()
    dates: set[str] = set()
    absents: list[str] = []
    for departement in departements:
        for gabarit in ("adresses-{}.csv.gz", "lieux-dits-{}-beta.csv.gz"):
            nom = gabarit.format(departement)
            date = telecharger(f"{BASE_BAN}/{nom}", telechargements / nom)
            (dates.add(date) if date else absents.append(nom))
    print(f"Téléchargement : {len(dates)} date(s) {sorted(dates)}, "
          f"{len(absents)} fichier(s) absent(s) — {(time.perf_counter() - debut) / 60:.1f} min")

    # ⛔ One single export date, or the files would not describe one same base.
    if len(dates) != 1:
        print(f"⚠️  plusieurs dates d'export : {sorted(dates)} — relancer le téléchargement")
        return 1
    export = dates.pop()

    mesures = []
    for departement in departements:
        mesure = ecrire(departement, lire_departement(telechargements, departement), export, sortie)
        mesures.append(mesure)
        print(f"{departement}: {mesure['communes']:>5} communes, {mesure['voies']:>7} voies, "
              f"{mesure['octets'] / 1e6:.2f} Mo — total {(time.perf_counter() - debut) / 60:.1f} min",
              flush=True)

    print(f"\nExport {export} : {len(mesures)} départements, "
          f"{sum(m['communes'] for m in mesures)} communes, {sum(m['voies'] for m in mesures)} voies, "
          f"{sum(m['octets'] for m in mesures) / 1e6:.0f} Mo compressés, "
          f"{(time.perf_counter() - debut) / 60:.1f} min")
    print(f"⚠️  Pointer EXPORT = \"{export}\" dans api/services/voies/base.py, "
          f"relancer test_recherche_voie.py, et supprimer les anciens fichiers dans le MÊME commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
