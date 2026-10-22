"""[.mark] Lot F3 : les cases des listes de valeurs de l'organisation.

- ``GET /organizations/listes-valeurs``  les listes qui portent une case (réglé seul, opportunité, urgent) ;
- ``PUT /organizations/listes-valeurs``  pose les cases envoyées, valeur par valeur ; l'auteur réel au journal.

Scoped to the selected organization's own database. Nothing here decides WHO may tick a box (the portal does).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.db.bases_clients.connexion import BaseClientIndisponible, connecter
from api.db.models import UserModel
from api.schemas.listes_valeurs import ListesValeurs, ModificationListesValeurs
from api.services.auth.depends import get_user_with_selected_organization
from api.services.base_client import rattachement

router = APIRouter(prefix="/organizations/listes-valeurs", tags=["organizations"])


def _refus(message: str, code: int = 422) -> HTTPException:
    return HTTPException(status_code=code, detail=message)


async def _connexion_de(organization_id: int):
    nom = await rattachement.nom_de_la_base(organization_id)
    if not nom:
        raise _refus("Attach a client database first: the lists live there.", 409)
    try:
        return await connecter(nom)
    except BaseClientIndisponible as erreur:
        raise _refus(str(erreur), 503) from None


@router.get("", response_model=ListesValeurs)
async def get_listes_valeurs(user: UserModel = Depends(get_user_with_selected_organization)):
    from api.db.bases_clients.listes import lire_listes
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de(user.selected_organization_id)
    try:
        async with _schema_a_jour(connexion):
            return await lire_listes(connexion)
    finally:
        await connexion.close()


@router.put("", response_model=ListesValeurs)
async def put_listes_valeurs(
    request: ModificationListesValeurs,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """Tick or untick the boxes sent; the others keep their state. The author recorded in the journal
    is the real one (``X-Mark-Auteur`` for a portal key), as for every other write to the database."""
    from api.db.bases_clients.listes import ValeurInconnue, ecrire_cases, lire_listes
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de(user.selected_organization_id)
    try:
        try:
            async with _schema_a_jour(connexion):
                await ecrire_cases(
                    connexion,
                    [m.model_dump(exclude_unset=True) for m in request.valeurs],
                    rattachement.auteur_de(user),
                )
        except ValeurInconnue as erreur:
            raise _refus(str(erreur)) from None
        return await lire_listes(connexion)
    finally:
        await connexion.close()
