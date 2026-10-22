"""[.mark] Lot F8 : un module est-il allumé, et un outil appartient-il à un module coupé ? (M4)

Pur : ni base, ni réseau. Lit ce que l'appel lit déjà : la configuration de l'agent (la valeur absente vaut
le défaut du schéma, comme chaque module la lit) et les outils posés sur ses étapes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from loguru import logger

from api.enums import ToolCategory
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.modules.registre import MODULES, Module, module_du_connecteur


def _defaut(cle: str) -> bool:
    champ = WorkflowConfigurationDefaults.model_fields.get(cle)
    return bool(champ.default) if champ is not None else False


def interrupteur_allume(module: Module, configurations: Mapping | None) -> bool:
    """The module's own switch, read through the schema like each module reads it (« false » typed as text
    is off). A module without a switch key answers ``True``: its tools decide (``actif_sur``)."""
    cle = module.interrupteur
    if cle is None:
        return True
    configurations = configurations or {}
    if cle not in configurations or configurations.get(cle) is None:
        return _defaut(cle)
    try:
        return bool(getattr(WorkflowConfigurationDefaults.model_validate({cle: configurations[cle]}), cle))
    except Exception as erreur:  # noqa: BLE001 -- unreadable = the default, as the module itself reads it
        logger.warning(f"[.mark] Switch {cle} of module {module.code} unreadable, default used: {erreur!r}")
        return _defaut(cle)


def connecteur_de(outil: Any) -> str | None:
    """The internal connector of an ``integration`` tool, ``None`` for any other tool."""
    if getattr(outil, "category", None) != ToolCategory.INTEGRATION.value:
        return None
    config = ((getattr(outil, "definition", None) or {}).get("config") or {}) if outil else {}
    connecteur = config.get("connecteur")
    return connecteur if isinstance(connecteur, str) else None


def outil_d_un_module_coupe(outil: Any, configurations: Mapping | None) -> bool:
    """True when the tool belongs to a module whose switch is off for this agent: the call does not offer
    it (M4, « ni outil »). ``configurations`` ``None`` (not known): never filtered, as before."""
    if configurations is None:
        return False
    module = module_du_connecteur(connecteur_de(outil))
    return module is not None and not interrupteur_allume(module, configurations)


def actif_sur(module: Module, configurations: Mapping | None, outils: Iterable[Any]) -> bool:
    """Is the module on for an agent? A switch key: its value. No key: one of its tools on a step."""
    if module.interrupteur is not None:
        return interrupteur_allume(module, configurations)
    return any(connecteur_de(o) in module.connecteurs for o in outils)


def modules_actifs(configurations: Mapping | None, outils: Iterable[Any]) -> list[str]:
    outils = list(outils)
    return [m.code for m in MODULES if actif_sur(m, configurations, outils)]
