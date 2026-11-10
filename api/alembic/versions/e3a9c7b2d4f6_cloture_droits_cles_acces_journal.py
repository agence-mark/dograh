"""[.mark] Clôture, lot A : clé d'API portée par un rôle, accès bloqué en un clic, journal complet de l'équipe.

Revision ID: e3a9c7b2d4f6
Revises: d2f7a1c8e9b3

* ``api_keys.role_id`` (D21) : le rôle que la clé porte ; vide = clé d'avant ou du portail (liste fermée). Le service refuse de supprimer un rôle
  tant qu'une clé NON révoquée le porte ; seules des clés révoquées peuvent donc retomber sur « vide » (``SET NULL``).
* ``mark_membres.acces_actif`` et ``bloque_le`` (D22).
* ``mark_journal.origine`` et un index sur ``action`` (D23 : filtrer par type de geste).
* ``mark_reglages_equipe`` (D22, D23) : message d'accès bloqué, durée du journal.
* Permission ``journal.lire`` (D24) accordée aux rôles qui gèrent déjà l'équipe (les rôles suprêmes).

Additive, idempotente pour la permission. Réversible : la descente retire tout, dans l'ordre inverse. Les tables touchées ne sont lues que par le
serveur de confiance : pas de politique de sécurité par ligne à poser (aucun rôle de portail, de site ou de salarié n'y accède).
"""

import sqlalchemy as sa
from alembic import op

revision = "e3a9c7b2d4f6"
down_revision = "d2f7a1c8e9b3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("api_keys", sa.Column("role_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_api_keys_role_id", "api_keys", "mark_roles", ["role_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_api_keys_role_id", "api_keys", ["role_id"])
    op.add_column("mark_membres", sa.Column("acces_actif", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("mark_membres", sa.Column("bloque_le", sa.DateTime(timezone=True), nullable=True))
    op.add_column("mark_journal", sa.Column("origine", sa.String(8), nullable=True))
    op.create_index("ix_mark_journal_action", "mark_journal", ["action"])
    op.create_table(
        "mark_reglages_equipe",
        sa.Column("cle", sa.String(64), primary_key=True),
        sa.Column("valeur", sa.JSON(), nullable=True),
        sa.Column("modifie_le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modifie_par", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.execute(
        "INSERT INTO mark_role_permissions (role_id, permission) "
        "SELECT role_id, 'journal.lire' FROM mark_role_permissions WHERE permission = 'equipe.gerer' "
        "ON CONFLICT DO NOTHING"
    )


def downgrade():
    op.execute("DELETE FROM mark_role_permissions WHERE permission = 'journal.lire'")
    op.drop_table("mark_reglages_equipe")
    op.drop_index("ix_mark_journal_action", table_name="mark_journal")
    op.drop_column("mark_journal", "origine")
    op.drop_column("mark_membres", "bloque_le")
    op.drop_column("mark_membres", "acces_actif")
    op.drop_index("ix_api_keys_role_id", table_name="api_keys")
    op.drop_constraint("fk_api_keys_role_id", "api_keys", type_="foreignkey")
    op.drop_column("api_keys", "role_id")
