"""[.mark] Le widget public : compteurs anonymes par jour et par agent (affiché, ouvert).

Revision ID: d7a1c4e9b362
Revises: c8f3b6d2a915

Chantier builder partie 2, U10.3 (lot S3 du plan du portail v4). Migration .mark additive : une table
``mark_embed_evenements_jour`` (un jeton d'agent, un jour, deux compteurs). Aucun cookie, aucun identifiant de
visiteur, aucune adresse IP : seulement des totaux. Réversible.
"""

import sqlalchemy as sa
from alembic import op

revision = "d7a1c4e9b362"
down_revision = "c8f3b6d2a915"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mark_embed_evenements_jour",
        sa.Column(
            "embed_token_id", sa.Integer(), sa.ForeignKey("embed_tokens.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("jour", sa.Date(), primary_key=True),
        sa.Column("affiche", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ouvert", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_table("mark_embed_evenements_jour")
