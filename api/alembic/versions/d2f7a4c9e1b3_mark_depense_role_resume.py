"""[.mark] Partie 3, N3b : le résumé d'appel, troisième rôle de la dépense du mois, et la permission ``tests.automatiser``.

Revision ID: d2f7a4c9e1b3
Revises: c9e4b7a2d1f5

1. ``mark_depense_roles`` ne connaissait que « appelant » et « juge » (contrainte ``ck_mark_depense_roles_role``) : le résumé d'appel par
   un modèle (réglage éteint par défaut) y range sa dépense comme les deux autres, jamais dans un second compteur. La montée élargit
   la contrainte ; la descente retire les lignes « resume » (la dépense d'un rôle qui n'existe plus) puis remet celle d'avant.
2. ``tests.automatiser`` : lancer la suite de tests d'un agent depuis une automatisation (n8n). Accordée aux rôles qui jouent déjà les
   tests (``tests.jouer``) : aucun droit perdu ni gagné. Additive et idempotente ; la descente la retire de tous les rôles.
"""

import sqlalchemy as sa
from alembic import op

revision = "d2f7a4c9e1b3"
down_revision = "c9e4b7a2d1f5"
branch_labels = None
depends_on = None

CONTRAINTE = "ck_mark_depense_roles_role"


def _accorder():
    op.execute(
        "INSERT INTO mark_role_permissions (role_id, permission) "
        "SELECT role_id, 'tests.automatiser' FROM mark_role_permissions WHERE permission = 'tests.jouer' "
        "ON CONFLICT DO NOTHING"
    )


def _retirer():
    op.execute("DELETE FROM mark_role_permissions WHERE permission = 'tests.automatiser'")


def upgrade():
    op.drop_constraint(CONTRAINTE, "mark_depense_roles", type_="check")
    op.create_check_constraint(CONTRAINTE, "mark_depense_roles", "role IN ('appelant', 'juge', 'resume')")
    _accorder()


def downgrade():
    _retirer()
    op.execute(sa.text("DELETE FROM mark_depense_roles WHERE role = 'resume'"))
    op.drop_constraint(CONTRAINTE, "mark_depense_roles", type_="check")
    op.create_check_constraint(CONTRAINTE, "mark_depense_roles", "role IN ('appelant', 'juge')")
