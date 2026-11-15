"""[.mark] Module Restauration : le lien point de vente d'une caisse -> établissement.

Revision ID: c5a8e2f1d934
Revises: b7d3f1a9c5e2

Chantier module-restauration, lot 1 (X2 : le point de vente se relie à l'ÉTABLISSEMENT, pas à l'organisation).
Migration .mark additive : une table, ``organization_id`` en cascade avec l'organisation. L'établissement est
nommé par sa ``cle`` (celle de ``mark.site`` dans la base du client). Un point de vente d'une prise ne sert
qu'un établissement (index unique) : un message d'une caisse retrouve son établissement sans ambiguïté.
Aucun secret ici. Réversible.
"""

import sqlalchemy as sa
from alembic import op

revision = "c5a8e2f1d934"
down_revision = "b7d3f1a9c5e2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mark_point_de_vente",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("prise", sa.String(40), nullable=False),
        sa.Column("point_de_vente", sa.String(120), nullable=False),
        sa.Column("etablissement_cle", sa.String(120), nullable=False),
        sa.Column(
            "cree_le",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Un point de vente d'une prise = un seul établissement, dans toute l'installation.
    op.create_index(
        "uq_mark_point_de_vente_prise_point",
        "mark_point_de_vente",
        ["prise", "point_de_vente"],
        unique=True,
    )
    # Un établissement n'a qu'un point de vente par prise.
    op.create_index(
        "uq_mark_point_de_vente_etablissement",
        "mark_point_de_vente",
        ["organization_id", "prise", "etablissement_cle"],
        unique=True,
    )


def downgrade():
    op.drop_index("uq_mark_point_de_vente_etablissement", table_name="mark_point_de_vente")
    op.drop_index("uq_mark_point_de_vente_prise_point", table_name="mark_point_de_vente")
    op.drop_table("mark_point_de_vente")
