from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select
from sqlalchemy.orm import load_only

from api.db.base_client import BaseDBClient
from api.db.models import FolderModel, WorkflowModel
from api.enums import WorkflowStatus


class FolderNameConflictError(Exception):
    """Raised when a folder name already exists within the organization."""


class FolderCycleError(Exception):
    """[.mark] Raised when a folder would become its own ancestor (or its own parent)."""


class FolderClient(BaseDBClient):
    async def create_folder(
        self, name: str, organization_id: int, parent_id: int | None = None
    ) -> FolderModel:
        """Create a folder. [.mark] ``parent_id`` makes it a sub-folder (lot 10, A9); the
        parent must belong to the same organization, otherwise ``ValueError``."""
        async with self.async_session() as session:
            if parent_id is not None:
                parent = (
                    await session.execute(
                        select(FolderModel.id).where(
                            FolderModel.id == parent_id,
                            FolderModel.organization_id == organization_id,
                        )
                    )
                ).scalar_one_or_none()
                if parent is None:
                    raise ValueError(f"Folder with id {parent_id} not found")
            folder = FolderModel(
                name=name, organization_id=organization_id, parent_id=parent_id
            )
            session.add(folder)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise FolderNameConflictError(
                    f"A folder named '{name}' already exists."
                )
            await session.refresh(folder)
        return folder

    async def get_folder(
        self, folder_id: int, organization_id: int
    ) -> FolderModel | None:
        """Fetch a single folder scoped to the organization (tenant isolation)."""
        async with self.async_session() as session:
            result = await session.execute(
                select(FolderModel).where(
                    FolderModel.id == folder_id,
                    FolderModel.organization_id == organization_id,
                )
            )
            return result.scalar_one_or_none()

    async def list_folders(self, organization_id: int) -> list[FolderModel]:
        async with self.async_session() as session:
            result = await session.execute(
                select(FolderModel)
                .where(FolderModel.organization_id == organization_id)
                .order_by(FolderModel.name.asc())
            )
            return result.scalars().all()

    async def rename_folder(
        self, folder_id: int, name: str, organization_id: int
    ) -> FolderModel:
        async with self.async_session() as session:
            result = await session.execute(
                select(FolderModel).where(
                    FolderModel.id == folder_id,
                    FolderModel.organization_id == organization_id,
                )
            )
            folder = result.scalar_one_or_none()
            if folder is None:
                raise ValueError(f"Folder with id {folder_id} not found")

            folder.name = name
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise FolderNameConflictError(
                    f"A folder named '{name}' already exists."
                )
            await session.refresh(folder)
        return folder

    async def move_folder(
        self, folder_id: int, parent_id: int | None, organization_id: int
    ) -> FolderModel:
        """[.mark] Move a folder under another one, or back to the top level (``None``).

        Raises ``ValueError`` if the folder or the target is not in the organization,
        ``FolderCycleError`` if the target is the folder itself or one of its descendants.
        """
        async with self.async_session() as session:
            rows = (
                await session.execute(
                    select(FolderModel.id, FolderModel.parent_id).where(
                        FolderModel.organization_id == organization_id
                    )
                )
            ).all()
            parents = {i: p for i, p in rows}
            if folder_id not in parents:
                raise ValueError(f"Folder with id {folder_id} not found")
            if parent_id is not None:
                if parent_id not in parents:
                    raise ValueError(f"Folder with id {parent_id} not found")
                # On remonte depuis la cible : si on croise le dossier déplacé, c'est un cycle.
                courant: int | None = parent_id
                vus: set[int] = set()
                while courant is not None and courant not in vus:
                    if courant == folder_id:
                        raise FolderCycleError(
                            "A folder cannot be moved into itself or its own sub-folders."
                        )
                    vus.add(courant)
                    courant = parents.get(courant)
            folder = (
                await session.execute(
                    select(FolderModel).where(
                        FolderModel.id == folder_id,
                        FolderModel.organization_id == organization_id,
                    )
                )
            ).scalar_one()
            folder.parent_id = parent_id
            await session.commit()
            await session.refresh(folder)
        return folder

    async def delete_folder(self, folder_id: int, organization_id: int) -> bool:
        """Delete a folder. Member workflows are un-filed (folder_id -> NULL)
        via the ON DELETE SET NULL foreign key, never deleted.

        [.mark] Lot 10 : un sous-dossier qui disparaît **remonte ses agents et ses
        sous-dossiers** dans son parent (dossier de premier niveau : ils deviennent
        « Uncategorized » / de premier niveau, comme avant). Rien n'est supprimé d'autre.
        """
        async with self.async_session() as session:
            result = await session.execute(
                select(FolderModel).where(
                    FolderModel.id == folder_id,
                    FolderModel.organization_id == organization_id,
                )
            )
            folder = result.scalar_one_or_none()
            if folder is None:
                return False

            remonte_vers = folder.parent_id
            await session.execute(
                update(WorkflowModel)
                .where(
                    WorkflowModel.folder_id == folder_id,
                    WorkflowModel.organization_id == organization_id,
                )
                .values(folder_id=remonte_vers)
            )
            await session.execute(
                update(FolderModel)
                .where(
                    FolderModel.parent_id == folder_id,
                    FolderModel.organization_id == organization_id,
                )
                .values(parent_id=remonte_vers)
            )
            await session.delete(folder)
            await session.commit()
        return True

    async def list_workflow_ids_in_folder(
        self, folder_id: int, organization_id: int
    ) -> list[int]:
        """[.mark] The ids of the active workflows directly in a folder (vue de groupe)."""
        async with self.async_session() as session:
            result = await session.execute(
                select(WorkflowModel.id)
                .where(
                    WorkflowModel.organization_id == organization_id,
                    WorkflowModel.folder_id == folder_id,
                    WorkflowModel.status == WorkflowStatus.ACTIVE.value,
                )
                .order_by(WorkflowModel.id.asc())
            )
            return list(result.scalars().all())

    async def get_active_workflow_counts_by_folder(
        self, organization_id: int
    ) -> dict[int, int]:
        """Return {folder_id: active_workflow_count} for the organization.

        Only counts active (non-archived) workflows with a non-NULL folder_id.
        """
        async with self.async_session() as session:
            result = await session.execute(
                select(
                    WorkflowModel.folder_id,
                    func.count(WorkflowModel.id).label("count"),
                )
                .where(
                    WorkflowModel.organization_id == organization_id,
                    WorkflowModel.folder_id.is_not(None),
                    WorkflowModel.status == WorkflowStatus.ACTIVE.value,
                )
                .group_by(WorkflowModel.folder_id)
            )
            return {folder_id: count for folder_id, count in result.all()}

    async def list_agent_configurations(
        self, organization_id: int
    ) -> list[tuple[int, dict]]:
        """[.mark] Lot 10/12 : ``(id, réglages de travail)`` des agents actifs de l'organisation.

        Sert à dresser les groupes (principal et spécialisés) pour la liste d'agents : les
        réglages de travail sont ceux du brouillon s'il existe, sinon de la version publiée
        (la colonne de l'agent suit les deux). Filtré par organisation à la requête.
        """
        async with self.async_session() as session:
            result = await session.execute(
                select(WorkflowModel)
                .options(
                    load_only(WorkflowModel.id, WorkflowModel.workflow_configurations)
                )
                .where(
                    WorkflowModel.organization_id == organization_id,
                    WorkflowModel.status == WorkflowStatus.ACTIVE.value,
                )
                .order_by(WorkflowModel.id.asc())
            )
            return [
                (w.id, dict(w.workflow_configurations or {}))
                for w in result.scalars().all()
            ]
