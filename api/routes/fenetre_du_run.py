"""[.mark] The organization's price table (chantier langwatch-et-fenetre-du-run, lot 2, L5).

``GET`` and ``PUT /organizations/fenetre-du-run``, always in the user's organization. Own router so
that Dograh's ``organization.py`` is not touched. The PUT replaces the whole table; bounds and
« one price per model » are checked before writing (422).
"""

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from api.db.models import UserModel
from api.schemas.fenetre_du_run import ReglagesFenetreDuRun
from api.services.analyse_run.cout import (
    enregistrer_reglages_fenetre,
    lire_reglages_fenetre_stricte,
)
from api.services.auth.depends import get_user_with_selected_organization

router = APIRouter(prefix="/organizations", tags=["organizations-fenetre-du-run"])


@router.get("/fenetre-du-run", response_model=ReglagesFenetreDuRun)
async def get_reglages_fenetre_du_run(
    user: UserModel = Depends(get_user_with_selected_organization),
):
    try:
        return await lire_reglages_fenetre_stricte(user.selected_organization_id)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Price table unreadable for the screen: {erreur!r}")
        raise HTTPException(
            status_code=500,
            detail=(
                "The price table saved for this organization cannot be read. "
                "Nothing was changed; saving now would replace it."
            ),
        ) from None


@router.put("/fenetre-du-run", response_model=ReglagesFenetreDuRun)
async def save_reglages_fenetre_du_run(
    request: ReglagesFenetreDuRun,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    return await enregistrer_reglages_fenetre(user.selected_organization_id, request)
