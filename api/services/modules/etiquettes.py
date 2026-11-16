"""[.mark] Lot 11 du chantier module : les étiquettes que les modules posent au décroché (§ 3.3 du plan). Mécanisme commun : aucun mot de métier.

Une étiquette est une variable du contexte de l'appel (``{{cle}}``), posée UNE fois au décroché, **courte et stable** : jamais une donnée de carte, de
prix détaillé ou d'allergène (cela se demande à un outil). Chaque module les déclare (``registre.Module.etiquettes``) et fournit la fonction qui lit
ses valeurs ; ce fichier ne sait que : lesquelles sont déclarées, si le module est allumé pour l'agent, et poser sans écraser.

- ``cles_des_etiquettes()`` : toutes les clés déclarées (catalogue de l'éditeur, noms que le code pose) ;
- ``poser(contexte, valeurs)`` : pur ; une clé déjà posée et non vide n'est jamais écrasée (un essai au clavier, un appel préalable) ;
- ``injecter_etiquettes_du_module(...)`` : au décroché, téléphone et clavier. ⛔ Ne lève jamais : l'appel continue sans l'étiquette.
"""

from __future__ import annotations

import importlib
from typing import Any, Mapping

from loguru import logger

from api.services.modules.etat import interrupteur_allume
from api.services.modules.registre import MODULES, PAR_CODE, Module

MAX_ETIQUETTE = 400  # une étiquette est courte : plus long, c'est un outil


def cles_des_etiquettes() -> tuple[str, ...]:
    return tuple(e.cle for m in MODULES for e in m.etiquettes)


def modules_a_etiquettes() -> list[Module]:
    return [m for m in MODULES if m.etiquettes]


def est_posee(valeur: Any) -> bool:
    return isinstance(valeur, str) and bool(valeur.strip())


def poser(contexte: dict, valeurs: Mapping[str, Any], cles_permises: frozenset[str]) -> dict:
    """Le contexte avec les valeurs ajoutées : seulement les clés DÉCLARÉES, jamais un texte long, jamais une clé déjà posée et non vide."""
    enrichi = dict(contexte)
    for cle, valeur in valeurs.items():
        if cle in cles_permises and est_posee(valeur) and not est_posee(enrichi.get(cle)):
            enrichi[cle] = valeur.strip()[:MAX_ETIQUETTE]
    return enrichi


def _fournisseur(module: Module):
    chemin = module.fournisseur_d_etiquettes
    if not chemin:
        return None
    nom_du_module, _, nom = chemin.partition(":")
    return getattr(importlib.import_module(nom_du_module), nom)


async def injecter_etiquettes_du_module(contexte: dict, run_configs: Mapping | None, organization_id: int | None, workflow_id: int | None) -> dict:
    """Au décroché : pour chaque module allumé qui déclare des étiquettes, lit ses valeurs et les pose. Ne lève jamais."""
    try:
        if not organization_id:
            return contexte
        enrichi = contexte
        for module in modules_a_etiquettes():
            proprietaire = PAR_CODE.get(module.interrupteur_des_etiquettes or module.code, module)
            if not interrupteur_allume(proprietaire, run_configs):
                continue
            fournisseur = _fournisseur(module)
            if fournisseur is None:
                continue
            valeurs = await fournisseur(organization_id, workflow_id, enrichi)
            enrichi = poser(enrichi, valeurs or {}, frozenset(e.cle for e in module.etiquettes))
        return enrichi
    except Exception as erreur:  # noqa: BLE001 -- le décroché ne dépend jamais d'une étiquette
        logger.warning(f"[.mark] Module labels not set, the call goes on without them ({type(erreur).__name__}): {erreur}")
        return contexte
