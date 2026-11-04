"""[.mark] La fin d'une entrée de .mark dans un portail, pour mesurer la durée de la visite.

Revision ID: d5b8f1a3c704
Revises: c4a7d2e9b301

Chantier builder partie 2, V4. ``mark_relation_entrees.fin_le`` : l'heure où le portail du client dit que la personne de .mark en est
sortie (``POST /organizations/relation/entree/{id}/fin``). Nulle tant que le portail ne l'a pas dit ; la durée est ``fin_le - utilise_le``.
Colonne additive, sans défaut : les entrées d'avant restent sans durée. Réversible.
"""

import sqlalchemy as sa
from alembic import op

revision = "d5b8f1a3c704"
down_revision = "c4a7d2e9b301"
branch_labels = None
depends_on = None

TABLE = "mark_relation_entrees"


def upgrade():
    op.add_column(TABLE, sa.Column("fin_le", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column(TABLE, "fin_le")
