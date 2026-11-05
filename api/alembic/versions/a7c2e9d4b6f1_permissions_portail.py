"""[.mark] Partie 3, sous-lot 17a : deux permissions propres au portail, accordées aux rôles qui gèrent déjà les clés.

Revision ID: a7c2e9d4b6f1
Revises: e5a1c3f7b2d9

* ``connecteurs.autoriser`` : autoriser, reconnecter et couper les comptes d'un client (ouverte à la clé du client) ;
* ``base_client.connexion_portail`` : l'accès du portail à la base du client (ouverte à la clé du client).

Avant ce lot, ces gestes exigeaient ``cles.gerer`` : les rôles qui la portent gardent donc ces deux gestes (aucun droit perdu).
Additive et idempotente (``ON CONFLICT DO NOTHING``). Réversible : la descente retire les deux permissions de tous les rôles.
"""

from alembic import op

revision = "a7c2e9d4b6f1"
down_revision = "e5a1c3f7b2d9"
branch_labels = None
depends_on = None

NOUVELLES = ("connecteurs.autoriser", "base_client.connexion_portail")


def upgrade():
    for permission in NOUVELLES:
        op.execute(
            "INSERT INTO mark_role_permissions (role_id, permission) "
            f"SELECT role_id, '{permission}' FROM mark_role_permissions WHERE permission = 'cles.gerer' "
            "ON CONFLICT DO NOTHING"
        )


def downgrade():
    op.execute("DELETE FROM mark_role_permissions WHERE permission IN ('connecteurs.autoriser', 'base_client.connexion_portail')")
