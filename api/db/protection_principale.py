"""[.mark] Partie 3, SA-L3c (05 § 12) : la branche principale PROTÉGÉE (on n'y entre que par une fusion relue).

Règle : la principale d'un agent est protégée quand (a) son drapeau ``protegee`` est posé, ou (b) l'agent est un agent CLIENT EN LIGNE
(une version publiée PAR UNE PERSONNE après la création, dans une organisation qui n'est pas le Labo). Le Labo n'est pas protégé par défaut. Sans Labo réglé
(poste de développement), on ne devine pas : seul le drapeau compte.

Le refus est posé dans la couche de données, sur les trois gestes qui écrivent le brouillon de la principale ou la version en ligne
(enregistrer, revenir à une version, publier) : l'éditeur, le builder, les routes de réglages, les modèles, la restauration et le
groupe passent tous par là, aucun ne peut l'oublier. Les branches ne sont pas concernées. La fusion écrit par sa propre transaction
(``BranchesClient.appliquer_la_fusion``), jamais par ces trois gestes.
"""

from __future__ import annotations

from sqlalchemy import func, select

from api.db.models import WorkflowDefinitionModel, WorkflowModel
from api.db.models_builder import WorkflowBranchModel

MESSAGE = "The main branch is protected: make your changes on a branch, then merge it after a review."


class PrincipaleProtegee(Exception):
    """Un refus normal (409) : l'écran le traduit, le builder le dit au cerveau."""

    code = "principale_protegee"

    def __init__(self, message: str = MESSAGE):
        super().__init__(message)


async def est_protegee(session, workflow_id: int) -> bool:
    ligne = (
        await session.execute(
            select(WorkflowModel.organization_id, WorkflowModel.released_definition_id).where(WorkflowModel.id == workflow_id)
        )
    ).first()
    if ligne is None:
        return False
    organisation, en_ligne = ligne
    drapeau = await session.scalar(
        select(WorkflowBranchModel.protegee).where(
            WorkflowBranchModel.organization_id == organisation,
            WorkflowBranchModel.workflow_id == workflow_id,
            WorkflowBranchModel.est_principale.is_(True),
        )
    )
    if drapeau:
        return True
    if en_ligne is None:
        return False
    # [.mark] « En ligne » = publié par une personne : la version 1 posée à la création (recette, Nouveau client, groupe) ne
    # compte pas, sinon un agent neuf naît protégé et ne se construit plus (constat de SA-7). Il faut au moins une
    # publication de la principale après la création (les versions des branches portent un ``branch_id``).
    publiees = await session.scalar(
        select(func.count())
        .select_from(WorkflowDefinitionModel)
        .where(
            WorkflowDefinitionModel.workflow_id == workflow_id,
            WorkflowDefinitionModel.branch_id.is_(None),
            WorkflowDefinitionModel.status.in_(["published", "archived"]),
        )
    )
    if (publiees or 0) < 2:
        return False
    from api.services.builder.constantes import organisation_bibliotheque

    labo = organisation_bibliotheque()
    return labo is not None and organisation != labo


async def exiger_modifiable(session, workflow_id: int) -> None:
    if await est_protegee(session, workflow_id):
        raise PrincipaleProtegee()
