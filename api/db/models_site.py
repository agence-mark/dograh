"""[.mark] Le widget public en tables : sites intégrés, chemins par agent, usage mensuel.

Dans un module à part (comme ``models_equipe``) : le moins de fichiers d'amont touchés possible. La migration
``mark_site_widget`` crée ces trois tables et ajoute à ``embed_tokens`` deux colonnes facultatives
(``site_id`` et ``reglages_mark``, déclarées dans ``models.py``).
"""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)

from api.db.models import Base


class MarkEmbedSiteModel(Base):
    """Un site intégré : sa clé publique (celle du script), ses domaines, le dernier chargement vu."""

    __tablename__ = "mark_embed_sites"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cle = Column(String(80), nullable=False, unique=True)
    nom = Column(String(120), nullable=False, default="")
    allowed_domains = Column(JSON, nullable=True)
    dernier_chargement = Column(DateTime(timezone=True), nullable=True)
    cree_le = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), default=lambda: datetime.now(UTC))


class MarkEmbedCheminModel(Base):
    """Un chemin servi par un agent de site. Unique par (site, chemin) : deux agents sur une page sont refusés."""

    __tablename__ = "mark_embed_chemins"
    __table_args__ = (UniqueConstraint("site_id", "chemin", name="uq_mark_embed_chemins_site_chemin"),)

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("mark_embed_sites.id", ondelete="CASCADE"), nullable=False)
    embed_token_id = Column(
        Integer, ForeignKey("embed_tokens.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chemin = Column(String(512), nullable=False)


class MarkEmbedUsageMensuelModel(Base):
    """L'usage d'un jeton sur un mois (``AAAA-MM``) : conversations commencées et secondes parlées."""

    __tablename__ = "mark_embed_usage_mensuel"

    embed_token_id = Column(
        Integer, ForeignKey("embed_tokens.id", ondelete="CASCADE"), primary_key=True
    )
    mois = Column(String(7), primary_key=True)
    conversations = Column(Integer, nullable=False, default=0, server_default="0")
    secondes = Column(Integer, nullable=False, default=0, server_default="0")


class MarkEmbedEvenementJourModel(Base):
    """Les compteurs anonymes d'un agent de site pour un jour : combien de fois le rond s'est affiché, combien de
    fois il s'est ouvert. Ni cookie, ni identifiant, ni adresse : des totaux (lot S3)."""

    __tablename__ = "mark_embed_evenements_jour"

    embed_token_id = Column(
        Integer, ForeignKey("embed_tokens.id", ondelete="CASCADE"), primary_key=True
    )
    jour = Column(Date, primary_key=True)
    affiche = Column(Integer, nullable=False, default=0, server_default="0")
    ouvert = Column(Integer, nullable=False, default=0, server_default="0")
