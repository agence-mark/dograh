"""[.mark] Verse le contenu de la bibliothèque rangé dans le dépôt (``services/builder/versement/contenu``), puis reprend les
modèles de réglages qui vivaient encore dans les organisations (``services/modeles_reglages/bibliotheque.py``).

    python -m api.scripts.mark.verser

Joué au démarrage du conteneur, après les migrations (``scripts/start_services_docker.sh``). Idempotent ; n'écrase jamais
une version écrite par une personne ; un échec ne bloque pas le démarrage (code de sortie 0, échec journalisé).

Revue serveur, mineur 10 : plusieurs répliques démarrent en parallèle. Un verrou de la base (``pg_try_advisory_lock``) fait que UNE
seule verse à la fois ; les autres passent leur tour sans attendre (le contenu est le même). Le script shell borne en plus
l'ensemble par ``timeout`` : un versement qui s'éternise ne retient jamais le démarrage.
"""

from __future__ import annotations

import asyncio
import json
import sys
from contextlib import asynccontextmanager

CLE_DU_VERROU = 7_431_900_112  # arbitraire, propre au versement de la bibliothèque


@asynccontextmanager
async def sous_verrou(engine):
    """Rend vrai si CETTE réplique tient le verrou du versement, faux si une autre verse déjà. Le verrou tient une connexion à part
    et se libère à la sortie (ou à la mort du processus : le verrou est de session)."""
    from sqlalchemy import text

    async with engine.connect() as connexion:
        pris = bool((await connexion.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": CLE_DU_VERROU})).scalar())
        try:
            yield pris
        finally:
            if pris:
                await connexion.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": CLE_DU_VERROU})


async def _principal() -> int:
    from api.db import db_client

    try:
        async with sous_verrou(db_client.engine) as pris:
            if not pris:
                print("versement déjà en cours dans une autre réplique : passé")
                return 0
            return await _verser()
    except Exception as erreur:  # noqa: BLE001 -- jamais un démarrage bloqué par le versement
        print(f"versement en échec : {type(erreur).__name__}: {erreur}", file=sys.stderr)
        return 0


async def _verser() -> int:
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
    # Lot M (7) : chaque agent sans recette indiquée reçoit la recette par défaut (idempotent, aucun changement de comportement).
    try:
        from api.services.builder import recettes

        print(json.dumps({"recettes_des_agents": await recettes.verser_les_agents()}, ensure_ascii=False))
    except Exception as erreur:  # noqa: BLE001
        print(f"versement des recettes des agents en échec : {type(erreur).__name__}: {erreur}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_principal()))
