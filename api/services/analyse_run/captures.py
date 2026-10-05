"""Les captures nouvelles d'un appel (.mark, chantier langwatch-et-fenetre-du-run, lot 2).

Ce que le fork n'enregistrait nulle part et que la fenêtre du run affiche. Chaque capture s'écrit
dans l'estampille de l'appel ou dans ``gathered_context`` sous une clé préfixée ``mark_`` (décision
L3 : aucune migration).

⛔ Une capture ne fait JAMAIS tomber un appel : elle s'écrit dans un ``try`` et, si elle échoue, le
journal le dit et la fenêtre affiche « not captured ». C'est le principe de toutes les mesures du
fork (voir le détail de latence dans ``run_pipeline.py``).
"""

from __future__ import annotations

import os
from typing import Any

from loguru import logger

from api.constants import APP_VERSION

CLE_VERSION = "mark_version"

# Le commit que Railway a construit (déploiement par ``deployer.mjs``, au commit nommé, depuis le
# dépôt GitHub). Absent hors de Railway (poste, tests) : la version le dit (``None``).
VARIABLE_DU_COMMIT = "RAILWAY_GIT_COMMIT_SHA"


def estampiller_la_version(runtime_configuration: dict, definition: Any) -> dict:
    """Écrit dans l'estampille QUEL code et QUELLE version de l'agent ont joué l'appel : la
    version de l'application, le commit déployé, la définition jouée et son numéro de version."""
    try:
        runtime_configuration[CLE_VERSION] = {
            "app_version": APP_VERSION,
            "commit": os.getenv(VARIABLE_DU_COMMIT) or None,
            "definition_id": getattr(definition, "id", None),
            "version_number": getattr(definition, "version_number", None),
            "definition_status": _statut(definition),
        }
    except Exception as erreur:  # noqa: BLE001 — une mesure n'emporte pas l'appel
        logger.warning(f"[captures] version non estampillée : {erreur!r}")
    return runtime_configuration


def _statut(definition: Any) -> str | None:
    statut = getattr(definition, "status", None)
    return getattr(statut, "value", statut)
