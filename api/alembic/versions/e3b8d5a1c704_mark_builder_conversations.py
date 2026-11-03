"""[.mark] Le builder en tables : conversations et événements.

Revision ID: e3b8d5a1c704
Revises: d7a1c4e9b362

Chantier builder partie 2, U5 (lot C1, D1 du 03/11). Migration .mark additive : ``mark_builder_conversations`` (une par
discussion avec le builder, titre, état, coût, jauge, historique du cerveau, lien vers un parent) et
``mark_builder_evenements`` (ce que l'écran rejoue, dans l'ordre). Réversible.
"""

import sqlalchemy as sa
from alembic import op

revision = "e3b8d5a1c704"
down_revision = "d7a1c4e9b362"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mark_builder_conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_id", sa.Integer(), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=True),
        sa.Column(
            "parent_id", sa.Integer(), sa.ForeignKey("mark_builder_conversations.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("titre", sa.String(200), nullable=False, server_default=""),
        sa.Column("etat", sa.String(20), nullable=False, server_default="nouvelle"),
        sa.Column("demarrage", sa.String(120), nullable=True),
        sa.Column("historique", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("jetons", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cout", sa.Float(), nullable=False, server_default="0"),
        sa.Column("jauge", sa.Float(), nullable=False, server_default="0"),
        sa.Column("changements", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cree_le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modifie_le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_mark_builder_conversations_organization_id", "mark_builder_conversations", ["organization_id"])
    op.create_index("ix_mark_builder_conversations_workflow_id", "mark_builder_conversations", ["workflow_id"])
    op.create_index("ix_mark_builder_conversations_parent_id", "mark_builder_conversations", ["parent_id"])
    op.create_table(
        "mark_builder_evenements",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey("mark_builder_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("donnees", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("cree_le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_mark_builder_evenements_fil", "mark_builder_evenements", ["conversation_id", "id"])


def downgrade():
    op.drop_table("mark_builder_evenements")
    op.drop_table("mark_builder_conversations")
