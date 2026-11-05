"""[.mark] Partie 3, N3b : le résumé d'appel est un troisième rôle de la dépense du mois.

Revision ID: d2f7a4c9e1b3
Revises: c9e4b7a2d1f5

``mark_depense_roles`` ne connaissait que « appelant » et « juge » (contrainte ``ck_mark_depense_roles_role``) : le résumé d'appel par un
modèle (réglage éteint par défaut) y range sa dépense comme les deux autres, jamais dans un second compteur. La montée élargit la
contrainte ; la descente retire les lignes « resume » (la dépense d'un rôle qui n'existe plus) puis remet la contrainte d'avant.
"""

import sqlalchemy as sa
from alembic import op

revision = "d2f7a4c9e1b3"
down_revision = "c9e4b7a2d1f5"
branch_labels = None
depends_on = None

CONTRAINTE = "ck_mark_depense_roles_role"


def upgrade():
    op.drop_constraint(CONTRAINTE, "mark_depense_roles", type_="check")
    op.create_check_constraint(CONTRAINTE, "mark_depense_roles", "role IN ('appelant', 'juge', 'resume')")


def downgrade():
    op.execute(sa.text("DELETE FROM mark_depense_roles WHERE role = 'resume'"))
    op.drop_constraint(CONTRAINTE, "mark_depense_roles", type_="check")
    op.create_check_constraint(CONTRAINTE, "mark_depense_roles", "role IN ('appelant', 'juge')")
