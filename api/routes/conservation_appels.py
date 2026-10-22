"""[.mark] Retention of the calls' copies, on screen and without it (cloture-code-avant-migration, lot 6).

Two routes, scoped to the user's selected organization:

- ``GET /organizations/conservation-appels``  the settings, the installation's audio ceiling and the last
  night's result (strict reading: shown over defaults, the next save would replace the real settings);
- ``PUT /organizations/conservation-appels``  replace the settings. Bounds are checked before writing (422);
  the audio cannot be switched ON while the installation's ceiling forbids it (422, nothing written).

The purge itself is the nightly task (``services/conservation_appels/purge.py``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import ValidationError

from api.db.models import UserModel
from api.schemas.conservation_appels import ReglagesConservationAppels, VueConservationAppels
from api.services.auth.depends import get_user_with_selected_organization
from api.services.conservation_appels import reglages as service

router = APIRouter(prefix="/organizations/conservation-appels", tags=["organizations"])


@router.get("", response_model=VueConservationAppels)
async def get_conservation_des_appels(user: UserModel = Depends(get_user_with_selected_organization)):
    try:
        return await service.vue_de_l_ecran(user.selected_organization_id)
    except (ValidationError, ValueError) as erreur:
        logger.warning(f"[.mark] Retention settings unreadable for the screen: {erreur!r}")
        raise HTTPException(
            status_code=500,
            detail=(
                "The retention settings saved for this organization cannot be read. "
                "Nothing was changed; saving now would replace them."
            ),
        ) from None


@router.put("", response_model=VueConservationAppels)
async def put_conservation_des_appels(
    reglages: ReglagesConservationAppels,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    # Switching the audio ON is what the ceiling forbids; a setting already on (the ceiling came later) can be
    # saved along with other changes, and it records nothing (the call checks the ceiling too).
    if (
        reglages.audio_enregistre
        and not service.audio_autorise_par_l_installation()
        and not (await service.lire_reglages(user.selected_organization_id)).audio_enregistre
    ):
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "msg": "The installation forbids recording the audio (ENABLE_CALL_RECORDING_UPLOAD is off).",
                    "loc": ["body", "audio_enregistre"],
                }
            ],
        )
    await service.enregistrer_reglages(user.selected_organization_id, reglages)
    return await service.vue_de_l_ecran(user.selected_organization_id)
