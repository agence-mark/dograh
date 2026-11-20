"""[.mark] Chantier Partie 1, lot 17 : les gabarits d'agent, leurs applications et leurs diffusions (migration ``a7c3e9f1b2d4``).

Lues par le serveur de confiance seulement (aucun rôle de portail) ; le cloisonnement est dans chaque requête de ``gabarits_client.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB

from api.db.models import Base


class GabaritModel(Base):
    __tablename__ = "mark_gabarits"
    __table_args__ = (
        UniqueConstraint("nom", "version", name="uq_mark_gabarits_nom_version"),
        CheckConstraint("statut IN ('actif', 'retire')", name="ck_mark_gabarits_statut"),
        CheckConstraint("version >= 1", name="ck_mark_gabarits_version"),
    )

    id = Column(Integer, primary_key=True)
    nom = Column(String(60), nullable=False)
    version = Column(Integer, nullable=False)
    contenu = Column(JSONB, nullable=False)
    empreinte = Column(String(64), nullable=False)
    statut = Column(String(12), nullable=False, default="actif", server_default="actif")
    cree_le = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), default=lambda: datetime.now(UTC))


class GabaritApplicationModel(Base):
    __tablename__ = "mark_gabarit_applications"
    __table_args__ = (
        UniqueConstraint("workflow_id", name="uq_mark_gabarit_applications_workflow"),
        Index("ix_mark_gabarit_applications_organization_id", "organization_id"),
        Index("ix_mark_gabarit_applications_gabarit", "gabarit_nom", "gabarit_version"),
    )

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    workflow_id = Column(Integer, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    gabarit_nom = Column(String(60), nullable=False)
    gabarit_version = Column(Integer, nullable=False)
    commit_fork = Column(String(64), nullable=True)
    agents = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    trous = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    formulaire = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    retouches = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    empreinte_retouches = Column(String(64), nullable=True)
    rodage_relus = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)
    installee_le = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), default=lambda: datetime.now(UTC))
    maj_le = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), default=lambda: datetime.now(UTC))


class GabaritDiffusionModel(Base):
    __tablename__ = "mark_gabarit_diffusions"
    __table_args__ = (
        CheckConstraint("portee IN ('organisation', 'toutes')", name="ck_mark_gabarit_diffusions_portee"),
        CheckConstraint("statut IN ('refusee', 'faite', 'partielle')", name="ck_mark_gabarit_diffusions_statut"),
        Index("ix_mark_gabarit_diffusions_organization_id", "organization_id"),
        Index("ix_mark_gabarit_diffusions_gabarit", "gabarit_nom", "le"),
    )

    id = Column(Integer, primary_key=True)
    gabarit_nom = Column(String(60), nullable=False)
    gabarit_version = Column(Integer, nullable=False)
    portee = Column(String(14), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    par_user_id = Column(Integer, nullable=True)
    statut = Column(String(12), nullable=False)
    resultat = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    le = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), default=lambda: datetime.now(UTC))
