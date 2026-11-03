"""[.mark] La note du juge, gardée par appel, et les index des filtres et tris de Conversations.

Revision ID: c4a7d2e9b301
Revises: b7d3e5a9c102

Chantier builder partie 2, lot C4. ``workflow_runs.note_juge`` : note sur 5 du juge (part des critères réussis parmi ceux qu'il a pu
vérifier), écrite par l'après-appel et par ``juge_ecrire`` (même fonction, rejuger remplace). Nulle tant que l'appel n'est pas jugé.
Trois index additifs pour les filtres et tris de la liste des appels : version jouée (``definition_id``), liste d'un agent par date,
note (partiel : seules les lignes jugées). Réversible.
"""

import sqlalchemy as sa
from alembic import op

revision = "c4a7d2e9b301"
down_revision = "b7d3e5a9c102"
branch_labels = None
depends_on = None

TABLE = "workflow_runs"


def upgrade():
    op.add_column(TABLE, sa.Column("note_juge", sa.Float(), nullable=True))
    op.create_index("idx_workflow_runs_definition_id", TABLE, ["definition_id"])
    op.create_index("idx_workflow_runs_workflow_created", TABLE, ["workflow_id", "created_at"])
    op.create_index("idx_workflow_runs_note_juge", TABLE, ["workflow_id", "note_juge"], postgresql_where=sa.text("note_juge IS NOT NULL"))


def downgrade():
    op.drop_index("idx_workflow_runs_note_juge", table_name=TABLE)
    op.drop_index("idx_workflow_runs_workflow_created", table_name=TABLE)
    op.drop_index("idx_workflow_runs_definition_id", table_name=TABLE)
    op.drop_column(TABLE, "note_juge")
