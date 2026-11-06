"""[.mark] La boucle d'amélioration : la table des problèmes de « À améliorer ».

Revision ID: b7d3e5a9c102
Revises: b9d4e7a2c516

Chantier builder partie 2, U8 (lot G1). Une table additive ``mark_ameliorations`` : un problème regroupe ses cas (même agent, même
critère ou contrôle, même étape) et porte son état (à trier, en cours, testée, publiée, ignorée). Réversible.
"""

import sqlalchemy as sa
from alembic import op

revision = "b7d3e5a9c102"
down_revision = "b9d4e7a2c516"
branch_labels = None
depends_on = None

TABLE = "mark_ameliorations"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_id", sa.Integer(), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cle", sa.String(240), nullable=False),
        sa.Column("releve_par", sa.String(16), nullable=False),
        sa.Column("titre", sa.Text(), nullable=False),
        sa.Column("critere", sa.String(240), nullable=True),
        sa.Column("etape", sa.String(160), nullable=True),
        sa.Column("gravite", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("cause", sa.String(16), nullable=True),
        sa.Column("action", sa.String(200), nullable=True),
        sa.Column("etat", sa.String(16), nullable=False, server_default="a_trier"),
        sa.Column("origine", sa.String(16), nullable=True),
        sa.Column("assigne", sa.Integer(), nullable=True),
        sa.Column("replique", sa.Text(), nullable=True),
        sa.Column("confiance", sa.Float(), nullable=True),
        sa.Column("cas", sa.JSON(), nullable=False),
        sa.Column("nb_cas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correction", sa.JSON(), nullable=True),
        sa.Column("avancement", sa.JSON(), nullable=False),
        sa.Column("version_numero", sa.Integer(), nullable=True),
        sa.Column("premiere_le", sa.DateTime(timezone=True), nullable=False),
        sa.Column("derniere_le", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cree_le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modifie_le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "workflow_id", "cle", name="uq_mark_ameliorations_groupe"),
    )
    op.create_index("ix_mark_ameliorations_workflow_id", TABLE, ["workflow_id"])
    op.create_index("ix_mark_ameliorations_file", TABLE, ["organization_id", "etat", "derniere_le"])


def downgrade():
    op.drop_index("ix_mark_ameliorations_file", table_name=TABLE)
    op.drop_index("ix_mark_ameliorations_workflow_id", table_name=TABLE)
    op.drop_table(TABLE)
