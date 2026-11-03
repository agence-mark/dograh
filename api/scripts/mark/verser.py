"""[.mark] Verse le contenu de la bibliothèque rangé dans le dépôt (``services/builder/versement/contenu``).

    python -m api.scripts.mark.verser

Joué au démarrage du conteneur, après les migrations (``scripts/start_services_docker.sh``). Idempotent ; n'écrase jamais
une version écrite par une personne ; un échec ne bloque pas le démarrage (code de sortie 0, échec journalisé).
"""

from __future__ import annotations

import asyncio
import json
import sys


async def _principal() -> int:
    from api.services.builder.versement import verser

    try:
        rapport = await verser()
    except Exception as erreur:  # noqa: BLE001 -- jamais un démarrage bloqué par le versement
        print(f"versement en échec : {type(erreur).__name__}: {erreur}", file=sys.stderr)
        return 0
    print(json.dumps(rapport.en_json(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_principal()))
