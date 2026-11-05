"""[.mark] Builder partie 3, SA-L3a (sous-lot 2) : la correction en un clic d'un réglage « sans effet ».

La personne (ou le builder) choisit une correction que la liste « Prêt à publier » a proposée. Le serveur relit le brouillon, retrouve
le constat qui propose CETTE correction (jamais un identifiant libre), l'applique au BROUILLON (rien n'est publié), et rend la liste
recalculée. Le graphe passe par la validation du moteur avant d'être écrit ; les réglages par la porte d'écriture du builder
(mêmes validateurs que l'écran).
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.db import db_client
from api.services.publication import sans_effet


class CorrectionIntrouvable(Exception):
    """Le brouillon n'a plus ce constat, ou le constat ne propose pas cette correction."""


async def corriger(
    workflow: Any,
    organisation_id: int,
    correction: str,
    *,
    noeud_id: str | None = None,
    liaison_id: str | None = None,
) -> dict[str, Any]:
    from api.services.builder import reglages_agent
    from api.services.publication import controles, defauts_org

    brouillon = await db_client.get_draft_version(workflow.id)
    if brouillon is None:
        raise CorrectionIntrouvable("There is no draft to fix.")
    configurations = await defauts_org.effectives(organisation_id, getattr(brouillon, "workflow_configurations", None))
    _, constats = await controles._lectures_de_la_liste(workflow, brouillon, organisation_id, configurations)
    demandee = sans_effet.Correction(correction, noeud_id=noeud_id, liaison_id=liaison_id)
    proposee = next(
        (
            c
            for constat in constats
            for c in constat.corrections
            if (c.id, c.noeud_id, c.liaison_id) == (demandee.id, demandee.noeud_id, demandee.liaison_id)
        ),
        None,
    )
    if proposee is None:
        raise CorrectionIntrouvable("This fix is not offered on the draft any more: read the list again.")
    definition = getattr(brouillon, "workflow_json", None) or {}
    nouvelle, ecrits = sans_effet.appliquer(proposee, definition, dict(getattr(brouillon, "workflow_configurations", None) or {}))

    if nouvelle != definition:
        from api.services.workflow.dto import ReactFlowDTO

        try:
            ReactFlowDTO.model_validate(nouvelle)
        except Exception as erreur:  # noqa: BLE001 -- une correction ne publie jamais un graphe que le moteur refuse
            raise sans_effet.CorrectionRefusee("The fix would leave the graph invalid.") from erreur
        await db_client.update_workflow(
            workflow_id=workflow.id,
            name=None,
            workflow_definition=nouvelle,
            template_context_variables=None,
            workflow_configurations=None,
            organization_id=organisation_id,
        )
    if proposee.id == "renvoyer_a_l_accueil":
        await _renvoyer_a_l_accueil(organisation_id, workflow.id, configurations, proposee.noeud_id or "")
    elif ecrits:
        try:
            await reglages_agent.regler(organisation_id, workflow.id, ecrits)
        except reglages_agent.ErreurReglage as erreur:
            raise sans_effet.CorrectionRefusee(str(erreur)) from None
    logger.info(f"[publication] correction « {proposee.id} » écrite dans le brouillon de l'agent {workflow.id}")
    return await controles.evaluer(workflow, await db_client.get_draft_version(workflow.id), organisation_id)


async def _renvoyer_a_l_accueil(organisation_id: int, workflow_id: int, configurations: dict[str, Any], depart: str) -> None:
    """La sortie d'impasse envoie vers l'étape de départ : une règle de phrase de l'agent pour le motif « impasse », qui garde la
    phrase en vigueur et ne change que son « Ensuite »."""
    from api.services.builder import reglages_agent
    from api.services.phrases.catalogue import IMPASSE
    from api.services.phrases.regles import resoudre

    en_vigueur = resoudre(IMPASSE, reglages_agent=configurations, reglages_principal=configurations)
    variantes = list(en_vigueur.variantes) if en_vigueur is not None else []
    regle = {
        "motif": IMPASSE,
        "portee": "agent",
        "variantes": variantes,
        "active": True,
        "ensuite": {"action": "aller_a_une_etape", "destination": depart},
    }
    try:
        await reglages_agent.regler_phrases(organisation_id, workflow_id, [regle])
    except reglages_agent.ErreurReglage as erreur:
        raise sans_effet.CorrectionRefusee(str(erreur)) from None
