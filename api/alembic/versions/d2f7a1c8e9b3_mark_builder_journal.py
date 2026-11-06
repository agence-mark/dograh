"""[.mark] Partie 3, N1 (SA-N1b) : le journal des écritures du builder (qui, quoi, quand, mode, autorisation, avant / après, annulation).

Revision ID: d2f7a1c8e9b3
Revises: c9e4b7a2d1f5

Une table additive, nommée ``mark_builder_journal`` : rien d'amont modifié. Lue et écrite par le serveur seulement (aucun rôle de portail,
de site ou de salarié n'y accède : pas de politique de sécurité par ligne à poser, le filtre par organisation est dans chaque requête).
Réversible : la descente retire la table et ses deux index.
"""

import sqlalchemy as sa
from alembic import op

revision = "d2f7a1c8e9b3"
down_revision = "c9e4b7a2d1f5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mark_builder_journal",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("quand", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_id", sa.Integer(), nullable=True),
        sa.Column("fil_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("auteur", sa.String(255), nullable=False),
        sa.Column("porte", sa.String(12), nullable=False, server_default="ecran"),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("famille", sa.String(24), nullable=False),
        sa.Column("mode", sa.String(12), nullable=True),
        sa.Column("autorisation", sa.String(16), nullable=False, server_default="mode"),
        sa.Column("statut", sa.String(10), nullable=False, server_default="en_cours"),
        sa.Column("arguments", sa.JSON(), nullable=True),
        sa.Column("avant", sa.JSON(), nullable=True),
        sa.Column("apres", sa.JSON(), nullable=True),
        sa.Column("annulation", sa.JSON(), nullable=True),
        sa.Column("non_annulable", sa.String(24), nullable=True),
        sa.Column("annule_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("annule_par", sa.String(255), nullable=True),
    )
    op.create_index("ix_mark_builder_journal_org_quand", "mark_builder_journal", ["organization_id", "quand"])
    op.create_index("ix_mark_builder_journal_org_agent", "mark_builder_journal", ["organization_id", "workflow_id", "id"])


def downgrade():
    op.drop_index("ix_mark_builder_journal_org_agent", table_name="mark_builder_journal")
    op.drop_index("ix_mark_builder_journal_org_quand", table_name="mark_builder_journal")
    op.drop_table("mark_builder_journal")
