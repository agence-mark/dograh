"""[.mark] Les sous-agents du builder, en tables.

Revision ID: a8c6e2f1d935
Revises: f4c9a2d7b815

Chantier builder partie 2, U5 (lot C2, E96). Migration .mark additive sur ``mark_builder_conversations`` : un sous-agent est une
conversation enfant (``parent_id`` existe déjà) qui garde sa délégation, son usage, sa tâche, son modèle et son rendu au builder ;
le parent garde l'interrupteur « Sous-agents dans ce chat ». Réversible.
"""

import sqlalchemy as sa
from alembic import op

revision = "a8c6e2f1d935"
down_revision = "f4c9a2d7b815"
branch_labels = None
depends_on = None

TABLE = "mark_builder_conversations"


def upgrade():
    op.add_column(TABLE, sa.Column("genre", sa.String(20), nullable=False, server_default="principal"))
    op.add_column(TABLE, sa.Column("delegation_id", sa.String(40), nullable=True))
    op.add_column(TABLE, sa.Column("usage", sa.String(20), nullable=True))
    op.add_column(TABLE, sa.Column("tache", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("modele", sa.String(120), nullable=True))
    op.add_column(TABLE, sa.Column("resultat", sa.JSON(), nullable=True))
    op.add_column(TABLE, sa.Column("sous_agents_actifs", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_index("ix_mark_builder_conversations_delegation", TABLE, ["parent_id", "delegation_id"])


def downgrade():
    op.drop_index("ix_mark_builder_conversations_delegation", table_name=TABLE)
    for colonne in ("sous_agents_actifs", "resultat", "modele", "tache", "usage", "delegation_id", "genre"):
        op.drop_column(TABLE, colonne)
