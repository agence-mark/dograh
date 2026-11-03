"""[.mark] Builder, K7 : l'interrupteur du builder et ses deux portes (Réglages du Labo > Builder IA).

* **Dans l'écran** : le chat du builder (cerveau payé à l'usage par sa clé) ;
* **Dans Claude Code (MCP)** : l'abonnement de chacun, les mêmes actions par le serveur MCP du fork.

Trois restrictions dans la ligne ``MARK_BUILDER_OPTIONS`` (``options.py``), éteintes par défaut : ``builder_coupe`` (les deux portes),
``porte_ecran_coupee``, ``porte_claude_code_coupee``. Le chat de l'écran se refuse à l'ouverture (``refus_de_l_ecran``) et chaque action
se refuse au passage de l'unique chemin d'exécution (``refus_de_la_porte``, appelé par ``registre.executer``).

⛔ Une lecture qui échoue n'ouvre ni ne ferme rien : on ne coupe pas le builder parce que la base est lente (fail-open).
"""

from __future__ import annotations

from loguru import logger

from api.services.builder import options

REFUS_BUILDER = "The builder is switched off (Settings of the Lab > Builder AI)."
REFUS_ECRAN = "The builder's door in the screen is switched off (Settings of the Lab > Builder AI > Doors)."
REFUS_CLAUDE_CODE = "The builder's door in Claude Code is switched off (Settings of the Lab > Builder AI > Doors)."


async def _options(organisation: int) -> options.Options | None:
    try:
        return await options.lire(organisation)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[portes] options illisibles ({type(erreur).__name__}) : rien n'est coupé")
        return None


async def refus_de_l_ecran(organisation: int) -> str | None:
    """Pourquoi le chat de l'écran ne s'ouvre pas, ou ``None``. ``organisation`` : celle des réglages du builder."""
    o = await _options(organisation)
    if o is None:
        return None
    if o.builder_coupe:
        return REFUS_BUILDER
    return REFUS_ECRAN if o.porte_ecran_coupee else None


async def refus_de_la_porte(contexte) -> str | None:
    """Pourquoi une action de cette porte est refusée, ou ``None``."""
    from api.services.builder.actions.registre import PORTE_MCP

    o = await _options(options.organisation_pour(contexte.organisation_id))
    if o is None:
        return None
    if o.builder_coupe:
        return REFUS_BUILDER
    if contexte.porte == PORTE_MCP:
        return REFUS_CLAUDE_CODE if o.porte_claude_code_coupee else None
    return REFUS_ECRAN if o.porte_ecran_coupee else None
