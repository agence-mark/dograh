"""[.mark] Partie 3, SA-L3b (05 § 12) : les branches d'agent et le rattachement des versions et des brouillons.

Revision ID: c7a2e9d4b1f6
Revises: a3d9e5b7c142

Une table ``workflow_branches`` (une ligne par branche, « Principale » toujours présente), et deux colonnes sur
``workflow_definitions`` : ``branch_id`` (NULL = principale, donc AUCUNE version existante n'est réécrite) et ``draft_owner_id``
(un brouillon de branche appartient à une personne). Un index sur (agent, branche, statut) sert la lecture du brouillon.

Montée : crée la table, ajoute les colonnes, puis pose la ligne « Principale » (100 % du trafic) de chaque agent qui n'en a pas
(``NOT EXISTS`` : rejouable sans effet double). Les déploiements progressifs en cours (lignes ``MARK_DEPLOIEMENT:*``) sont repris par
le script ``scripts/mark/migrer_branches.py`` (sauvegarde d'abord), pas ici.

Descente : supprime les brouillons des branches (sinon ils se mêleraient au brouillon unique de la principale), retire les colonnes
puis la table. Les versions publiées sur une branche restent, immuables, dans l'historique (un appel passé peut les porter).
"""

import sqlalchemy as sa
from alembic import op

revision = "c7a2e9d4b1f6"
down_revision = "a3d9e5b7c142"
branch_labels = None
depends_on = None


def poser_les_principales(connexion):
    """Une ligne « Principale » par agent qui n'en a pas encore (rejouable sans effet double)."""
    connexion.execute(
        sa.text(
            "INSERT INTO workflow_branches (organization_id, workflow_id, nom, est_principale, statut, part_trafic, protegee) "
            "SELECT w.organization_id, w.id, 'Principale', true, 'active', 100, false FROM workflows w "
            "WHERE w.organization_id IS NOT NULL AND NOT EXISTS "
            "(SELECT 1 FROM workflow_branches b WHERE b.workflow_id = w.id AND b.est_principale)"
        )
    )


def upgrade():
    op.create_table(
        "workflow_branches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_id", sa.Integer(), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nom", sa.String(60), nullable=False),
        sa.Column("est_principale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("statut", sa.String(12), nullable=False, server_default="active"),
        sa.Column("part_trafic", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("head_definition_id", sa.Integer(), nullable=True),
        sa.Column("base_definition_id", sa.Integer(), nullable=True),
        sa.Column("protegee", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cree_par", sa.Integer(), nullable=True),
        sa.Column("cree_le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("archivee_le", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("workflow_id", "nom", name="uq_workflow_branches_agent_nom"),
        sa.CheckConstraint("part_trafic BETWEEN 0 AND 100", name="ck_workflow_branches_part"),
    )
    op.create_foreign_key(
        "fk_workflow_branches_head", "workflow_branches", "workflow_definitions", ["head_definition_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_workflow_branches_org_agent", "workflow_branches", ["organization_id", "workflow_id"])
    op.create_index(
        "uq_workflow_branches_principale",
        "workflow_branches",
        ["workflow_id"],
        unique=True,
        postgresql_where=sa.text("est_principale"),
    )
    op.add_column("workflow_definitions", sa.Column("branch_id", sa.Integer(), nullable=True))
    op.add_column("workflow_definitions", sa.Column("draft_owner_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_workflow_definitions_branch", "workflow_definitions", "workflow_branches", ["branch_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_foreign_key(
        "fk_workflow_definitions_draft_owner", "workflow_definitions", "users", ["draft_owner_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index(
        "ix_workflow_definitions_agent_branche_statut", "workflow_definitions", ["workflow_id", "branch_id", "status"]
    )
    poser_les_principales(op.get_bind())


def descendre_les_brouillons_de_branche(connexion):
    connexion.execute(sa.text("DELETE FROM workflow_definitions WHERE status = 'draft' AND branch_id IS NOT NULL"))


def downgrade():
    descendre_les_brouillons_de_branche(op.get_bind())
    op.drop_index("ix_workflow_definitions_agent_branche_statut", table_name="workflow_definitions")
    op.drop_constraint("fk_workflow_definitions_draft_owner", "workflow_definitions", type_="foreignkey")
    op.drop_constraint("fk_workflow_definitions_branch", "workflow_definitions", type_="foreignkey")
    op.drop_column("workflow_definitions", "draft_owner_id")
    op.drop_column("workflow_definitions", "branch_id")
    op.drop_index("uq_workflow_branches_principale", table_name="workflow_branches")
    op.drop_index("ix_workflow_branches_org_agent", table_name="workflow_branches")
    op.drop_constraint("fk_workflow_branches_head", "workflow_branches", type_="foreignkey")
    op.drop_table("workflow_branches")
