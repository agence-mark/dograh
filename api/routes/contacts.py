"""[.mark] Builder partie 3, SA-17c : les trois gestes des contacts du portail, avec la clé du client.

- ``POST /organizations/contacts/{contact_id}/fusionner``  fusionne un doublon dans la fiche qu'il double ;
- ``POST /organizations/contacts/{contact_id}/separer``    « Ce n'est pas la même personne » : le doute est levé, les deux fiches restent ;
- ``PUT  /organizations/contacts/{contact_id}/memoriser``  ``{"memoriser": false}`` : l'agent ne lit plus aucun historique de cette personne.

Permission ``contacts.traiter`` (ouverte à la clé du client). L'organisation est celle de la clé ou de la session, jamais celle du
corps : le contact est relu dans la base de CETTE organisation (404 sinon). L'auteur réel (``X-Mark-Auteur``) va au journal de la base.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.db.bases_clients import contacts as sql
from api.db.bases_clients.connexion import BaseClientIndisponible, connecter
from api.db.models import UserModel
from api.schemas.contacts import ContactFusionne, ContactTraite, MemoriserContact
from api.services.auth.depends import get_user_with_selected_organization
from api.services.base_client import rattachement

router = APIRouter(prefix="/organizations/contacts", tags=["organizations"])


def _refus(message: str, code: int) -> HTTPException:
    return HTTPException(status_code=code, detail=message)


async def _connexion_de(organization_id: int):
    nom = await rattachement.nom_de_la_base(organization_id)
    if not nom:
        raise _refus("Attach a client database first: the contacts live there.", 409)
    try:
        return await connecter(nom)
    except BaseClientIndisponible as erreur:
        raise _refus(str(erreur), 503) from None


async def _geste(user: UserModel, geste):
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de(user.selected_organization_id)
    try:
        try:
            async with _schema_a_jour(connexion):
                return await geste(connexion, rattachement.auteur_de(user))
        except sql.ContactInconnu:
            raise _refus("Contact not found.", 404) from None
        except sql.PasDeDoute as erreur:
            raise _refus(str(erreur), 409) from None
    finally:
        await connexion.close()


@router.post("/{contact_id}/fusionner", response_model=ContactFusionne)
async def post_fusionner(contact_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    """Merge a doubled contact into the one it doubles. 409 when it has no doubt; replayed, it answers the same kept contact."""
    fiche, deja_fait, ancien = await _geste(user, lambda c, auteur: sql.fusionner(c, contact_id, auteur))
    return ContactFusionne(**fiche, fusionne_depuis=ancien, deja_fait=deja_fait)


@router.post("/{contact_id}/separer", response_model=ContactTraite)
async def post_separer(contact_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    """« Not the same person »: the doubt is lifted, both contacts stay. Without doubt, nothing changes."""
    return await _geste(user, lambda c, auteur: sql.separer(c, contact_id, auteur))


@router.put("/{contact_id}/memoriser", response_model=ContactTraite)
async def put_memoriser(
    contact_id: int, corps: MemoriserContact, user: UserModel = Depends(get_user_with_selected_organization)
):
    """Tick or untick « do not memorise this contact ». Idempotent."""
    return await _geste(user, lambda c, auteur: sql.memoriser(c, contact_id, corps.memoriser, auteur))
