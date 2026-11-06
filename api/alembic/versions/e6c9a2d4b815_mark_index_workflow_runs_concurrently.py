"""[.mark] Les trois index de Conversations sur ``workflow_runs``, créés SANS verrouiller les écritures.

Revision ID: e6c9a2d4b815
Revises: d5b8f1a3c704

Revue serveur, mineur 9. ``c4a7d2e9b301`` créait ces index par un ``CREATE INDEX`` ordinaire : sur une table d'appels de production,
il bloque les écritures (les appels en cours) le temps de la construction. Les index sont retirés de ``c4a7d2e9b301`` et créés ici
par ``CREATE INDEX CONCURRENTLY`` (hors transaction, ``autocommit_block``). ``IF NOT EXISTS`` : une base qui a déjà joué l'ancienne
version de ``c4a7d2e9b301`` garde les siens, sans les recréer. Réversible : la descente les retire (``DROP INDEX CONCURRENTLY IF EXISTS``).
"""

from alembic import op

revision = "e6c9a2d4b815"
down_revision = "d5b8f1a3c704"
branch_labels = None
depends_on = None

INDEX = (
    ("idx_workflow_runs_definition_id", "(definition_id)"),
    ("idx_workflow_runs_workflow_created", "(workflow_id, created_at)"),
    ("idx_workflow_runs_note_juge", "(workflow_id, note_juge) WHERE note_juge IS NOT NULL"),
)


def upgrade():
    with op.get_context().autocommit_block():
        for nom, definition in INDEX:
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {nom} ON workflow_runs {definition}")


def downgrade():
    with op.get_context().autocommit_block():
        for nom, _ in reversed(INDEX):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {nom}")
