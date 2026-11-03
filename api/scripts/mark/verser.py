"""[.mark] Verse le contenu de la bibliothèque rangé dans le dépôt (``services/builder/versement/contenu``), puis reprend les
modèles de réglages qui vivaient encore dans les organisations (``services/modeles_reglages/bibliotheque.py``).

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
    # D1 (E45) : la donnée déplacée. Les modèles de réglages stockés par organisation deviennent des éléments de la
    # bibliothèque ; aucune ligne d'origine n'est supprimée, un nom pris par une personne n'est jamais écrasé.
    try:
        from api.services.modeles_reglages.bibliotheque import reprendre_les_existants

        reprise = await reprendre_les_existants()
        print(json.dumps({"modeles_reglages": reprise.en_json()}, ensure_ascii=False))
    except Exception as erreur:  # noqa: BLE001
        print(f"reprise des modèles de réglages en échec : {type(erreur).__name__}: {erreur}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_principal()))
