"""[.mark] Partie 3, lot 15 (P-6) : la permission « relation.ecrire » est accordée aux rôles qui ouvrent un portail.

Revision ID: f1a8c3d5e702
Revises: e6c9a2d4b815

Les écritures du Hub « Relation clients » (réponses, suivi, notes, témoignages) avaient seulement une journalisation. Elles ont
désormais leur permission, accordée par cette migration à chaque rôle qui porte déjà ``clients.ouvrir_portail`` (la décision P-6
du 04/11 : même public). Additive et idempotente (``ON CONFLICT DO NOTHING``). Réversible : la descente retire la permission de
tous les rôles (aucune autre table n'est touchée).
"""

from alembic import op

revision = "f1a8c3d5e702"
down_revision = "e6c9a2d4b815"
branch_labels = None
depends_on = None


MONTEE = (
    "INSERT INTO mark_role_permissions (role_id, permission) "
    "SELECT role_id, 'relation.ecrire' FROM mark_role_permissions WHERE permission = 'clients.ouvrir_portail' "
    "ON CONFLICT DO NOTHING"
)
DESCENTE = "DELETE FROM mark_role_permissions WHERE permission = 'relation.ecrire'"


def upgrade():
    op.execute(MONTEE)


def downgrade():
    op.execute(DESCENTE)
