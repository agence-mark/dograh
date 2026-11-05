"""[.mark] Partie 3, sous-lot 17b : un fil peut être un signalement lié à un appel, et garde son auteur d'ouverture.

Revision ID: b8d3f6a1c4e2
Revises: a7c2e9d4b6f1

Trois colonnes nullables sur ``mark_relation_fils`` (additif : les fils d'avant gardent leurs valeurs vides) :

* ``run_id`` : l'appel signalé (suppression de l'appel : le lien tombe, le fil reste) ;
* ``amelioration_id`` : le problème « À améliorer » créé dans le même geste (relevé par le client) ;
* ``ouvert_par`` : l'auteur qui a ouvert le fil (« portail : prénom nom »), pour le filtre « les miens ».

Un index sert ce filtre. Réversible : la descente retire l'index puis les trois colonnes.
"""

import sqlalchemy as sa
from alembic import op

revision = "b8d3f6a1c4e2"
down_revision = "a7c2e9d4b6f1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mark_relation_fils",
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("mark_relation_fils", sa.Column("amelioration_id", sa.Integer(), nullable=True))
    op.add_column("mark_relation_fils", sa.Column("ouvert_par", sa.String(160), nullable=True))
    op.create_index("ix_mark_relation_fils_ouvert_par", "mark_relation_fils", ["organization_id", "ouvert_par", "modifie_le"])


def downgrade():
    op.drop_index("ix_mark_relation_fils_ouvert_par", table_name="mark_relation_fils")
    op.drop_column("mark_relation_fils", "ouvert_par")
    op.drop_column("mark_relation_fils", "amelioration_id")
    op.drop_column("mark_relation_fils", "run_id")
