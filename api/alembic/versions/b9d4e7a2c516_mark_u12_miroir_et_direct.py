"""[.mark] U12 : le miroir des conversations Claude Code et la mise à jour en direct.

Revision ID: b9d4e7a2c516
Revises: a8c6e2f1d935

Chantier builder partie 2, U12 (lot I1, E104). Migration .mark additive :

* ``mark_builder_conversations`` : ``session_externe`` (la session Claude Code recopiée, une conversation par session et par
  organisation) et ``auteur`` (qui parle dans Claude Code, pour la marque « Claude Code · Evan ») ;
* ``mark_modifications`` : une ligne par écriture (agent, brouillon, tests, bibliothèque...), lue par l'écran ouvert sur
  l'élément pour se rafraîchir seul. La table fait foi, Redis ne fait que réveiller. Table lue par le serveur seulement
  (jamais par un rôle de portail, de site ou de salarié) : pas de politique de ligne à poser.

Réversible.
"""

import sqlalchemy as sa
from alembic import op

revision = "b9d4e7a2c516"
down_revision = "a8c6e2f1d935"
branch_labels = None
depends_on = None

CONVERSATIONS = "mark_builder_conversations"
MODIFICATIONS = "mark_modifications"


def upgrade():
    op.add_column(CONVERSATIONS, sa.Column("session_externe", sa.String(80), nullable=True))
    op.add_column(CONVERSATIONS, sa.Column("auteur", sa.String(120), nullable=True))
    op.create_index("ix_mark_builder_conversations_session", CONVERSATIONS, ["organization_id", "session_externe"])
    op.create_table(
        MODIFICATIONS,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("objet", sa.String(80), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("auteur", sa.String(120), nullable=True),
        sa.Column("cree_le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_mark_modifications_org", MODIFICATIONS, ["organization_id", "id"])
    op.create_index("ix_mark_modifications_objet", MODIFICATIONS, ["organization_id", "objet", "id"])


def downgrade():
    op.drop_index("ix_mark_modifications_objet", table_name=MODIFICATIONS)
    op.drop_index("ix_mark_modifications_org", table_name=MODIFICATIONS)
    op.drop_table(MODIFICATIONS)
    op.drop_index("ix_mark_builder_conversations_session", table_name=CONVERSATIONS)
    op.drop_column(CONVERSATIONS, "auteur")
    op.drop_column(CONVERSATIONS, "session_externe")
