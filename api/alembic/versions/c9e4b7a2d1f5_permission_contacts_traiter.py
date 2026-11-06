"""[.mark] Partie 3, SA-17c : la permission ``contacts.traiter``, accordée aux rôles qui modifient déjà les agents du client.

Revision ID: c9e4b7a2d1f5
Revises: b8d3f6a1c4e2

``contacts.traiter`` : fusionner deux contacts, « ce n'est pas la même personne », « ne pas mémoriser » (ouverte à la clé du client).
Ces gestes sont des routes ``/organizations/*``, qui exigeaient jusqu'ici ``agents.modifier`` : les rôles qui la portent gardent donc
ces gestes (aucun droit perdu). Additive et idempotente. Réversible : la descente retire la permission de tous les rôles.
"""

from alembic import op

revision = "c9e4b7a2d1f5"
down_revision = "b8d3f6a1c4e2"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "INSERT INTO mark_role_permissions (role_id, permission) "
        "SELECT role_id, 'contacts.traiter' FROM mark_role_permissions WHERE permission = 'agents.modifier' "
        "ON CONFLICT DO NOTHING"
    )


def downgrade():
    op.execute("DELETE FROM mark_role_permissions WHERE permission = 'contacts.traiter'")
