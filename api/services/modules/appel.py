"""[.mark] Lot F8 (M4) : un module coupé ne laisse aucun outil dans l'appel.

Ses consignes et ses variables, chaque module les retient déjà lui-même quand son interrupteur est éteint
(lecture des nombres, des communes, de l'épellation, lexique, équipe, contrôle des données : leurs tests et
les traversants le prouvent). Restait ses OUTILS : la vérification de l'appelant répondait « indisponible »
et l'outil de l'équipe refusait toute personne, mais le modèle les voyait. L'appel garde ici la
configuration qu'il lit (celle du premier agent, comme ``engine.reglages_appel``) et le gestionnaire des
outils ne montre ni n'inscrit un outil dont le module est coupé.

Moteur sans configuration posée (montage à la main, temps réel) : rien n'est retiré, comme avant.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from api.services.modules.etat import outil_d_un_module_coupe

ATTRIBUT = "configurations_des_modules"


def brancher_les_modules(engine: Any, run_configs: Mapping | None) -> None:
    setattr(engine, ATTRIBUT, dict(run_configs or {}))


def outil_coupe_dans_l_appel(engine: Any, outil: Any) -> bool:
    # Seule une configuration POSÉE compte (un moteur doublé répond n'importe quoi à un attribut absent).
    configurations = getattr(engine, ATTRIBUT, None)
    return outil_d_un_module_coupe(outil, configurations if isinstance(configurations, Mapping) else None)
