"""[.mark] Clôture, lot A (décision d'Evan du 09/11) : trois interrupteurs par clé d'API pour les gestes qui coûtent ou engagent, par la porte MCP.

Revision ID: a1c5e9d3b7f2
Revises: f4b8d2a6c1e7

``api_keys.mcp_publier``, ``mcp_tests_payants``, ``mcp_appels_reels`` : ÉTEINTS par défaut, y compris pour les clés déjà existantes (``server_default``
faux). Un interrupteur allumé ne donne rien de plus que le rôle de la clé : il faut en plus que le rôle porte la permission du geste et que le
créateur l'ait. Additive. Réversible : la descente retire les trois colonnes. Table lue et écrite par le serveur de confiance seulement : pas de
politique de sécurité par ligne à poser.
"""

import sqlalchemy as sa
from alembic import op

revision = "a1c5e9d3b7f2"
down_revision = "f4b8d2a6c1e7"
branch_labels = None
depends_on = None

COLONNES = ("mcp_publier", "mcp_tests_payants", "mcp_appels_reels")


def upgrade():
    for nom in COLONNES:
        op.add_column("api_keys", sa.Column(nom, sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    for nom in reversed(COLONNES):
        op.drop_column("api_keys", nom)
