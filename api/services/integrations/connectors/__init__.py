"""[.mark] The connectors: the agent works in the client's software (chantier l-agent-travaille,
L5; plan connecteurs-agent D1 to D9, D11 to D18).

- ``nango``         the installation's Nango: connections found by the organization's tag, relay
- ``catalogue``     the declarative actions, one file per software in ``actions/``
- ``modele_commun`` the common .mark model the actions read (D16)
- ``execution``     an action within its deadline, fallback, stamps (D6 to D8)
- ``anticipation``  read-only actions launched as soon as their fields are known (D17, D18)
- ``routes``        the catalogue, the connections and the authorization link, on screen

The tool type ``integration`` (``api/schemas/tool.py``) points at a connector and an action;
the engine's dispatcher runs it (``pipecat_engine_custom_tools.py``). Off by default: an agent
without an ``integration`` tool is not touched (D12).
"""

from __future__ import annotations

from api.services.integrations.base import IntegrationPackageSpec
from api.services.integrations.registry import register_package

from .routes import router

PACKAGE = register_package(IntegrationPackageSpec(name="connectors", routers=(router,)))

__all__ = ["PACKAGE"]
