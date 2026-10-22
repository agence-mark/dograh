"""[.mark] Lot F7 : les objets de l'agent (D106 à D119), dans la base du client de l'organisation.

- ``GET    /organizations/objets``               tous les objets, leur taille, qui les lit (calculé) et le plafond ;
- ``POST   /organizations/objets``               crée UN objet ;
- ``PUT    /organizations/objets/{objet_id}``    réécrit UN objet (ses colonnes et ses lignes : celles envoyées) ;
- ``DELETE /organizations/objets/{objet_id}``    le supprime (son historique reste, D111) ;
- ``GET    /organizations/objets/utilisation``   « utilisé par », calculé au moment de la demande (D118) ;
- ``GET``/``PUT /organizations/objets/reglages`` le plafond d'un objet en caractères (D112, défaut 3 000).

Le plafond vit dans la base du client et c'est elle qui l'applique (019) : un objet qui le dépasse n'est pas
enregistré (422), que l'écriture vienne d'ici ou du portail. Règle du 22/10 : rien ici ne décide QUI peut
écrire (le portail le fait) ; toutes les routes travaillent dans la base de l'organisation de l'utilisateur ou
de la clé d'API, et l'auteur réel va à l'historique.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.db.bases_clients.connexion import BaseClientIndisponible, connecter
from api.db.models import UserModel
from api.schemas.objets_agent import (
    PLAFOND_PAR_DEFAUT,
    ObjetAgent,
    ObjetEnvoye,
    ObjetsAgent,
    ReglagesObjets,
    UtilisationObjets,
)
from api.services.auth.depends import get_user_with_selected_organization
from api.services.base_client import rattachement
from api.services.objets_agent import stockage
from api.services.objets_agent.rendu import taille

router = APIRouter(prefix="/organizations/objets", tags=["organizations"])


def _refus(message: str, code: int = 422) -> HTTPException:
    return HTTPException(status_code=code, detail=message)


async def _connexion_de(organization_id: int):
    nom = await rattachement.nom_de_la_base(organization_id)
    if not nom:
        raise _refus("Attach a client database first: the objects live there.", 409)
    try:
        return await connecter(nom)
    except BaseClientIndisponible as erreur:
        raise _refus(str(erreur), 503) from None


async def _vue(organization_id: int, connexion) -> ObjetsAgent:
    """Every object with its size and its readers; the readers are written for the portal's view and the
    names kept for a call that cannot read the database."""
    from api.db.bases_clients.objets import (
        ecrire_utilisation,
        lire_objets,
        lire_plafond,
    )
    from api.services.objets_agent.utilisation import calculer_utilisation

    objets = await lire_objets(connexion)
    utilisation = await calculer_utilisation(organization_id, [o.nom for o in objets]) if objets else {}
    if objets:
        await ecrire_utilisation(connexion, {n: [a.id for a in agents] for n, agents in utilisation.items()})
    await stockage.retenir_noms(organization_id, [o.nom for o in objets])
    return ObjetsAgent(
        objets=[
            o.model_copy(update={"taille": taille(o), "utilise_par": utilisation.get(o.nom, [])}) for o in objets
        ],
        plafond_caracteres=await lire_plafond(connexion) or PLAFOND_PAR_DEFAUT,
    )


async def _ecrire(user: UserModel, objet: ObjetEnvoye, objet_id: int | None) -> ObjetAgent:
    from api.db.bases_clients.objets import (
        NomPris,
        ObjetInconnu,
        ObjetRefuse,
        ecrire_objet,
    )
    from api.routes.base_client import _apres_changement_de_source, _schema_a_jour

    organization_id = user.selected_organization_id
    if objet.forme == "valeur" and objet.type is None:
        raise _refus("A single value has a type (text, number, amount, yes/no, date).")
    connexion = await _connexion_de(organization_id)
    try:
        try:
            async with _schema_a_jour(connexion):
                ecrit = await ecrire_objet(connexion, objet, rattachement.auteur_de(user), objet_id)
        except ObjetInconnu:
            raise _refus("Object not found", 404) from None
        except NomPris as erreur:
            raise _refus(str(erreur), 409) from None
        except ObjetRefuse as erreur:
            raise _refus(str(erreur)) from None
        vue = await _vue(organization_id, connexion)
    finally:
        await connexion.close()
    # The calls read the copy: the next pick-up has the new content without waiting for the notification.
    await _apres_changement_de_source(organization_id)
    return next(o for o in vue.objets if o.id == ecrit)


@router.get("", response_model=ObjetsAgent)
async def get_objets(user: UserModel = Depends(get_user_with_selected_organization)):
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de(user.selected_organization_id)
    try:
        async with _schema_a_jour(connexion):
            return await _vue(user.selected_organization_id, connexion)
    finally:
        await connexion.close()


@router.post("", response_model=ObjetAgent)
async def post_objet(request: ObjetEnvoye, user: UserModel = Depends(get_user_with_selected_organization)):
    return await _ecrire(user, request, None)


@router.get("/utilisation", response_model=UtilisationObjets)
async def get_utilisation(user: UserModel = Depends(get_user_with_selected_organization)):
    vue = await get_objets(user)
    return UtilisationObjets(utilisation={o.nom: o.utilise_par for o in vue.objets})


@router.get("/reglages", response_model=ReglagesObjets)
async def get_reglages_objets(user: UserModel = Depends(get_user_with_selected_organization)):
    vue = await get_objets(user)
    return ReglagesObjets(plafond_caracteres=vue.plafond_caracteres)


@router.put("/reglages", response_model=ReglagesObjets)
async def put_reglages_objets(
    request: ReglagesObjets, user: UserModel = Depends(get_user_with_selected_organization)
):
    from api.db.bases_clients.objets import ecrire_plafond, lire_plafond
    from api.routes.base_client import _schema_a_jour

    connexion = await _connexion_de(user.selected_organization_id)
    try:
        async with _schema_a_jour(connexion):
            await ecrire_plafond(connexion, request.plafond_caracteres, rattachement.auteur_de(user))
            return ReglagesObjets(plafond_caracteres=await lire_plafond(connexion) or PLAFOND_PAR_DEFAUT)
    finally:
        await connexion.close()


@router.put("/{objet_id}", response_model=ObjetAgent)
async def put_objet(
    objet_id: int, request: ObjetEnvoye, user: UserModel = Depends(get_user_with_selected_organization)
):
    return await _ecrire(user, request, objet_id)


@router.delete("/{objet_id}")
async def delete_objet(objet_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    from api.db.bases_clients.objets import ObjetInconnu, supprimer_objet
    from api.routes.base_client import _apres_changement_de_source, _schema_a_jour

    connexion = await _connexion_de(user.selected_organization_id)
    try:
        try:
            async with _schema_a_jour(connexion):
                await supprimer_objet(connexion, objet_id, rattachement.auteur_de(user))
        except ObjetInconnu:
            raise _refus("Object not found", 404) from None
    finally:
        await connexion.close()
    await _apres_changement_de_source(user.selected_organization_id)
    return {"supprime": True, "id": objet_id}
