"""[.mark] RA-B (R6, audit 06 point 7) : le juge du Labo est-il prêt à juger ? Dit à l'écran quand « allumé » ne suffit pas.

Un agent peut avoir « juge des vrais appels » allumé alors que le juge du Labo est éteint ou sans clé : l'après-appel ne fait
alors rien, en silence. Cette lecture (la même que celle de l'après-appel, sans rien juger ni appeler) le dit :

* ``regle``   : le juge du Labo peut juger (clé d'API construite, ou Claude Code : l'appel attend dans « À juger ») ;
* ``eteint``  : l'interrupteur du juge du Labo est éteint ;
* ``sans_cle``: allumé, mais aucune clé ne permet de construire son cerveau.
"""

from __future__ import annotations

from loguru import logger

ETAT_REGLE = "regle"
ETAT_ETEINT = "eteint"
ETAT_SANS_CLE = "sans_cle"


async def etat_du_juge(organisation: int) -> str:
    """⛔ Ne lève jamais : illisible, on dit ``regle`` (pas de fausse alerte)."""
    try:
        from api.services import sources_cerveaux
        from api.services.appel_simule import reglages as appel_simule
        from api.services.builder.cerveau import reglages as reglages_cerveau
        from api.services.builder.cerveau import simules

        roles = await appel_simule.lire_reglages(organisation)
        source = await sources_cerveaux.source_de(organisation, "juge_appels", roles.juge.source)
        if source == "claude_code":
            return ETAT_REGLE
        if not roles.juge.actif:
            return ETAT_ETEINT
        base = await reglages_cerveau.lire(organisation)
        cerveau = await simules.cerveau_du_role(organisation, roles.juge.model_copy(update={"source": source}), base)
        return ETAT_REGLE if cerveau is not None else ETAT_SANS_CLE
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[juge] état du juge illisible : {type(erreur).__name__}")
        return ETAT_REGLE
