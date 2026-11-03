"""[.mark] Le schéma de l'API, SANS serveur (builder partie 2, prérequis 6).

Écrit ``ui/openapi.json`` à partir de ``app.openapi()``, exactement ce que sert ``/api/v1/openapi.json`` : la fenêtre
principale régénère ensuite le client (``ui/src/client/*.gen.ts``) une fois après chaque fusion, sans lancer l'API.

    python -m scripts.mark.generer_openapi            # écrit ui/openapi.json
    python -m scripts.mark.generer_openapi --sortie X  # ailleurs

Puis, dans ``ui/`` : ``npm run generate-client:fichier`` (``OPENAPI_INPUT=openapi.json npx openapi-ts``).
⛔ Un sous-agent ne commite jamais le client généré : seule la fenêtre principale le fait, après la fusion.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
SORTIE_PAR_DEFAUT = RACINE / "ui" / "openapi.json"


def schema() -> dict:
    from loguru import logger

    logger.remove()
    from api.app import app

    return app.openapi()


def main() -> None:
    lecteur = argparse.ArgumentParser()
    lecteur.add_argument("--sortie", default=str(SORTIE_PAR_DEFAUT))
    sortie = Path(lecteur.parse_args().sortie)
    spec = schema()
    sortie.write_text(json.dumps(spec, ensure_ascii=False, indent=1, sort_keys=False), encoding="utf-8")
    print(f"{len(spec.get('paths', {}))} chemins écrits dans {os.path.relpath(sortie, RACINE)}")


if __name__ == "__main__":
    main()
