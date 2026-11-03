"""[.mark] L'équipe .mark : accès aux tables de rôles, membres, invitations et journal (``models_equipe``).

Toute lecture ou écriture de ce module passe par la base ; la logique (qui a le droit de quoi, un seul
administrateur restant...) vit dans ``api/services/equipe_mark/``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update

from api.db.base_client import BaseDBClient
from api.db.models import OrganizationModel, UserModel
from api.db.models_equipe import (
    MarkInvitationModel,
    MarkJournalModel,
    MarkMembreModel,
    MarkRoleModel,
    MarkRoleOrganisationModel,
    MarkRolePermissionModel,
)


@dataclass(frozen=True)
class AccesCompte:
    """Le rôle d'un compte de l'équipe et ce qu'il ouvre ; un compte sans ligne n'a aucun accès d'équipe."""

    role_id: int
    role_nom: str
    fixe: bool
    labo_ouvert: bool
    tous_les_clients: bool
    permissions: frozenset = field(default_factory=frozenset)
    organisations: frozenset = field(default_factory=frozenset)


class EquipeClient(BaseDBClient):
    # ------------------------------------------------------------------ lecture d'un compte
    async def acces_du_compte(self, user_id: int) -> AccesCompte | None:
        async with self.async_session() as session:
            ligne = (
                await session.execute(
                    select(MarkRoleModel)
                    .join(MarkMembreModel, MarkMembreModel.role_id == MarkRoleModel.id)
                    .where(MarkMembreModel.user_id == user_id)
                )
            ).scalars().first()
            if ligne is None:
                return None
            permissions = (
                await session.execute(
                    select(MarkRolePermissionModel.permission).where(
                        MarkRolePermissionModel.role_id == ligne.id
                    )
                )
            ).scalars().all()
            organisations = (
                await session.execute(
                    select(MarkRoleOrganisationModel.organization_id).where(
                        MarkRoleOrganisationModel.role_id == ligne.id
                    )
                )
            ).scalars().all()
            return AccesCompte(
                role_id=ligne.id,
                role_nom=ligne.nom,
                fixe=bool(ligne.fixe),
                labo_ouvert=bool(ligne.labo_ouvert),
                tous_les_clients=bool(ligne.tous_les_clients),
                permissions=frozenset(permissions),
                organisations=frozenset(organisations),
            )

    async def lister_organisations(self) -> list[tuple[int, str]]:
        """(id, provider_id) de toutes les organisations, par id."""
        async with self.async_session() as session:
            lignes = await session.execute(
                select(OrganizationModel.id, OrganizationModel.provider_id).order_by(
                    OrganizationModel.id
                )
            )
            return [(i, p) for i, p in lignes.all()]

    # ------------------------------------------------------------------ journal
    async def ecrire_journal(
        self,
        *,
        user_id: int | None,
        auteur: str,
        action: str,
        organization_id: int | None = None,
        detail: dict | None = None,
    ) -> None:
        async with self.async_session() as session:
            session.add(
                MarkJournalModel(
                    user_id=user_id,
                    auteur=auteur[:255],
                    action=action[:120],
                    organization_id=organization_id,
                    detail=detail,
                )
            )
            await session.commit()

    async def lister_journal(
        self, *, limit: int, offset: int, organization_id: int | None = None
    ) -> tuple[list[dict], int]:
        """Une page du journal, du plus récent au plus ancien, et le total."""
        async with self.async_session() as session:
            filtre = []
            if organization_id is not None:
                filtre.append(MarkJournalModel.organization_id == organization_id)
            total = (
                await session.execute(
                    select(func.count()).select_from(MarkJournalModel).where(*filtre)
                )
            ).scalar_one()
            lignes = (
                await session.execute(
                    select(
                        MarkJournalModel,
                        MarkMembreModel.prenom,
                        MarkMembreModel.nom,
                    )
                    .outerjoin(
                        MarkMembreModel, MarkMembreModel.user_id == MarkJournalModel.user_id
                    )
                    .where(*filtre)
                    .order_by(MarkJournalModel.quand.desc(), MarkJournalModel.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            return (
                [
                    {
                        "id": j.id,
                        "quand": j.quand,
                        "user_id": j.user_id,
                        "auteur": j.auteur,
                        "prenom": prenom,
                        "nom": nom,
                        "action": j.action,
                        "organization_id": j.organization_id,
                        "detail": j.detail,
                    }
                    for j, prenom, nom in lignes
                ],
                int(total),
            )

    # ------------------------------------------------------------------ rôles
    async def lister_roles(self) -> list[dict]:
        async with self.async_session() as session:
            roles = (
                await session.execute(select(MarkRoleModel).order_by(MarkRoleModel.id))
            ).scalars().all()
            permissions = (
                await session.execute(select(MarkRolePermissionModel))
            ).scalars().all()
            organisations = (
                await session.execute(select(MarkRoleOrganisationModel))
            ).scalars().all()
            effectifs = dict(
                (
                    await session.execute(
                        select(MarkMembreModel.role_id, func.count()).group_by(
                            MarkMembreModel.role_id
                        )
                    )
                ).all()
            )
            return [
                {
                    "id": r.id,
                    "nom": r.nom,
                    "fixe": bool(r.fixe),
                    "labo_ouvert": bool(r.labo_ouvert),
                    "tous_les_clients": bool(r.tous_les_clients),
                    "permissions": sorted(
                        p.permission for p in permissions if p.role_id == r.id
                    ),
                    "organisations": sorted(
                        o.organization_id for o in organisations if o.role_id == r.id
                    ),
                    "membres": int(effectifs.get(r.id, 0)),
                }
                for r in roles
            ]

    async def obtenir_role(self, role_id: int) -> dict | None:
        return next((r for r in await self.lister_roles() if r["id"] == role_id), None)

    async def creer_role(
        self,
        *,
        nom: str,
        labo_ouvert: bool,
        tous_les_clients: bool,
        permissions: list[str],
        organisations: list[int],
    ) -> int:
        async with self.async_session() as session:
            role = MarkRoleModel(
                nom=nom,
                fixe=False,
                labo_ouvert=labo_ouvert,
                tous_les_clients=tous_les_clients,
            )
            session.add(role)
            await session.flush()
            session.add_all(
                MarkRolePermissionModel(role_id=role.id, permission=p) for p in permissions
            )
            session.add_all(
                MarkRoleOrganisationModel(role_id=role.id, organization_id=o)
                for o in organisations
            )
            await session.commit()
            return role.id

    async def modifier_role(
        self,
        role_id: int,
        *,
        nom: str,
        labo_ouvert: bool,
        tous_les_clients: bool,
        permissions: list[str],
        organisations: list[int],
    ) -> None:
        async with self.async_session() as session:
            await session.execute(
                update(MarkRoleModel)
                .where(MarkRoleModel.id == role_id)
                .values(nom=nom, labo_ouvert=labo_ouvert, tous_les_clients=tous_les_clients)
            )
            await session.execute(
                delete(MarkRolePermissionModel).where(MarkRolePermissionModel.role_id == role_id)
            )
            await session.execute(
                delete(MarkRoleOrganisationModel).where(
                    MarkRoleOrganisationModel.role_id == role_id
                )
            )
            session.add_all(
                MarkRolePermissionModel(role_id=role_id, permission=p) for p in permissions
            )
            session.add_all(
                MarkRoleOrganisationModel(role_id=role_id, organization_id=o)
                for o in organisations
            )
            await session.commit()

    async def supprimer_role(self, role_id: int) -> None:
        async with self.async_session() as session:
            await session.execute(delete(MarkRoleModel).where(MarkRoleModel.id == role_id))
            await session.commit()

    # ------------------------------------------------------------------ membres
    async def poser_membre(
        self,
        user_id: int,
        role_id: int,
        *,
        prenom: str | None = None,
        nom: str | None = None,
    ) -> None:
        async with self.async_session() as session:
            membre = await session.get(MarkMembreModel, user_id)
            if membre is None:
                session.add(
                    MarkMembreModel(user_id=user_id, role_id=role_id, prenom=prenom, nom=nom)
                )
            else:
                membre.role_id = role_id
                if prenom is not None:
                    membre.prenom = prenom
                if nom is not None:
                    membre.nom = nom
            await session.commit()

    async def retirer_membre(self, user_id: int) -> None:
        async with self.async_session() as session:
            await session.execute(
                delete(MarkMembreModel).where(MarkMembreModel.user_id == user_id)
            )
            await session.commit()

    async def obtenir_membre(self, user_id: int) -> dict | None:
        async with self.async_session() as session:
            ligne = (
                await session.execute(
                    select(MarkMembreModel, UserModel.email, MarkRoleModel.nom)
                    .join(UserModel, UserModel.id == MarkMembreModel.user_id)
                    .join(MarkRoleModel, MarkRoleModel.id == MarkMembreModel.role_id)
                    .where(MarkMembreModel.user_id == user_id)
                )
            ).first()
            if ligne is None:
                return None
            m, email, role_nom = ligne
            return {
                "user_id": m.user_id,
                "email": email,
                "prenom": m.prenom,
                "nom": m.nom,
                "role_id": m.role_id,
                "role_nom": role_nom,
            }

    async def lister_membres(self, *, limit: int, offset: int) -> tuple[list[dict], int]:
        async with self.async_session() as session:
            total = (
                await session.execute(select(func.count()).select_from(MarkMembreModel))
            ).scalar_one()
            lignes = (
                await session.execute(
                    select(MarkMembreModel, UserModel.email, MarkRoleModel.nom)
                    .join(UserModel, UserModel.id == MarkMembreModel.user_id)
                    .join(MarkRoleModel, MarkRoleModel.id == MarkMembreModel.role_id)
                    .order_by(MarkMembreModel.cree_le, MarkMembreModel.user_id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            return (
                [
                    {
                        "user_id": m.user_id,
                        "email": email,
                        "prenom": m.prenom,
                        "nom": m.nom,
                        "role_id": m.role_id,
                        "role_nom": role_nom,
                    }
                    for m, email, role_nom in lignes
                ],
                int(total),
            )

    async def lister_utilisateurs_du_role(self, role_id: int) -> list[int]:
        async with self.async_session() as session:
            return list(
                (
                    await session.execute(
                        select(MarkMembreModel.user_id).where(MarkMembreModel.role_id == role_id)
                    )
                ).scalars()
            )

    async def compter_membres_du_role(self, role_id: int) -> int:
        async with self.async_session() as session:
            return int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(MarkMembreModel)
                        .where(MarkMembreModel.role_id == role_id)
                    )
                ).scalar_one()
            )

    async def compter_membres(self) -> int:
        async with self.async_session() as session:
            return int(
                (await session.execute(select(func.count()).select_from(MarkMembreModel))).scalar_one()
            )

    async def compter_comptes(self) -> int:
        async with self.async_session() as session:
            return int((await session.execute(select(func.count()).select_from(UserModel))).scalar_one())

    # ------------------------------------------------------------------ invitations
    async def creer_invitation(
        self,
        *,
        email: str,
        role_id: int,
        empreinte_jeton: str,
        cree_par: int | None,
        expire_le: datetime,
    ) -> int:
        async with self.async_session() as session:
            invitation = MarkInvitationModel(
                email=email.lower(),
                role_id=role_id,
                empreinte_jeton=empreinte_jeton,
                cree_par=cree_par,
                expire_le=expire_le,
            )
            session.add(invitation)
            await session.commit()
            return invitation.id

    async def invitation_par_empreinte(self, empreinte_jeton: str) -> dict | None:
        async with self.async_session() as session:
            i = (
                await session.execute(
                    select(MarkInvitationModel).where(
                        MarkInvitationModel.empreinte_jeton == empreinte_jeton
                    )
                )
            ).scalars().first()
            if i is None:
                return None
            return {
                "id": i.id,
                "email": i.email,
                "role_id": i.role_id,
                "expire_le": i.expire_le,
                "utilisee_le": i.utilisee_le,
            }

    async def consommer_invitation(self, empreinte_jeton: str) -> dict | None:
        """Marque l'invitation utilisée SI elle est encore valable (une seule fois, atomique), et la rend ; sinon ``None``."""
        async with self.async_session() as session:
            maintenant = datetime.now(UTC)
            ligne = (
                await session.execute(
                    update(MarkInvitationModel)
                    .where(
                        MarkInvitationModel.empreinte_jeton == empreinte_jeton,
                        MarkInvitationModel.utilisee_le.is_(None),
                        MarkInvitationModel.expire_le > maintenant,
                    )
                    .values(utilisee_le=maintenant)
                    .returning(MarkInvitationModel.id, MarkInvitationModel.email, MarkInvitationModel.role_id)
                )
            ).first()
            await session.commit()
            if ligne is None:
                return None
            return {"id": ligne[0], "email": ligne[1], "role_id": ligne[2]}

    async def lister_invitations_ouvertes(self, *, limit: int, offset: int) -> tuple[list[dict], int]:
        async with self.async_session() as session:
            maintenant = datetime.now(UTC)
            filtre = (
                MarkInvitationModel.utilisee_le.is_(None),
                MarkInvitationModel.expire_le > maintenant,
            )
            total = (
                await session.execute(
                    select(func.count()).select_from(MarkInvitationModel).where(*filtre)
                )
            ).scalar_one()
            lignes = (
                await session.execute(
                    select(MarkInvitationModel, MarkRoleModel.nom)
                    .join(MarkRoleModel, MarkRoleModel.id == MarkInvitationModel.role_id)
                    .where(*filtre)
                    .order_by(MarkInvitationModel.cree_le.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            return (
                [
                    {
                        "id": i.id,
                        "email": i.email,
                        "role_id": i.role_id,
                        "role_nom": role_nom,
                        "expire_le": i.expire_le,
                    }
                    for i, role_nom in lignes
                ],
                int(total),
            )

    async def annuler_invitation(self, invitation_id: int) -> bool:
        async with self.async_session() as session:
            resultat = await session.execute(
                delete(MarkInvitationModel).where(
                    MarkInvitationModel.id == invitation_id,
                    MarkInvitationModel.utilisee_le.is_(None),
                )
            )
            await session.commit()
            return resultat.rowcount > 0
