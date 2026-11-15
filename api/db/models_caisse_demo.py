"""[.mark] Module Restauration, lot 20 : les modèles de la caisse de démo (migration ``e3b7c1d9a4f2``). Labo seulement, aucun secret en clair.

Dans un module à part (comme ``models_restauration``) : aucun fichier d'amont touché. Les dates sont posées par l'écrivain, d'après la source d'heure
de l'organisation (D6) : aucune lecture de l'heure ici.
"""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from api.db.models import Base


class CaisseDemoRestaurantModel(Base):
    __tablename__ = "mark_caisse_demo_restaurant"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    nom = Column(String(120), nullable=False)
    point_de_vente = Column(String(40), nullable=False)
    jeton_empreinte = Column(String(64), nullable=True)
    etat = Column(String(20), nullable=False, default="ouvert")
    minutes_en_plus = Column(Integer, nullable=False, default=0)
    carte = Column(JSONB, nullable=False, default=dict)
    stocks = Column(JSONB, nullable=False, default=list)
    clients = Column(JSONB, nullable=False, default=list)
    reglages = Column(JSONB, nullable=False, default=dict)
    comportement = Column(JSONB, nullable=False, default=dict)
    scenario = Column(String(60), nullable=True)
    callback_url = Column(Text, nullable=True)
    callback_evenements = Column(JSONB, nullable=True)
    cree_le = Column(DateTime(timezone=True), nullable=False)
    maj_le = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("uq_mark_caisse_demo_point_de_vente", "point_de_vente", unique=True),
        Index("ix_mark_caisse_demo_restaurant_org", "organization_id"),
        Index("ix_mark_caisse_demo_restaurant_jeton", "jeton_empreinte"),
    )


class CaisseDemoCommandeModel(Base):
    __tablename__ = "mark_caisse_demo_commande"

    id = Column(Integer, primary_key=True)
    restaurant_id = Column(Integer, ForeignKey("mark_caisse_demo_restaurant.id", ondelete="CASCADE"), nullable=False)
    ref = Column(String(20), nullable=False)
    private_ref = Column(String(120), nullable=True)
    statut = Column(String(30), nullable=False)
    corps = Column(JSONB, nullable=False)
    cree_le = Column(DateTime(timezone=True), nullable=False)
    maj_le = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("uq_mark_caisse_demo_commande_ref", "restaurant_id", "ref", unique=True),
        Index("ix_mark_caisse_demo_commande_private", "restaurant_id", "private_ref"),
    )


class CaisseDemoMessageModel(Base):
    __tablename__ = "mark_caisse_demo_message"

    id = Column(String(40), primary_key=True)
    restaurant_id = Column(Integer, ForeignKey("mark_caisse_demo_restaurant.id", ondelete="CASCADE"), nullable=False)
    corps = Column(JSONB, nullable=False)
    statut = Column(String(20), nullable=False, default="a_envoyer")
    tentatives = Column(Integer, nullable=False, default=0)
    prochaine_le = Column(DateTime(timezone=True), nullable=True)
    cree_le = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_mark_caisse_demo_message_du", "statut", "prochaine_le"),
        Index("ix_mark_caisse_demo_message_restaurant", "restaurant_id"),
    )
