"""[.mark] The verdict of a run's record, made by the after-call (L7, QD2, QD8, Q-2).

Only for an agent whose « Check the data » is on (X2). The record is the one the extraction left
(``extracted_variables``); it is read, never changed. The fields EXPECTED (QD2) are those of the
steps the call went through (``nodes_visited``) that declare them as extraction variables. With
the record of « la fiche au fil de l'eau » on, its fields belong to no step: nothing is expected
of them (only their values are checked).

Q-2: the verdict is written with the call in the client's database, shown in the run's « After
the call », and said in the mail of a request when the record is to be taken up again.
"""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger

from api.services.fiche.controle import NON_CONTROLE, controler
from api.services.fiche.reconnaissance import controle_allume, tous_les_noms


def champs_attendus(definition, visites: list[str]) -> list[str]:
    """QD2: the extraction variables of the steps the call went through, in order."""
    noeuds = ((getattr(definition, "workflow_json", None) or {}).get("nodes")) or []
    sortie: list[str] = []
    for noeud in noeuds:
        donnees = (noeud or {}).get("data") or {}
        if donnees.get("name") not in visites or not donnees.get("extraction_enabled"):
            continue
        for variable in donnees.get("extraction_variables") or []:
            nom = (variable or {}).get("name")
            if nom and nom not in sortie:
                sortie.append(nom)
    return sortie


async def verdict_du_run(run) -> dict | None:
    """The verdict, or None when the agent's switch is off. Never raises."""
    definition = getattr(run, "definition", None)
    configs = getattr(definition, "workflow_configurations", None) or {}
    if not controle_allume(configs):
        return None
    try:
        from api.services.communes.base import normaliser, obtenir_base

        contexte = getattr(run, "gathered_context", None) or {}
        fiche = contexte.get("extracted_variables")
        fiche = fiche if isinstance(fiche, dict) else {}
        visites = [v for v in contexte.get("nodes_visited") or [] if isinstance(v, str)]
        debut = getattr(run, "created_at", None) or datetime.now(UTC)
        try:
            base = await obtenir_base()
        except Exception:  # noqa: BLE001 -- the postcodes are then not checked
            base = None
        verdict = controler(
            fiche,
            noms=tous_les_noms(configs),
            champs_attendus=champs_attendus(definition, visites),
            jour_appel=debut.date(),
            base_communes=base,
            normaliser=normaliser,
        )
        return {**verdict, "le": datetime.now(UTC).isoformat()}
    except Exception as erreur:  # noqa: BLE001 -- QD8: never costs the after-call
        logger.warning(f"[.mark] Record of run {getattr(run, 'id', '?')} not checked: {erreur!r}")
        return {"statut": NON_CONTROLE, "problemes": []}
