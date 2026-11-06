"""[.mark] Le Hub « Relation clients » : fils, messages, notes, témoignages, entrées dans les portails.

Revision ID: f4c9a2d7b815
Revises: e3b8d5a1c704

Chantier builder partie 2, U3 septies (lot H1, E78). Migration .mark additive : cinq tables, chacune avec
``organization_id`` (suppression en cascade avec l'organisation). Le jeton d'une entrée n'est jamais écrit : seulement
son empreinte. Réversible.
"""

import sqlalchemy as sa
from alembic import op

revision = "f4c9a2d7b815"
down_revision = "e3b8d5a1c704"
branch_labels = None
depends_on = None


def _org():
    return sa.Column(
        "organization_id",
        sa.Integer(),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )


def _ts(nom, **options):
    return sa.Column(nom, sa.DateTime(timezone=True), **options)


def upgrade():
    op.create_table(
        "mark_relation_fils",
        sa.Column("id", sa.Integer(), primary_key=True),
        _org(),
        sa.Column("sorte", sa.String(24), nullable=False, server_default="message"),
        sa.Column("sujet", sa.String(200), nullable=False),
        sa.Column("etat", sa.String(16), nullable=False, server_default="nouveau"),
        sa.Column("suivi_par", sa.Integer(), nullable=True),
        sa.Column("suivi_nom", sa.String(120), nullable=True),
        sa.Column("lu_par_mark", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("logiciel", sa.String(120), nullable=True),
        sa.Column("catalogue", sa.String(120), nullable=True),
        sa.Column("etat_demande", sa.String(16), nullable=True),
        _ts("cree_le", nullable=False),
        _ts("modifie_le", nullable=False),
    )
    op.create_index(
        "ix_mark_relation_fils_org", "mark_relation_fils", ["organization_id", "modifie_le"]
    )
    op.create_table(
        "mark_relation_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "fil_id",
            sa.Integer(),
            sa.ForeignKey("mark_relation_fils.id", ondelete="CASCADE"),
            nullable=False,
        ),
        _org(),
        sa.Column("cote", sa.String(8), nullable=False),
        sa.Column("auteur", sa.String(160), nullable=False),
        sa.Column("texte", sa.Text(), nullable=False),
        _ts("cree_le", nullable=False),
    )
    op.create_index(
        "ix_mark_relation_messages_fil", "mark_relation_messages", ["fil_id", "id"]
    )
    op.create_table(
        "mark_relation_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        _org(),
        sa.Column("auteur", sa.String(160), nullable=False),
        sa.Column("texte", sa.Text(), nullable=False),
        _ts("cree_le", nullable=False),
    )
    op.create_index(
        "ix_mark_relation_notes_org", "mark_relation_notes", ["organization_id", "id"]
    )
    op.create_table(
        "mark_relation_temoignages",
        sa.Column("id", sa.Integer(), primary_key=True),
        _org(),
        sa.Column("texte", sa.Text(), nullable=False),
        sa.Column("auteur", sa.String(160), nullable=False),
        sa.Column("accord", sa.Boolean(), nullable=False, server_default="false"),
        _ts("cree_le", nullable=False),
    )
    op.create_index(
        "ix_mark_relation_temoignages_org", "mark_relation_temoignages", ["organization_id"]
    )
    op.create_table(
        "mark_relation_entrees",
        sa.Column("id", sa.Integer(), primary_key=True),
        _org(),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("auteur", sa.String(160), nullable=False),
        sa.Column("motif", sa.String(200), nullable=True),
        sa.Column("empreinte_jeton", sa.String(64), nullable=False, unique=True),
        _ts("cree_le", nullable=False),
        _ts("expire_le", nullable=False),
        _ts("utilise_le", nullable=True),
    )
    op.create_index(
        "ix_mark_relation_entrees_org", "mark_relation_entrees", ["organization_id", "id"]
    )


def downgrade():
    for table in (
        "mark_relation_entrees",
        "mark_relation_temoignages",
        "mark_relation_notes",
        "mark_relation_messages",
        "mark_relation_fils",
    ):
        op.drop_table(table)
