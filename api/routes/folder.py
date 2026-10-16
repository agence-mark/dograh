from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from api.db import db_client
from api.db.folder_client import FolderCycleError, FolderNameConflictError
from api.db.models import UserModel
from api.services.auth.depends import get_user

router = APIRouter(prefix="/folder")


class FolderResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    # [.mark] Lot 10 (A9) : le dossier parent, None pour un dossier de premier niveau.
    parent_id: int | None = None


class UpdateFolderRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Folder name cannot be empty")
        return v


class CreateFolderRequest(UpdateFolderRequest):
    # [.mark] Lot 10 : créer un sous-dossier. Absent = dossier de premier niveau (comme avant).
    parent_id: int | None = None


class MoveFolderRequest(BaseModel):
    """[.mark] Lot 10 : déplacer un dossier sous un autre (``None`` = premier niveau)."""

    parent_id: int | None = None


def _reponse(f) -> FolderResponse:
    return FolderResponse(
        id=f.id, name=f.name, created_at=f.created_at, parent_id=f.parent_id
    )


@router.get("/")
async def list_folders(
    user: UserModel = Depends(get_user),
) -> list[FolderResponse]:
    """List all folders in the authenticated user's organization.

    [.mark] Liste à plat avec ``parent_id`` : l'écran dresse l'arbre (un dossier dont le
    parent n'est pas de l'organisation n'existe pas ici, la requête filtre par organisation).
    """
    folders = await db_client.list_folders(
        organization_id=user.selected_organization_id
    )
    return [_reponse(f) for f in folders]


@router.post("/")
async def create_folder(
    request: CreateFolderRequest,
    user: UserModel = Depends(get_user),
) -> FolderResponse:
    """Create a new folder in the authenticated user's organization."""
    try:
        folder = await db_client.create_folder(
            name=request.name,
            organization_id=user.selected_organization_id,
            parent_id=request.parent_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FolderNameConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _reponse(folder)


@router.put("/{folder_id}")
async def rename_folder(
    folder_id: int,
    request: UpdateFolderRequest,
    user: UserModel = Depends(get_user),
) -> FolderResponse:
    """Rename a folder owned by the authenticated user's organization."""
    try:
        folder = await db_client.rename_folder(
            folder_id=folder_id,
            name=request.name,
            organization_id=user.selected_organization_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FolderNameConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _reponse(folder)


@router.put("/{folder_id}/parent")
async def move_folder(
    folder_id: int,
    request: MoveFolderRequest,
    user: UserModel = Depends(get_user),
) -> FolderResponse:
    """[.mark] Move a folder under another one of the organization, or to the top level."""
    try:
        folder = await db_client.move_folder(
            folder_id=folder_id,
            parent_id=request.parent_id,
            organization_id=user.selected_organization_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FolderCycleError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _reponse(folder)


@router.delete("/{folder_id}")
async def delete_folder(
    folder_id: int,
    user: UserModel = Depends(get_user),
) -> dict[str, bool]:
    """Delete a folder. Member agents are moved to "Uncategorized", not deleted.

    [.mark] Un sous-dossier remonte ses agents et ses sous-dossiers dans son parent.
    """
    deleted = await db_client.delete_folder(
        folder_id=folder_id,
        organization_id=user.selected_organization_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Folder with id {folder_id} not found"
        )
    return {"success": True}
