"""[.mark] Module Restauration, lot 11 : les dossiers d'outils et les kits d'outils.

Revision ID: d4e9b1c7a3f5
Revises: c5a8e2f1d934

Migration .mark additive (rien n'est réécrit, aucune donnée supprimée) :

- ``tool_folders`` : dossiers de l'écran Outils, par organisation, deux niveaux (``parent_id``) ; supprimer un dossier supprime ses
  sous-dossiers, jamais un outil (``tools.folder_id`` repasse à NULL) ;
- ``tool_kits`` et ``tool_kit_items`` : les kits, au niveau du fork (aucune organisation) ; chaque outil de kit porte sa ``version`` ;
- ``tools.folder_id``, ``tools.kit_item_id``, ``tools.kit_version`` : le rangement et l'origine d'un outil. Rien de tout cela n'est
  jamais envoyé au modèle ni écrit dans la définition de l'outil.

Les kits livrés (Commande, Réservation, Envois) sont posés au démarrage par le serveur, d'après le catalogue des connecteurs, pour ne
jamais recopier ici un texte qui vieillit. Réversible.
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e9b1c7a3f5"
down_revision = "c5a8e2f1d934"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tool_folders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("tool_folders.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tool_folders_id", "tool_folders", ["id"])
    op.create_index("ix_tool_folders_organization_id", "tool_folders", ["organization_id"])
    op.create_index("ix_tool_folders_parent_id", "tool_folders", ["parent_id"])
    op.create_index(
        "uq_tool_folders_org_parent_nom",
        "tool_folders",
        ["organization_id", sa.text("coalesce(parent_id, 0)"), "name"],
        unique=True,
    )

    op.create_table(
        "tool_kits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tool_kits_id", "tool_kits", ["id"])

    op.create_table(
        "tool_kit_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kit_id", sa.Integer(), sa.ForeignKey("tool_kits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("icon_color", sa.String(7), nullable=True),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("kit_id", "name", name="uq_tool_kit_items_kit_nom"),
    )
    op.create_index("ix_tool_kit_items_id", "tool_kit_items", ["id"])
    op.create_index("ix_tool_kit_items_kit_id", "tool_kit_items", ["kit_id"])

    op.add_column("tools", sa.Column("folder_id", sa.Integer(), sa.ForeignKey("tool_folders.id", ondelete="SET NULL"), nullable=True))
    op.add_column("tools", sa.Column("kit_item_id", sa.Integer(), sa.ForeignKey("tool_kit_items.id", ondelete="SET NULL"), nullable=True))
    op.add_column("tools", sa.Column("kit_version", sa.Integer(), nullable=True))
    op.create_index("ix_tools_folder_id", "tools", ["folder_id"])
    op.create_index("ix_tools_kit_item_id", "tools", ["kit_item_id"])


def downgrade():
    op.drop_index("ix_tools_kit_item_id", table_name="tools")
    op.drop_index("ix_tools_folder_id", table_name="tools")
    op.drop_column("tools", "kit_version")
    op.drop_column("tools", "kit_item_id")
    op.drop_column("tools", "folder_id")
    op.drop_table("tool_kit_items")
    op.drop_table("tool_kits")
    op.drop_table("tool_folders")
