"""[.mark] Builder partie 2, lot K7 : ce que lisent les onglets Builder IA, Appelant simulé et Juge des Réglages du Labo.

- ``GET /builder/cerveaux``   le prompt système de chaque cerveau (version et statut en bibliothèque), ce qu'il reçoit, les deux portes,
                              la dépense du mois face au plafond, les limites du juge. Lecture seule, équipe .mark.

Les réglages qui s'écrivent gardent leurs routes : ``PUT /builder/cerveau`` (le plafond du mois y est) et ``PUT /builder/options``
(l'interrupteur du builder et les deux portes).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.db.models import UserModel
from api.services.auth.depends import get_user_with_selected_organization
from api.services.builder import vue_cerveaux
from api.services.builder.bibliotheque import droits
from api.services.builder.bibliotheque.service import ErreurBibliotheque
from api.services.builder.cerveau import reglages as reglages_cerveau

router = APIRouter(tags=["builder"])


@router.get("/cerveaux", response_model=vue_cerveaux.VueCerveaux)
async def lire_les_cerveaux(user: UserModel = Depends(get_user_with_selected_organization)):
    try:
        await droits.exiger_l_equipe(user)
    except ErreurBibliotheque as erreur:
        raise HTTPException(status_code=erreur.statut, detail=str(erreur)) from None
    return await vue_cerveaux.lire(user, await reglages_cerveau.organisation_des_reglages(user))
