"""[.mark] Chantier agents-specialises (lot 3) : la fiche appartient à l'appel.

Quand un agent prend la main par passation, ses champs de fiche entrent dans la fiche de
l'appel (P4 du plan du 13/10) : même nom = un seul champ, et c'est la définition de
l'agent qui a décroché qui reste ; un champ propre à l'agent appelé s'ajoute ; les
valeurs déjà notées sont gardées (elles vivent dans le contexte de l'appel, pas ici).
Aucun mot de métier : des noms de champs venus de la configuration.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Mapping

from loguru import logger

from api.services.workflow.fiche_au_fil_de_leau import ChampFiche, ReglagesFiche


def champs_fusionnes(
    fiche: ReglagesFiche | None, reglages_agent: Mapping[str, Any] | None
) -> tuple[ChampFiche, ...] | None:
    """Les champs de la fiche de l'appel augmentés de ceux de l'agent appelé, ou
    ``None`` s'il n'y a rien à ajouter (fiche éteinte, agent sans fiche, aucun champ
    nouveau). ⛔ Ne lève jamais."""
    try:
        if fiche is None:
            return None
        autre = ReglagesFiche.depuis(dict(reglages_agent or {}))
        if autre is None:
            return None
        connus = {champ.nom for champ in fiche.champs}
        nouveaux = tuple(champ for champ in autre.champs if champ.nom not in connus)
        return fiche.champs + nouveaux if nouveaux else None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[fiche] champs de l'agent appelé illisibles : {e!r}")
        return None


def fiche_fusionnee(
    fiche: ReglagesFiche | None, reglages_agent: Mapping[str, Any] | None
) -> ReglagesFiche | None:
    """Une COPIE de la fiche de l'appel avec les champs de l'agent appelé (clavier :
    un moteur par passage). La fiche d'origine si rien ne change."""
    champs = champs_fusionnes(fiche, reglages_agent)
    if fiche is None or champs is None:
        return fiche
    return dataclasses.replace(fiche, champs=champs)


def traitement_pour_agent_appele(engine: Any) -> Any:
    """Le processeur de prise de notes à placer dans le sous-circuit d'un agent appelé
    par passation (téléphone) : le post-scriptum, ou le lecteur de portes du greffier.
    Le greffier lui-même reste celui de l'appel (déclenché par la conversation), il
    n'est jamais recréé. ``None`` hors de ces modes. ⛔ Ne lève jamais."""
    try:
        from api.services.pipecat.lecteur_de_portes import lecteur_de_portes_du_moteur
        from api.services.pipecat.post_scriptum import post_scriptum_du_moteur
        from api.services.workflow.fiche_au_fil_de_leau import (
            MODE_GREFFIER,
            MODE_POST_SCRIPTUM,
        )

        fiche = engine.fiche
        if fiche is None:
            return None
        if fiche.mode == MODE_POST_SCRIPTUM:
            return post_scriptum_du_moteur(engine)
        if fiche.mode == MODE_GREFFIER and getattr(engine, "greffier", None) is not None:
            return lecteur_de_portes_du_moteur(engine)
        return None
    except Exception as e:  # noqa: BLE001
        logger.error(f"[fiche] prise de notes de l'agent appelé non branchée : {e!r}")
        return None
