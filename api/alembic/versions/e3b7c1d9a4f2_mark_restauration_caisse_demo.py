"""[.mark] Module Restauration, lot 20 : les tables de la CAISSE DE DÉMO (Labo seulement).

Revision ID: e3b7c1d9a4f2
Revises: c5a8e2f1d934

Trois tables, séparées de tout classeur : les restaurants de test, leurs commandes reçues, les messages signés à rendre à la prise
(avec leurs tentatives). ``organization_id`` en cascade avec l'organisation. Aucun secret en clair : le jeton de la caisse n'est gardé qu'en
empreinte (le jeton lui-même est rangé au coffre d'identifiants de l'organisation par le branchement). Additive et réversible.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e3b7c1d9a4f2"
down_revision = "c5a8e2f1d934"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mark_caisse_demo_restaurant",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nom", sa.String(120), nullable=False),
        sa.Column("point_de_vente", sa.String(40), nullable=False),
        sa.Column("jeton_empreinte", sa.String(64), nullable=True),
        sa.Column("etat", sa.String(20), nullable=False, server_default="ouvert"),
        sa.Column("minutes_en_plus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("carte", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("stocks", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("clients", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("reglages", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("comportement", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("scenario", sa.String(60), nullable=True),
        sa.Column("callback_url", sa.Text(), nullable=True),
        sa.Column("callback_evenements", postgresql.JSONB(), nullable=True),
        sa.Column("cree_le", sa.DateTime(timezone=True), nullable=False),
        sa.Column("maj_le", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_mark_caisse_demo_point_de_vente", "mark_caisse_demo_restaurant", ["point_de_vente"], unique=True)
    op.create_index("ix_mark_caisse_demo_restaurant_org", "mark_caisse_demo_restaurant", ["organization_id"])
    op.create_index("ix_mark_caisse_demo_restaurant_jeton", "mark_caisse_demo_restaurant", ["jeton_empreinte"])
    op.create_table(
        "mark_caisse_demo_commande",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("mark_caisse_demo_restaurant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ref", sa.String(20), nullable=False),
        sa.Column("private_ref", sa.String(120), nullable=True),
        sa.Column("statut", sa.String(30), nullable=False),
        sa.Column("corps", postgresql.JSONB(), nullable=False),
        sa.Column("cree_le", sa.DateTime(timezone=True), nullable=False),
        sa.Column("maj_le", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_mark_caisse_demo_commande_ref", "mark_caisse_demo_commande", ["restaurant_id", "ref"], unique=True)
    op.create_index("ix_mark_caisse_demo_commande_private", "mark_caisse_demo_commande", ["restaurant_id", "private_ref"])
    op.create_table(
        "mark_caisse_demo_message",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("mark_caisse_demo_restaurant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("corps", postgresql.JSONB(), nullable=False),
        sa.Column("statut", sa.String(20), nullable=False, server_default="a_envoyer"),
        sa.Column("tentatives", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prochaine_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cree_le", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mark_caisse_demo_message_du", "mark_caisse_demo_message", ["statut", "prochaine_le"])
    op.create_index("ix_mark_caisse_demo_message_restaurant", "mark_caisse_demo_message", ["restaurant_id"])


def downgrade():
    op.drop_index("ix_mark_caisse_demo_message_restaurant", table_name="mark_caisse_demo_message")
    op.drop_index("ix_mark_caisse_demo_message_du", table_name="mark_caisse_demo_message")
    op.drop_table("mark_caisse_demo_message")
    op.drop_index("ix_mark_caisse_demo_commande_private", table_name="mark_caisse_demo_commande")
    op.drop_index("uq_mark_caisse_demo_commande_ref", table_name="mark_caisse_demo_commande")
    op.drop_table("mark_caisse_demo_commande")
    op.drop_index("ix_mark_caisse_demo_restaurant_jeton", table_name="mark_caisse_demo_restaurant")
    op.drop_index("ix_mark_caisse_demo_restaurant_org", table_name="mark_caisse_demo_restaurant")
    op.drop_index("uq_mark_caisse_demo_point_de_vente", table_name="mark_caisse_demo_restaurant")
    op.drop_table("mark_caisse_demo_restaurant")
