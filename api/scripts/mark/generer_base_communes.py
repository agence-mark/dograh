"""[.mark] Build the national list of communes used to recognise the town a caller names.

Run from the repository root, once a year or when the keys change:

    PYTHONPATH=. api/.venv/Scripts/python.exe -m api.scripts.mark.generer_base_communes

Writes ``api/assets/communes/communes-AAAA-MM.json.gz``. To recompute the
keys and sounds WITHOUT downloading (same communes, same data), for example
after a change of ``VERSION_CLES``:

    PYTHONPATH=. api/.venv/Scripts/python.exe -m api.scripts.mark.generer_base_communes
        --depuis api/assets/communes/communes-2026-09.json.gz
        --sortie api/assets/communes/communes-2026-09-v2.json.gz

The sounds need espeak-ng (``espeakng-loader``, ``phonemizer-fork``). Then point
``FICHIER_BASE`` in ``api/services/communes/base.py`` at the new file, run
``api/tests/mark/test_base_communes.py`` and ``test_analyse_communes.py``, and
delete the old file in the same commit.

⛔ Never called during a call: it downloads.

⚠️ Before pointing ``FICHIER_BASE`` at a new file, check the addresses already
saved (organizations and agents): a commune merged away since the last list
loses its INSEE code, and every later save of those preferences or agents --
even from a screen that does not show the address -- is refused with
« Unknown commune » (review of 2026-09-16).

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
from api.services.communes.sons import sons

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
    triees = sorted(communes_brutes, key=lambda c: c["code"])
    # ⛔ The sounds are required: a file without them would silently turn the
    # pronunciation score off for every call.
    sons_des_noms = sons([normaliser(c["nom"]) for c in triees])
    if sons_des_noms is None:
        raise SystemExit("espeak-ng unavailable: install espeakng-loader and phonemizer-fork")
    for c, son_prononce in zip(triees, sons_des_noms):
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
                son_prononce,
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
                         "longitude", "latitude", "norm", "phon", "son", "son_prononce"],
            "nombre": len(communes),
        },
        "departements": {d["code"]: d["nom"] for d in departements_bruts},
        "communes": communes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sortie", type=Path, default=None)
    parser.add_argument("--depuis", type=Path, default=None,
                        help="an existing file: recompute its keys, download nothing")
    args = parser.parse_args()

    maintenant = datetime.now(timezone.utc)
    if args.depuis:
        with gzip.open(args.depuis, "rt", encoding="utf-8") as f:
            ancien = json.load(f)
        communes = [
            {"code": l[0], "nom": l[1], "codesPostaux": l[2], "population": l[3],
             "codeDepartement": l[4], "centre": {"coordinates": (l[5], l[6])}}
            for l in ancien["communes"]
        ]
        departements = [{"code": code, "nom": nom} for code, nom in ancien["departements"].items()]
        donnees = construire(communes, departements, ancien["entete"]["telecharge_le"])
    else:
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
