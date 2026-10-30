"""[.mark] Builder : l'utilisateur déjà authentifié que le moteur pose pour appeler les outils du serveur MCP comme fonctions.

Seul du code du serveur le pose (jamais un en-tête de requête). Module à part, sans dépendance : il est lu par
``api/mcp_server/auth.py`` ET par les actions du builder, sans créer de circuit d'import (importer un module de
``api.mcp_server`` charge tout le serveur MCP).
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

UTILISATEUR_DIRECT: ContextVar[Any | None] = ContextVar("mark_builder_utilisateur", default=None)
