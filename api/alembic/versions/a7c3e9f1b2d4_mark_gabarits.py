"""[.mark] Chantier Partie 1, lot 17 : les gabarits d'agent (D11), leurs applications et leurs diffusions.

Revision ID: a7c3e9f1b2d4
Revises: d4e9b1c7a3f5

Migration .mark additive (rien n'est réécrit, aucune donnée supprimée) :

- ``mark_gabarits`` : une version FIGÉE d'un gabarit (nom, version, contenu, empreinte). Une version ne change jamais : un contenu différent
  est une nouvelle version ;
- ``mark_gabarit_applications`` : un agent installé depuis un gabarit (le principal du groupe, ses étapes) : version du gabarit, commit du
  fork, trous remplis, empreinte et contenu de ses retouches, son rodage (appels réels relus, D28) ;
- ``mark_gabarit_diffusions`` : le journal des diffusions d'une version (qui, quoi, quand, portée, résultat agent par agent).

Ces tables ne sont lues que par le serveur de confiance (aucun rôle de portail ni de salarié) : pas de RLS, le cloisonnement est dans
chaque requête de la couche d'accès (``gabarits_client.py``). Réversible.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "a7c3e9f1b2d4"
down_revision = "d4e9b1c7a3f5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mark_gabarits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nom", sa.String(60), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("contenu", JSONB(), nullable=False),
        sa.Column("empreinte", sa.String(64), nullable=False),
        sa.Column("statut", sa.String(12), nullable=False, server_default="actif"),
        sa.Column("cree_le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("nom", "version", name="uq_mark_gabarits_nom_version"),
        sa.CheckConstraint("statut IN ('actif', 'retire')", name="ck_mark_gabarits_statut"),
        sa.CheckConstraint("version >= 1", name="ck_mark_gabarits_version"),
    )
    op.create_table(
        "mark_gabarit_applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_id", sa.Integer(), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gabarit_nom", sa.String(60), nullable=False),
        sa.Column("gabarit_version", sa.Integer(), nullable=False),
        sa.Column("commit_fork", sa.String(64), nullable=True),
        sa.Column("agents", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("trous", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("formulaire", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("retouches", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("empreinte_retouches", sa.String(64), nullable=True),
        sa.Column("rodage_relus", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("installee_le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("maj_le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workflow_id", name="uq_mark_gabarit_applications_workflow"),
    )
    op.create_index("ix_mark_gabarit_applications_organization_id", "mark_gabarit_applications", ["organization_id"])
    op.create_index("ix_mark_gabarit_applications_gabarit", "mark_gabarit_applications", ["gabarit_nom", "gabarit_version"])
    op.create_table(
        "mark_gabarit_diffusions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("gabarit_nom", sa.String(60), nullable=False),
        sa.Column("gabarit_version", sa.Integer(), nullable=False),
        sa.Column("portee", sa.String(14), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("par_user_id", sa.Integer(), nullable=True),
        sa.Column("statut", sa.String(12), nullable=False),
        sa.Column("resultat", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("portee IN ('organisation', 'toutes')", name="ck_mark_gabarit_diffusions_portee"),
        sa.CheckConstraint("statut IN ('refusee', 'faite', 'partielle')", name="ck_mark_gabarit_diffusions_statut"),
    )
    op.create_index("ix_mark_gabarit_diffusions_organization_id", "mark_gabarit_diffusions", ["organization_id"])
    op.create_index("ix_mark_gabarit_diffusions_gabarit", "mark_gabarit_diffusions", ["gabarit_nom", "le"])


def downgrade():
    op.drop_index("ix_mark_gabarit_diffusions_gabarit", table_name="mark_gabarit_diffusions")
    op.drop_index("ix_mark_gabarit_diffusions_organization_id", table_name="mark_gabarit_diffusions")
    op.drop_table("mark_gabarit_diffusions")
    op.drop_index("ix_mark_gabarit_applications_gabarit", table_name="mark_gabarit_applications")
    op.drop_index("ix_mark_gabarit_applications_organization_id", table_name="mark_gabarit_applications")
    op.drop_table("mark_gabarit_applications")
    op.drop_table("mark_gabarits")
