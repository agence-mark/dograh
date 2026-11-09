"""[.mark] Clôture, lot B (D5, D6, D7) : la protection de la version en ligne devient un RÉGLAGE PAR AGENT.

Revision ID: f4b8d2a6c1e7
Revises: e3a9c7b2d4f6

``workflow_branches.protection_choisie`` (sur la ligne de la principale) : ``NULL`` = la règle par défaut (allumée chez un client à la première
publication par une personne, éteinte au Labo) ; ``true`` ou ``false`` = le choix de l'équipe pour CET agent, journalisé. Aucune donnée réécrite :
tant que personne ne choisit, rien ne change pour les agents existants.

Additive. Réversible : la descente retire la colonne. Table lue et écrite par le serveur de confiance seulement (aucun rôle de portail, de site ou
de salarié n'y accède) : pas de politique de sécurité par ligne à poser.
"""

import sqlalchemy as sa
from alembic import op

revision = "f4b8d2a6c1e7"
down_revision = "e3a9c7b2d4f6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("workflow_branches", sa.Column("protection_choisie", sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column("workflow_branches", "protection_choisie")
