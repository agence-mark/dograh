"""[.mark] Lot F8 : les modules de l'agent (D120 à D122, M4 à M8), lus par le portail et la page de l'agent.

- ``GET /organizations/modules``       le registre : besoins et traducteur branché par besoin, interrupteur,
                                        réglages de construction et terrain, « utilisé par » (calculé) ;
- ``GET /agents/{agent_id}/modules``   la même chose pour un agent de l'organisation, avec ``actif``.

Les deux écrivent aussi le catalogue et « utilisé par » dans la base du client (``v_portail_modules``), sans
jamais échouer pour elle. Règle du 22/10 : rien ici ne décide QUI voit ou règle un module (le portail le fait) ;
tout est lu dans l'organisation de l'utilisateur ou de la clé d'API. Les réglages terrain eux-mêmes se lisent
et s'écrivent où ils vivent (le planificateur : ``/organizations/planificateur``, F4).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.db.models import UserModel
from api.schemas.modules import ModulesAgent, ModulesOrganisation
from api.services.auth.depends import get_user_with_selected_organization
from api.services.modules.lecture import (
    lire_modules,
    lire_modules_de_l_agent,
    synchroniser_modules,
)

router = APIRouter(tags=["organizations"])


@router.get("/organizations/modules", response_model=ModulesOrganisation)
async def get_modules(user: UserModel = Depends(get_user_with_selected_organization)):
    vue = await lire_modules(user.selected_organization_id)
    await synchroniser_modules(user.selected_organization_id, vue)
    return vue


@router.get("/agents/{agent_id}/modules", response_model=ModulesAgent)
async def get_modules_de_l_agent(agent_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    vue = await lire_modules_de_l_agent(user.selected_organization_id, agent_id)
    if vue is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return vue
