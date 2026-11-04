"""[.mark] L'équipe .mark (U2 ter) : profil, rôles, membres, invitations, journal, et la page publique « Rejoindre l'équipe ».

Permissions (au registre ``services/equipe_mark/registre_routes.py``) : son propre profil = tout compte ;
lire membres, invitations, rôles et journal = ``equipe.gerer`` ; inviter, changer ou retirer un membre = ``equipe.gerer`` ;
créer, modifier, supprimer un rôle = ``roles.gerer``. Chaque geste d'écriture est écrit au journal par sa route.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.schemas.auth import AuthResponse, UserResponse
from api.services.auth.depends import get_user, require_local_auth
from api.services.equipe_mark import equipe
from api.services.equipe_mark.acces import journaliser
from api.services.equipe_mark.equipe import ErreurEquipe

router = APIRouter(prefix="/equipe-mark", tags=["equipe-mark"])
routeur_public = APIRouter(
    prefix="/auth/invitation", tags=["equipe-mark"], dependencies=[Depends(require_local_auth)]
)


def _erreur(e: ErreurEquipe) -> HTTPException:
    return HTTPException(status_code=e.statut, detail=e.message)


# ---------------------------------------------------------------------- profil
class ProfilResponse(BaseModel):
    id: int
    email: str | None
    prenom: str | None
    nom: str | None
    role: str | None
    permissions: list[str]
    langue: str
    alertes_mail: bool


class ModifierProfilRequest(BaseModel):
    prenom: str | None = Field(default=None, max_length=120)
    nom: str | None = Field(default=None, max_length=120)
    langue: str | None = None
    alertes_mail: bool | None = None


class MotDePasseRequest(BaseModel):
    actuel: str
    nouveau: str


@router.get("/moi", response_model=ProfilResponse)
async def mon_profil(user: UserModel = Depends(get_user)) -> ProfilResponse:
    return ProfilResponse(**await equipe.mon_profil(user))


@router.patch("/moi", response_model=ProfilResponse)
async def modifier_mon_profil(corps: ModifierProfilRequest, user: UserModel = Depends(get_user)) -> ProfilResponse:
    try:
        profil = await equipe.modifier_profil(
            user,
            prenom=corps.prenom,
            nom=corps.nom,
            langue=corps.langue,
            alertes_mail=corps.alertes_mail,
            champs=set(corps.model_fields_set),
        )
    except ErreurEquipe as e:
        raise _erreur(e) from None
    return ProfilResponse(**profil)


@router.post("/moi/mot-de-passe", status_code=204)
async def changer_mon_mot_de_passe(corps: MotDePasseRequest, user: UserModel = Depends(get_user)) -> None:
    try:
        await equipe.changer_mot_de_passe(user, corps.actuel, corps.nouveau)
    except ErreurEquipe as e:
        raise _erreur(e) from None
    await journaliser(user, "profil.mot_de_passe", None)


class PermissionResponse(BaseModel):
    cle: str
    groupe: str
    libelle: str


@router.get("/permissions", response_model=list[PermissionResponse])
async def catalogue(user: UserModel = Depends(get_user)) -> list[PermissionResponse]:
    return [PermissionResponse(**p) for p in equipe.catalogue_des_permissions()]


# ---------------------------------------------------------------------- rôles
class RoleResponse(BaseModel):
    id: int
    nom: str
    fixe: bool
    labo_ouvert: bool
    tous_les_clients: bool
    permissions: list[str]
    organisations: list[int]
    membres: int


class RoleRequest(BaseModel):
    nom: str = Field(min_length=1, max_length=80)
    labo_ouvert: bool = False
    tous_les_clients: bool = False
    permissions: list[str] = Field(default_factory=list)
    organisations: list[int] = Field(default_factory=list)


@router.get("/roles", response_model=list[RoleResponse])
async def lister_les_roles(user: UserModel = Depends(get_user)) -> list[RoleResponse]:
    return [RoleResponse(**r) for r in await db_client.lister_roles()]


@router.post("/roles", response_model=RoleResponse, status_code=201)
async def creer_un_role(corps: RoleRequest, user: UserModel = Depends(get_user)) -> RoleResponse:
    try:
        role_id = await equipe.creer_role(
            corps.nom, corps.permissions, corps.organisations, corps.labo_ouvert, corps.tous_les_clients
        )
    except ErreurEquipe as e:
        raise _erreur(e) from None
    await journaliser(user, "role.creer", None, {"role": corps.nom})
    return RoleResponse(**await db_client.obtenir_role(role_id))


@router.put("/roles/{role_id}", response_model=RoleResponse)
async def modifier_un_role(role_id: int, corps: RoleRequest, user: UserModel = Depends(get_user)) -> RoleResponse:
    try:
        await equipe.modifier_role(
            role_id, corps.nom, corps.permissions, corps.organisations, corps.labo_ouvert, corps.tous_les_clients
        )
    except ErreurEquipe as e:
        raise _erreur(e) from None
    await journaliser(user, "role.modifier", None, {"role": corps.nom})
    return RoleResponse(**await db_client.obtenir_role(role_id))


@router.delete("/roles/{role_id}", status_code=204)
async def supprimer_un_role(role_id: int, user: UserModel = Depends(get_user)) -> None:
    role = await db_client.obtenir_role(role_id)
    try:
        await equipe.supprimer_role(role_id)
    except ErreurEquipe as e:
        raise _erreur(e) from None
    await journaliser(user, "role.supprimer", None, {"role": role["nom"] if role else role_id})


# ---------------------------------------------------------------------- membres
class MembreResponse(BaseModel):
    user_id: int
    email: str | None
    prenom: str | None
    nom: str | None
    role_id: int
    role_nom: str
    # V4 : la date d'entrée dans l'équipe (``mark_membres.cree_le``), pour la colonne « Depuis ».
    depuis: datetime | None = None


class MembresResponse(BaseModel):
    membres: list[MembreResponse]
    total: int
    limit: int
    offset: int


class ChangerRoleRequest(BaseModel):
    role_id: int


@router.get("/membres", response_model=MembresResponse)
async def lister_les_membres(
    limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0), user: UserModel = Depends(get_user)
) -> MembresResponse:
    lignes, total = await db_client.lister_membres(limit=limit, offset=offset)
    return MembresResponse(membres=[MembreResponse(**m) for m in lignes], total=total, limit=limit, offset=offset)


@router.put("/membres/{user_id}/role", status_code=204)
async def changer_le_role_d_un_membre(
    user_id: int, corps: ChangerRoleRequest, user: UserModel = Depends(get_user)
) -> None:
    try:
        await equipe.changer_role_du_membre(user_id, corps.role_id)
    except ErreurEquipe as e:
        raise _erreur(e) from None
    await journaliser(user, "membre.role", None, {"membre": user_id, "role": corps.role_id})


@router.delete("/membres/{user_id}", status_code=204)
async def retirer_un_membre(user_id: int, user: UserModel = Depends(get_user)) -> None:
    try:
        await equipe.changer_role_du_membre(user_id, None)
    except ErreurEquipe as e:
        raise _erreur(e) from None
    await journaliser(user, "membre.retirer", None, {"membre": user_id})


# ---------------------------------------------------------------------- invitations
class InvitationRequest(BaseModel):
    email: str = Field(max_length=320)
    role_id: int


class InvitationCreeeResponse(BaseModel):
    id: int
    email: str
    role_nom: str
    expire_le: datetime
    lien: str
    envoye: bool


class InvitationResponse(BaseModel):
    id: int
    email: str
    role_id: int
    role_nom: str
    expire_le: datetime


class InvitationsResponse(BaseModel):
    invitations: list[InvitationResponse]
    total: int
    limit: int
    offset: int


@router.post("/invitations", response_model=InvitationCreeeResponse, status_code=201)
async def inviter(corps: InvitationRequest, user: UserModel = Depends(get_user)) -> InvitationCreeeResponse:
    try:
        invitation = await equipe.inviter(user, corps.email, corps.role_id)
    except ErreurEquipe as e:
        raise _erreur(e) from None
    # Le jeton n'est jamais journalisé : seulement l'adresse invitée et le rôle.
    await journaliser(user, "invitation.creer", None, {"email": invitation["email"], "role": invitation["role_nom"]})
    return InvitationCreeeResponse(**invitation)


@router.get("/invitations", response_model=InvitationsResponse)
async def lister_les_invitations(
    limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0), user: UserModel = Depends(get_user)
) -> InvitationsResponse:
    lignes, total = await db_client.lister_invitations_ouvertes(limit=limit, offset=offset)
    return InvitationsResponse(
        invitations=[InvitationResponse(**i) for i in lignes], total=total, limit=limit, offset=offset
    )


@router.delete("/invitations/{invitation_id}", status_code=204)
async def annuler_une_invitation(invitation_id: int, user: UserModel = Depends(get_user)) -> None:
    if not await db_client.annuler_invitation(invitation_id):
        raise HTTPException(status_code=404, detail="Invitation not found")
    await journaliser(user, "invitation.annuler", None, {"invitation": invitation_id})


# ---------------------------------------------------------------------- journal
class JournalLigne(BaseModel):
    id: int
    quand: datetime
    user_id: int | None
    auteur: str
    prenom: str | None
    nom: str | None
    action: str
    organization_id: int | None
    detail: dict | None


class JournalResponse(BaseModel):
    lignes: list[JournalLigne]
    total: int
    limit: int
    offset: int


@router.get("/journal", response_model=JournalResponse)
async def lire_le_journal(
    organization_id: int | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: UserModel = Depends(get_user),
) -> JournalResponse:
    lignes, total = await db_client.lister_journal(limit=limit, offset=offset, organization_id=organization_id)
    return JournalResponse(lignes=[JournalLigne(**ligne) for ligne in lignes], total=total, limit=limit, offset=offset)


# ---------------------------------------------------------------------- page publique « Rejoindre l'équipe »
class InvitationLueResponse(BaseModel):
    email: str
    role_nom: str


class AccepterRequest(BaseModel):
    prenom: str = Field(min_length=1, max_length=120)
    nom: str = Field(min_length=1, max_length=120)
    mot_de_passe: str


@routeur_public.get("/{jeton}", response_model=InvitationLueResponse)
async def lire_une_invitation(jeton: str) -> InvitationLueResponse:
    try:
        return InvitationLueResponse(**await equipe.lire_invitation(jeton))
    except ErreurEquipe as e:
        raise _erreur(e) from None


@routeur_public.post("/{jeton}/accepter", response_model=AuthResponse)
async def accepter_une_invitation(jeton: str, corps: AccepterRequest) -> AuthResponse:
    try:
        user, token = await equipe.accepter_invitation(jeton, corps.prenom, corps.nom, corps.mot_de_passe)
    except ErreurEquipe as e:
        raise _erreur(e) from None
    await journaliser(user, "invitation.accepter", None)
    return AuthResponse(
        token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=f"{corps.prenom} {corps.nom}".strip(),
            organization_id=user.selected_organization_id,
            provider_id=user.provider_id,
        ),
    )
