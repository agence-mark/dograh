"""[.mark] Module Restauration : le lien point de vente d'une caisse -> établissement (X2, lot 1).

Dans un module à part (comme ``models_relation``) : aucun fichier d'amont touché. La migration
``c5a8e2f1d934`` crée la table. Le point de vente se relie à l'ÉTABLISSEMENT (sa ``cle`` dans la base du
client), pas à l'organisation ; un point de vente d'une prise ne sert qu'un établissement. Aucun secret ici.
La date de création est posée par l'écrivain, d'après la source d'heure de l'organisation (D6) : aucune lecture de l'heure ici.
"""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String

from api.db.models import Base


class MarkPointDeVenteModel(Base):
    __tablename__ = "mark_point_de_vente"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    prise = Column(String(40), nullable=False)
    point_de_vente = Column(String(120), nullable=False)
    etablissement_cle = Column(String(120), nullable=False)
    cree_le = Column(DateTime(timezone=True), nullable=False)  # posée par l'écrivain, d'après la source d'heure

    __table_args__ = (
        Index("uq_mark_point_de_vente_prise_point", "prise", "point_de_vente", unique=True),
        Index(
            "uq_mark_point_de_vente_etablissement",
            "organization_id",
            "prise",
            "etablissement_cle",
            unique=True,
        ),
    )
