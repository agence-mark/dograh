"""[.mark] L'équipe .mark (U2 ter) : profil, rôles, membres, invitations, journal, et la page publique « Rejoindre l'équipe ».

Permissions (au registre ``services/equipe_mark/registre_routes.py``) : son propre profil = tout compte ;
lire membres, invitations, rôles et journal = ``equipe.gerer`` ; inviter, changer ou retirer un membre = ``equipe.gerer`` ;
créer, modifier, supprimer un rôle = ``roles.gerer``. Chaque geste d'écriture est écrit au journal par sa route.
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.schemas.auth import AuthResponse, UserResponse
from api.services.auth.depends import get_user, require_local_auth
from api.services.equipe_mark import blocage, equipe
from api.services.equipe_mark import journal as journal_equipe
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
    # Clôture, lot A (D22) : l'interrupteur « Accès actif ».
    acces_actif: bool = True


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


class AccesRequest(BaseModel):
    actif: bool


@router.put("/membres/{user_id}/acces", status_code=204)
async def changer_l_acces_d_un_membre(user_id: int, corps: AccesRequest, user: UserModel = Depends(get_user)) -> None:
    """D22 : bloquer (``actif`` faux) ou rétablir un membre en un clic. Bloqué : sessions et clés coupées à la requête suivante."""
    try:
        await equipe.changer_l_acces_du_membre(user, user_id, corps.actif)
    except ErreurEquipe as e:
        raise _erreur(e) from None
    await journaliser(user, "membre.acces_actif" if corps.actif else "membre.acces_bloque", None, {"membre": user_id})


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
    # Lot 15 (P-1) : le nom à montrer. Un compte sans nom n'a pas d'identifiant brut à l'écran : ``None`` et ``sans_nom`` vrai
    # (l'écran dit « Compte sans nom »). Un geste sans compte (clé d'API du portail) garde son auteur.
    qui: str | None = None
    sans_nom: bool = False
    action: str
    organization_id: int | None
    detail: dict | None
    # Clôture, lot A (D23) : d'où vient le geste (écran, API, MCP) ; vide pour une ligne d'avant.
    origine: str | None = None
    # D23, le « quoi » : le geste (``publier``, ``supprimer``, ``creer``, ``modifier``...) et l'objet touché (type, identifiant, nom ; ``nom`` vide = l'objet
    # n'existe plus). Absents pour une ligne d'avant ou une route sans objet : l'écran retombe sur le libellé du type de geste.
    geste: str | None = None
    cible: dict | None = None


def _ligne_du_journal(ligne: dict, noms: dict | None = None) -> JournalLigne:
    from api.services.equipe_mark import journal_cibles

    extra: dict = {"geste": journal_cibles.verbe_de(ligne.get("detail"))}
    trouvee = journal_cibles.cible_de(ligne.get("detail"))
    if trouvee is not None:
        type_, identifiant = trouvee
        extra["cible"] = {"type": type_, "id": identifiant, "nom": (noms or {}).get((ligne.get("organization_id"), type_, identifiant))}
    nom = " ".join(p for p in (ligne.get("prenom"), ligne.get("nom")) if p)
    if nom:
        return JournalLigne(**ligne, qui=nom, **extra)
    if ligne.get("user_id") is not None:
        return JournalLigne(**ligne, qui=None, sans_nom=True, **extra)
    return JournalLigne(**ligne, qui=ligne.get("auteur"), **extra)


class JournalResponse(BaseModel):
    lignes: list[JournalLigne]
    total: int
    limit: int
    offset: int


@router.get("/journal", response_model=JournalResponse)
async def lire_le_journal(
    organization_id: int | None = Query(None, description="Only this space."),
    membre: int | None = Query(None, description="Only this member (his user id)."),
    action: list[str] | None = Query(None, description="Only these types of gestures (the journal's action names)."),
    origine: Literal["ecran", "api", "mcp"] | None = Query(None, description="Only gestures from this door."),
    depuis: datetime | None = Query(None, description="Not before this moment."),
    jusqu_a: datetime | None = Query(None, description="Strictly before this moment."),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: UserModel = Depends(get_user),
) -> JournalResponse:
    """D23, D24 : le journal complet, paginé, filtrable (personne, client, type de geste, porte, période). Permission « Lire le journal »."""
    lignes, total = await db_client.lister_journal(
        limit=limit,
        offset=offset,
        organization_id=organization_id,
        user_id=membre,
        actions=action,
        origine=origine,
        depuis=depuis,
        jusqu_a=jusqu_a,
    )
    from api.services.equipe_mark import journal_cibles

    demandees = []
    for ligne in lignes:
        trouvee = journal_cibles.cible_de(ligne.get("detail"))
        if trouvee is not None:
            demandees.append((ligne.get("organization_id"), *trouvee))
    noms = await db_client.noms_des_cibles(demandees) if demandees else {}  # une seule requête pour la page
    return JournalResponse(lignes=[_ligne_du_journal(ligne, noms) for ligne in lignes], total=total, limit=limit, offset=offset)


@router.get("/journal/types", response_model=list[str])
async def types_de_gestes(user: UserModel = Depends(get_user)) -> list[str]:
    """Les types de gestes présents dans le journal, pour le filtre de la page."""
    return await db_client.types_de_gestes_du_journal()


# ---------------------------------------------------------------------- réglages de l'équipe (message d'accès bloqué, durée du journal)
class MessageBloqueRequest(BaseModel):
    fr: str = Field(default="", max_length=blocage.MESSAGE_MAX)
    en: str = Field(default="", max_length=blocage.MESSAGE_MAX)


class MessageBloqueResponse(BaseModel):
    fr: str
    en: str
    defaut: dict[str, str]


class DureeJournalRequest(BaseModel):
    mois: int = Field(ge=journal_equipe.DUREE_MIN_MOIS, le=journal_equipe.DUREE_MAX_MOIS)


class ReglagesEquipeResponse(BaseModel):
    message_acces_bloque: MessageBloqueResponse
    journal_mois: int
    journal_mois_min: int = journal_equipe.DUREE_MIN_MOIS
    journal_mois_max: int = journal_equipe.DUREE_MAX_MOIS


async def _reglages() -> ReglagesEquipeResponse:
    return ReglagesEquipeResponse(
        message_acces_bloque=MessageBloqueResponse(**await blocage.reglages_du_message()),
        journal_mois=await journal_equipe.duree_de_garde_en_mois(),
    )


@router.get("/reglages", response_model=ReglagesEquipeResponse)
async def lire_les_reglages(user: UserModel = Depends(get_user)) -> ReglagesEquipeResponse:
    return await _reglages()


@router.put("/reglages/message-acces-bloque", response_model=ReglagesEquipeResponse)
async def regler_le_message_d_acces_bloque(corps: MessageBloqueRequest, user: UserModel = Depends(get_user)) -> ReglagesEquipeResponse:
    """Vide = le message par défaut. Le texte est montré à la connexion d'un membre bloqué."""
    await blocage.regler_le_message(corps.fr, corps.en, user.id)
    await journaliser(user, "reglage.message_acces_bloque", None)
    return await _reglages()


@router.put("/reglages/duree-journal", response_model=ReglagesEquipeResponse)
async def regler_la_duree_du_journal(corps: DureeJournalRequest, user: UserModel = Depends(get_user)) -> ReglagesEquipeResponse:
    await journal_equipe.regler_la_duree(corps.mois, user.id)
    await journaliser(user, "reglage.duree_journal", None, {"mois": corps.mois})
    return await _reglages()


# ---------------------------------------------------------------------- page publique « Rejoindre l'équipe »
class InvitationLueResponse(BaseModel):
    email: str
    role_nom: str
    # Lot 15 (P-3) : qui invite (son nom, jamais son adresse ; ``None`` s'il n'a pas de nom) et jusqu'à quand le lien vaut.
    invite_par: str | None = None
    expire_le: datetime | None = None


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
