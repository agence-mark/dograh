"""[.mark] Sous-dossiers : ajoute ``folders.parent_id`` (facultative).

Revision ID: 7c4e1a9b2d58
Revises: 3a7b91c5d402

Chantier agents-specialises, lot 10 (A9). Migration .mark permise par la règle n° 4
reformulée (Evan et Pierre, 16/10/2026), aux trois conditions :

- **additive** : colonne facultative, ``NULL`` = un dossier de premier niveau, comportement
  d'avant ; aucune donnée existante n'est modifiée ;
- **nommée ``mark_*``** (``mark_folders_parent_id``) ;
- **rebasée en premier** à chaque audit de l'amont : si l'amont ajoute une migration, celle-ci
  reprend sa place en tête de chaîne (changer ``down_revision``), jamais l'inverse.

``ON DELETE SET NULL`` : supprimer un dossier parent ne supprime jamais ses sous-dossiers
(la route les remonte d'un niveau avant, la contrainte n'est que le filet).
Réversible : ``downgrade`` retire l'index, la contrainte et la colonne.
"""

import sqlalchemy as sa
from alembic import op

revision = "7c4e1a9b2d58"
down_revision = "3a7b91c5d402"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("folders", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_folders_parent_id",
        "folders",
        "folders",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_folders_parent_id", "folders", ["parent_id"])


def downgrade():
    op.drop_index("ix_folders_parent_id", table_name="folders")
    op.drop_constraint("fk_folders_parent_id", "folders", type_="foreignkey")
    op.drop_column("folders", "parent_id")
