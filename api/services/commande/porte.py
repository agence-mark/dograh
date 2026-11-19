"""[.mark] La porte d'entrée de la commande (chantier Partie 1) : ce que le connecteur ``commande`` exécute.

- ``lire`` (lot 2, E16) : la lecture, qui n'écrit jamais rien (``services/commande/lire.py``) ;
- ``fiche`` : la fiche à cases, exécutée case par case dans l'ordre du banc (lot 3, ``executer_la_fiche``).

La source (le catalogue) est ouverte une fois par appel d'outil, comme avant ; une panne du catalogue ne lève pas : ``INDISPONIBLE`` au journal (R1).
"""

from __future__ import annotations

from dataclasses import is_dataclass, replace
from typing import Any

from loguru import logger

from api.services.actions_communes.enveloppe import Enveloppe
from api.services.commande import etat_pour_le_modele
from api.services.commande import panier as P
from api.services.commande import source as registre_des_sources
from api.services.commande.lire import lire
from api.services.commande.reglages import reglages_de_la_commande
from api.services.commande.resultat import (
    question_apres_enregistrement,
    question_du_numero_affiche,
)

SOURCE_DE_L_OUTIL = "source"  # clé du réglage de l'outil qui nomme sa source ; vide : ``classeur`` (reprise de ``action.py``)


def _regles(ctx: Any):
    regles = reglages_de_la_commande(ctx.configurations)
    if regles is not None and is_dataclass(regles):
        regles = replace(regles, question_numero_affiche=question_du_numero_affiche(ctx), question_apres_enregistrement=question_apres_enregistrement(ctx))
    return regles


async def executer_la_fiche(fiche_du_modele: dict[str, Any], contexte: Any) -> dict[str, Any]:
    """La fiche exécutée case par case : son exécutant est le lot 3 (D48). Jusque-là, refusée avec la raison, rien n'est changé."""
    return Enveloppe("REJETEE", raison="operation_inconnue", a_faire="rien n'est changé").vers_json()


async def executer_la_fiche_du_service(fiche_du_modele: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """La fiche du service exécutée : son exécutant est le lot 3 (D48). Jusque-là, refusée avec la raison, rien n'est changé."""
    return Enveloppe("REJETEE", raison="operation_inconnue", a_faire="rien n'est changé").vers_json()


async def executer(action: Any, arguments: dict[str, Any], ctx: Any, delai_s: float) -> dict[str, Any]:
    regles = _regles(ctx)
    if regles is None:
        return Enveloppe("REJETEE", raison="rien_a_faire").vers_json()
    p = P.du_dossier(ctx.fiche)
    try:
        from api.services.restauration.recherche_reglages import (
            reglages_de_la_recherche,
        )

        async with registre_des_sources.ouvrir(
            (ctx.reglages or {}).get(SOURCE_DE_L_OUTIL), ctx, reglages_de_recherche=reglages_de_la_recherche(ctx.configurations)
        ) as source_ouverte:
            source = etat_pour_le_modele.SourceQuiRetient(source_ouverte)
            if action.nom == "lire":
                return await lire(source, p, regles, dict(arguments or {}), str(ctx.run_id) if getattr(ctx, "run_id", None) else None)
            if action.nom == "fiche":
                return await executer_la_fiche(dict(arguments or {}), ctx)
    except Exception as erreur:  # noqa: BLE001 -- R1 : au journal, l'appel continue
        logger.error(f"[.mark] commande {action.nom} en échec : {erreur!r}")
        return Enveloppe("REJETEE", raison="rien_a_faire", faits={"indisponible": True}).vers_json()
    return Enveloppe("REJETEE", raison="operation_inconnue").vers_json()
