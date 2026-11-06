"""[.mark] Partie 3, sous-lot 9 (SE-5) : l'installation d'un nouveau client (migration ``e5a1c3f7b2d9``).

Une installation par organisation cliente, neuf étapes chacune. Une seule installation ouverte par client (index unique
partiel). Aucun secret n'est rangé ici : la clé d'API et le mot de passe du portail sont montrés une fois, jamais écrits.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from api.db.models import Base


class InstallationClientModel(Base):
    __tablename__ = "mark_installations_client"
    __table_args__ = (
        CheckConstraint("etat IN ('ouverte', 'terminee', 'abandonnee')", name="ck_mark_installations_client_etat"),
        Index("uq_mark_installations_client_ouverte", "organization_id", unique=True, postgresql_where=text("etat = 'ouverte'")),
    )

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    nom = Column(String(100), nullable=False)
    etat = Column(String(12), nullable=False, default="ouverte", server_default="ouverte")
    cree_par = Column(Integer, nullable=True)
    cree_le = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), default=lambda: datetime.now(UTC))
    terminee_le = Column(DateTime(timezone=True), nullable=True)


class EtapeInstallationModel(Base):
    __tablename__ = "mark_installations_client_etapes"
    __table_args__ = (
        UniqueConstraint("installation_id", "numero", name="uq_mark_installations_client_etapes_numero"),
        CheckConstraint("numero BETWEEN 1 AND 9", name="ck_mark_installations_client_etapes_numero"),
        CheckConstraint(
            "etat IN ('a_faire', 'en_cours', 'faite', 'erreur', 'passee')", name="ck_mark_installations_client_etapes_etat"
        ),
        Index("ix_mark_installations_client_etapes_org", "organization_id", "installation_id"),
    )

    id = Column(Integer, primary_key=True)
    installation_id = Column(Integer, ForeignKey("mark_installations_client.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    numero = Column(SmallInteger, nullable=False)
    etat = Column(String(10), nullable=False, default="a_faire", server_default="a_faire")
    par = Column(Integer, nullable=True)
    le = Column(DateTime(timezone=True), nullable=True)
    debut = Column(DateTime(timezone=True), nullable=True)
    derniere_erreur = Column(String(300), nullable=True)
    resultat = Column(JSONB, nullable=True)
