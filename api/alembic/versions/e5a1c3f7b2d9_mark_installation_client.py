"""[.mark] Partie 3, sous-lot 9 (SE-5, § 5 du plan) : l'installation d'un nouveau client, étape par étape.

Revision ID: e5a1c3f7b2d9
Revises: d4b8f1a6c9e3

Deux tables neuves, rien d'existant n'est touché :

* ``mark_installations_client`` : une installation par organisation cliente (qui l'a lancée, quand, son état). **Une seule
  installation ouverte par client** : index unique partiel sur ``organization_id`` quand ``etat = 'ouverte'`` ;
* ``mark_installations_client_etapes`` : les neuf étapes d'une installation (étape, état, qui, quand, dernière erreur, ce
  qu'elle a produit, sans aucun secret). ``organization_id`` est recopié pour que chaque lecture filtre par organisation dans
  la requête. Une ligne par étape (unique sur installation et numéro).

Lues et écrites par le serveur seul (l'équipe .mark), jamais par le portail ni par un rôle d'une base du client : pas de RLS.

Descente : supprime les deux tables (les installations en cours sont perdues ; les organisations, bases, agents et clés
qu'elles ont créés restent, ils vivent dans leurs propres tables).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e5a1c3f7b2d9"
down_revision = "d4b8f1a6c9e3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mark_installations_client",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nom", sa.String(100), nullable=False),
        sa.Column("etat", sa.String(12), nullable=False, server_default="ouverte"),
        sa.Column("cree_par", sa.Integer(), nullable=True),
        sa.Column("cree_le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("terminee_le", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("etat IN ('ouverte', 'terminee', 'abandonnee')", name="ck_mark_installations_client_etat"),
    )
    op.create_index(
        "uq_mark_installations_client_ouverte",
        "mark_installations_client",
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text("etat = 'ouverte'"),
    )
    op.create_table(
        "mark_installations_client_etapes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "installation_id",
            sa.Integer(),
            sa.ForeignKey("mark_installations_client.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("numero", sa.SmallInteger(), nullable=False),
        sa.Column("etat", sa.String(10), nullable=False, server_default="a_faire"),
        sa.Column("par", sa.Integer(), nullable=True),
        sa.Column("le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("debut", sa.DateTime(timezone=True), nullable=True),
        sa.Column("derniere_erreur", sa.String(300), nullable=True),
        sa.Column("resultat", postgresql.JSONB(), nullable=True),
        sa.UniqueConstraint("installation_id", "numero", name="uq_mark_installations_client_etapes_numero"),
        sa.CheckConstraint("numero BETWEEN 1 AND 9", name="ck_mark_installations_client_etapes_numero"),
        sa.CheckConstraint(
            "etat IN ('a_faire', 'en_cours', 'faite', 'erreur', 'passee')", name="ck_mark_installations_client_etapes_etat"
        ),
    )
    op.create_index(
        "ix_mark_installations_client_etapes_org", "mark_installations_client_etapes", ["organization_id", "installation_id"]
    )


def downgrade():
    op.drop_index("ix_mark_installations_client_etapes_org", table_name="mark_installations_client_etapes")
    op.drop_table("mark_installations_client_etapes")
    op.drop_index("uq_mark_installations_client_ouverte", table_name="mark_installations_client")
    op.drop_table("mark_installations_client")
