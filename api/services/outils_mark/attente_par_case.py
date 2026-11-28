"""[.mark] Chantier Partie 1, lot 6 (D24) : la phrase d'attente choisie par la case exécutée (lecture de la carte, adresse et zone, réservation
retrouvée, enregistrement), tirée de sa famille sans répétition dans l'appel (``variantes_d_attente``).

Lot 8, 8c-2 (128) : le mécanisme ne connaît plus le métier. Le module du connecteur (``modules/registre.Module.attentes``, ``module:fonction`` qui rend
``(familles, famille_de_la_case)``) fournit les familles et la lecture des cases ; la restauration les pose (``restauration/attentes.py``).

Le seuil reste celui de l'outil (``seuil_patience_ms``, 1 200 ms par défaut) : rien n'est dit si l'outil répond avant. Une case sans famille garde
la phrase d'attente de l'outil, comme avant. ⛔ Ne lève jamais (une panne est écrite au journal, la phrase de l'outil reste).
"""

from __future__ import annotations

from typing import Any

from loguru import logger


def _chemin_des_attentes(connecteur: str | None) -> str | None:
    """Le module qui donne les phrases d'attente de ce connecteur : celui qui le porte, ou celui qu'il allume (``signal``, comme la commande pour la restauration)."""
    from api.services.modules.registre import MODULES

    if not connecteur:
        return None
    return next((m.attentes for m in MODULES if m.attentes and (connecteur in m.connecteurs or connecteur in m.signal)), None)


def config_avec_l_attente(config: dict[str, Any], connecteur: str | None, action: str | None, arguments: Any) -> dict[str, Any]:
    """La configuration de l'outil, avec les variantes d'attente de la famille du geste (sinon telle quelle)."""
    try:
        chemin = _chemin_des_attentes(connecteur)
        if chemin is None:
            return config
        from api.services.modules.crochets import resoudre

        familles, famille_de_la_case = resoudre(chemin)()
        famille = famille_de_la_case(action, arguments)
        variantes = familles.get(famille) if famille else None
        return {**config, "phrases_attente": list(variantes)} if variantes else config
    except (OSError, ValueError, LookupError, TypeError, AttributeError, ImportError) as erreur:  # jamais à la place du tour : la phrase de l'outil reste
        logger.warning(f"[attente] phrases d'attente du module illisibles ({connecteur}.{action}) : {erreur!r}")
        return config
