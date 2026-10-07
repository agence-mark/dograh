"""[.mark] One file per software: importing it declares its actions in the catalogue, and its
translator for the hub when it has one (l-agent-collegue, L4)."""

from api.services.integrations.connectors.actions import (  # noqa: F401
    equipe,
    google_agenda,
    outlook_agenda,
    planificateur,
)
