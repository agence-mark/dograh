"""[.mark] La note du juge, gardée par appel, et les index des filtres et tris de Conversations.

Revision ID: c4a7d2e9b301
Revises: b7d3e5a9c102

Chantier builder partie 2, lot C4. ``workflow_runs.note_juge`` : note sur 5 du juge (part des critères réussis parmi ceux qu'il a pu
vérifier), écrite par l'après-appel et par ``juge_ecrire`` (même fonction, rejuger remplace). Nulle tant que l'appel n'est pas jugé.
Les index des filtres et tris de la liste des appels (version jouée, liste d'un agent par date, note) ne sont plus créés ici : revue
serveur, mineur 9, ils sont créés sans verrou par ``e6c9a2d4b815`` (``CREATE INDEX CONCURRENTLY``). Réversible.
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


def downgrade():
    # Les index ont pu être créés par l'ancienne version de cette migration (bases déjà migrées) : retirés s'ils sont là.
    for nom in ("idx_workflow_runs_note_juge", "idx_workflow_runs_workflow_created", "idx_workflow_runs_definition_id"):
        op.execute(f"DROP INDEX IF EXISTS {nom}")
    op.drop_column(TABLE, "note_juge")
