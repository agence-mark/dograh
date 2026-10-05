"""[.mark] The organization's price table (chantier langwatch-et-fenetre-du-run, lot 2, L5).

``GET`` and ``PUT /organizations/table-des-prix``, always in the user's organization. Own router so
that Dograh's ``organization.py`` is not touched. The PUT replaces the whole table; bounds and
« one price per model » are checked before writing (422).
"""

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from api.db.models import UserModel
from api.schemas.table_des_prix import TableDesPrix
from api.services.analyse_run.cout import (
    enregistrer_table_des_prix,
    lire_table_des_prix_stricte,
)
from api.services.auth.depends import get_user_with_selected_organization

router = APIRouter(prefix="/organizations", tags=["organizations-table-des-prix"])


@router.get("/table-des-prix", response_model=TableDesPrix)
async def get_table_des_prix(
    user: UserModel = Depends(get_user_with_selected_organization),
):
    try:
        return await lire_table_des_prix_stricte(user.selected_organization_id)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Price table unreadable for the screen: {erreur!r}")
        raise HTTPException(
            status_code=500,
            detail=(
                "The price table saved for this organization cannot be read. "
                "Nothing was changed; saving now would replace it."
            ),
        ) from None


@router.put("/table-des-prix", response_model=TableDesPrix)
async def save_table_des_prix(
    request: TableDesPrix,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    return await enregistrer_table_des_prix(user.selected_organization_id, request)
