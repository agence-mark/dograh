"""[.mark] Clôture, É36 : qui a créé une version d'agent et ce qu'elle change.

Revision ID: b7d3f1a9c5e2
Revises: a1c5e9d3b7f2

Cinq colonnes sur ``workflow_definitions``, TOUTES nullables et sans valeur par défaut : les versions d'avant restent vides (l'écran
met « – »), aucune donnée n'est réécrite.

* ``auteur_type`` : ``personne`` | ``builder`` | ``cle_api`` (vide : version d'avant, ou geste sans auteur connu) ;
* ``auteur_user_id`` : le compte (personne connectée, ou propriétaire de la clé) ;
* ``auteur_libelle`` : le nom de la clé d'API, ou l'auteur du portail (jamais une adresse) ;
* ``accepte_par_user_id`` : la personne qui a accepté (changement proposé par le builder, fusion de branche) ;
* ``resume_changements`` : « Ce qui change » en données neutres (genres, comptes, noms d'étapes), calculé à la publication.

Additive. Réversible : la descente retire les cinq colonnes. Table lue et écrite par le serveur de confiance seulement : pas de
politique de sécurité par ligne à poser. Aucun index : l'historique se lit par ``(workflow_id, status)``, déjà indexé.
"""

import sqlalchemy as sa
from alembic import op

revision = "b7d3f1a9c5e2"
down_revision = "a1c5e9d3b7f2"
branch_labels = None
depends_on = None

COLONNES = (
    ("auteur_type", sa.String(12)),
    ("auteur_user_id", sa.Integer()),
    ("auteur_libelle", sa.String(160)),
    ("accepte_par_user_id", sa.Integer()),
    ("resume_changements", sa.JSON()),
)


def upgrade():
    for nom, type_ in COLONNES:
        op.add_column("workflow_definitions", sa.Column(nom, type_, nullable=True))


def downgrade():
    for nom, _type in reversed(COLONNES):
        op.drop_column("workflow_definitions", nom)
