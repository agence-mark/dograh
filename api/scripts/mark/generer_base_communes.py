"""[.mark] Build the national list of communes used to recognise the town a caller names.

Run from the repository root, once a year or when the keys change:

    PYTHONPATH=. api/.venv/Scripts/python.exe -m api.scripts.mark.generer_base_communes

Writes ``api/assets/communes/communes-AAAA-MM.json.gz``. Then point
``FICHIER_BASE`` in ``api/services/communes/base.py`` at the new file, run
``api/tests/mark/test_base_communes.py`` and ``test_analyse_communes.py``, and
delete the old file in the same commit.

⛔ Never called during a call: it downloads.

Source: API Géo, https://geo.api.gouv.fr (INSEE Code officiel géographique,
La Poste postal codes, INSEE population). Licence Ouverte (open licence of the
French State's geographic API); attribution kept in the file header.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from api.services.communes.base import (
    DOSSIER_BASE,
    VERSION_CLES,
    cle_phonetique,
    cle_sonore,
    normaliser,
)

URL_COMMUNES = (
    "https://geo.api.gouv.fr/communes"
    "?fields=nom,code,codesPostaux,population,centre,codeDepartement&format=json"
)
URL_DEPARTEMENTS = "https://geo.api.gouv.fr/departements?fields=nom,code&format=json"


def _telecharger(url: str):
    requete = urllib.request.Request(url, headers={"User-Agent": "agence-mark/dograh"})
    with urllib.request.urlopen(requete, timeout=120) as reponse:
        return json.load(reponse)


def construire(communes_brutes: list[dict], departements_bruts: list[dict], telecharge_le: str) -> dict:
    communes = []
    for c in sorted(communes_brutes, key=lambda c: c["code"]):
        lon, lat = (c.get("centre") or {}).get("coordinates", (None, None))
        norm = normaliser(c["nom"])
        communes.append(
            [
                c["code"],
                c["nom"],
                sorted(c.get("codesPostaux") or []),
                c.get("population") or 0,
                c.get("codeDepartement") or "",
                lon,
                lat,
                norm,
                cle_phonetique(norm),
                cle_sonore(norm),
            ]
        )
    return {
        "entete": {
            "telecharge_le": telecharge_le,
            "sources": [URL_COMMUNES, URL_DEPARTEMENTS],
            "producteur": "API Géo (geo.api.gouv.fr) : INSEE COG, La Poste, INSEE population",
            "licence": "Licence Ouverte",
            "perimetre": "communes actuelles seulement, ni anciennes communes ni lieux-dits",
            "version_cles": VERSION_CLES,
            "colonnes": ["insee", "nom", "codes_postaux", "population", "departement",
                         "longitude", "latitude", "norm", "phon", "son"],
            "nombre": len(communes),
        },
        "departements": {d["code"]: d["nom"] for d in departements_bruts},
        "communes": communes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sortie", type=Path, default=None)
    args = parser.parse_args()

    maintenant = datetime.now(timezone.utc)
    communes = _telecharger(URL_COMMUNES)
    departements = _telecharger(URL_DEPARTEMENTS)
    donnees = construire(communes, departements, maintenant.date().isoformat())

    sortie = args.sortie or DOSSIER_BASE / f"communes-{maintenant:%Y-%m}.json.gz"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0: the same download gives the same bytes, so git sees no change.
    with open(sortie, "wb") as brut, gzip.GzipFile(fileobj=brut, mode="wb", mtime=0) as f:
        f.write(json.dumps(donnees, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    print(f"{donnees['entete']['nombre']} communes -> {sortie} ({sortie.stat().st_size // 1024} Ko)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
