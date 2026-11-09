"""[.mark] L'équipe .mark en tables : rôles, permissions, rôle de chaque membre, invitations, journal.

Dans un module à part (et non dans ``models.py``) : le moins de fichiers d'amont touchés possible. La migration
``mark_equipe_roles`` crée ces six tables ; rien d'amont n'est modifié.

* un rôle = un nom, les espaces qu'il ouvre (le Labo, tous les clients, ou des clients choisis) et ses permissions ;
* un membre = un compte (``users``) et son rôle ; un compte sans ligne ici n'a AUCUNE permission d'écriture ;
* une invitation ne garde jamais le jeton : seulement son empreinte (SHA-256) ;
* le journal dit qui, quoi, quel espace, quand (l'auteur est l'identifiant du compte, jamais une adresse).
"""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)

from api.db.models import Base


def _maintenant():
    return datetime.now(UTC)


class MarkRoleModel(Base):
    __tablename__ = "mark_roles"

    id = Column(Integer, primary_key=True)
    nom = Column(String(80), nullable=False)
    # Le rôle Administrateur : non modifiable, non supprimable, il en reste toujours un.
    fixe = Column(Boolean, nullable=False, default=False, server_default="false")
    labo_ouvert = Column(Boolean, nullable=False, default=False, server_default="false")
    tous_les_clients = Column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    cree_le = Column(DateTime(timezone=True), nullable=False, default=_maintenant)

    __table_args__ = (
        Index("ux_mark_roles_nom_lower", func.lower(nom), unique=True),
    )


class MarkRolePermissionModel(Base):
    __tablename__ = "mark_role_permissions"

    role_id = Column(
        Integer, ForeignKey("mark_roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission = Column(String(64), primary_key=True)


class MarkRoleOrganisationModel(Base):
    """Les clients choisis qu'un rôle ouvre (sans effet quand ``tous_les_clients`` est vrai)."""

    __tablename__ = "mark_role_organisations"

    role_id = Column(
        Integer, ForeignKey("mark_roles.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )


class MarkMembreModel(Base):
    __tablename__ = "mark_membres"

    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id = Column(Integer, ForeignKey("mark_roles.id"), nullable=False)
    prenom = Column(String(120), nullable=True)
    nom = Column(String(120), nullable=True)
    cree_le = Column(DateTime(timezone=True), nullable=False, default=_maintenant)
    # Clôture, lot A (D22) : « Accès actif », sans date. Bloqué = sessions et clés du compte coupées à la requête suivante ; permissions gardées.
    acces_actif = Column(Boolean, nullable=False, default=True, server_default="true")
    bloque_le = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_mark_membres_role_id", "role_id"),)


class MarkInvitationModel(Base):
    __tablename__ = "mark_invitations"

    id = Column(Integer, primary_key=True)
    email = Column(String(320), nullable=False)
    role_id = Column(Integer, ForeignKey("mark_roles.id"), nullable=False)
    # SHA-256 du jeton : le jeton lui-même n'est jamais écrit en base.
    empreinte_jeton = Column(String(64), nullable=False)
    cree_par = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cree_le = Column(DateTime(timezone=True), nullable=False, default=_maintenant)
    expire_le = Column(DateTime(timezone=True), nullable=False)
    utilisee_le = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("empreinte_jeton", name="uq_mark_invitations_empreinte"),
        Index("ix_mark_invitations_email", func.lower(email)),
    )


class MarkJournalModel(Base):
    __tablename__ = "mark_journal"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    quand = Column(DateTime(timezone=True), nullable=False, default=_maintenant)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Copie de l'identifiant du compte au moment du geste (survit à la suppression du compte).
    auteur = Column(String(255), nullable=False)
    action = Column(String(120), nullable=False)
    # L'espace touché : organisation sans clé étrangère, l'historique survit à sa suppression.
    organization_id = Column(Integer, nullable=True)
    detail = Column(JSON, nullable=True)
    # Clôture, lot A (D23) : d'où vient le geste, ``ecran`` (session), ``api`` (clé d'API) ou ``mcp`` (porte MCP).
    origine = Column(String(8), nullable=True)

    __table_args__ = (
        Index("ix_mark_journal_action", "action"),
        Index("ix_mark_journal_quand", "quand"),
        Index("ix_mark_journal_organization_id", "organization_id"),
    )


class MarkReglageEquipeModel(Base):
    """Les réglages de l'équipe .mark réglables à l'écran (message d'accès bloqué, durée du journal) : une clé, une valeur JSON."""

    __tablename__ = "mark_reglages_equipe"

    cle = Column(String(64), primary_key=True)
    valeur = Column(JSON, nullable=True)
    modifie_le = Column(DateTime(timezone=True), nullable=False, default=_maintenant)
    modifie_par = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
