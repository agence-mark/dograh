"""[.mark] Le widget public : sites, chemins, usage mensuel, réglages .mark du jeton.

Revision ID: c8f3b6d2a915
Revises: b4e2a7c19d30

Chantier builder partie 2, U10 (S1 et S2 du plan du portail v4). Migration .mark additive : trois tables
nouvelles (``mark_embed_sites``, ``mark_embed_chemins``, ``mark_embed_usage_mensuel``) et deux colonnes
facultatives sur ``embed_tokens`` (``site_id``, ``reglages_mark``). Aucun jeton existant n'est modifié : un
jeton sans site et sans réglages garde exactement son comportement d'avant (l'ancien script par jeton marche).
Réversible.
"""

import sqlalchemy as sa
from alembic import op

revision = "c8f3b6d2a915"
down_revision = "b4e2a7c19d30"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mark_embed_sites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cle", sa.String(80), nullable=False, unique=True),
        sa.Column("nom", sa.String(120), nullable=False, server_default=""),
        sa.Column("allowed_domains", sa.JSON(), nullable=True),
        sa.Column("dernier_chargement", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cree_le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_mark_embed_sites_organization_id", "mark_embed_sites", ["organization_id"])

    op.add_column(
        "embed_tokens",
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("mark_embed_sites.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("embed_tokens", sa.Column("reglages_mark", sa.JSON(), nullable=True))
    op.create_index("ix_embed_tokens_site_id", "embed_tokens", ["site_id"])

    op.create_table(
        "mark_embed_chemins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("mark_embed_sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "embed_token_id", sa.Integer(), sa.ForeignKey("embed_tokens.id", ondelete="CASCADE"), nullable=False
        ),
        # Le chemin normalisé (minuscules, sans paramètres ni ancre, sans barre finale) ; "/" = tout le site.
        sa.Column("chemin", sa.String(512), nullable=False),
        sa.UniqueConstraint("site_id", "chemin", name="uq_mark_embed_chemins_site_chemin"),
    )
    op.create_index("ix_mark_embed_chemins_embed_token_id", "mark_embed_chemins", ["embed_token_id"])

    op.create_table(
        "mark_embed_usage_mensuel",
        sa.Column(
            "embed_token_id", sa.Integer(), sa.ForeignKey("embed_tokens.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("mois", sa.String(7), primary_key=True),
        sa.Column("conversations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("secondes", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_table("mark_embed_usage_mensuel")
    op.drop_index("ix_mark_embed_chemins_embed_token_id", table_name="mark_embed_chemins")
    op.drop_table("mark_embed_chemins")
    op.drop_index("ix_embed_tokens_site_id", table_name="embed_tokens")
    op.drop_column("embed_tokens", "reglages_mark")
    op.drop_column("embed_tokens", "site_id")
    op.drop_index("ix_mark_embed_sites_organization_id", table_name="mark_embed_sites")
    op.drop_table("mark_embed_sites")
