"""[.mark] Partie 3, lot 12 (SE-23, M-5 et M-6) : la dépense suivie de l'appelant simulé et du juge.

Revision ID: a3d9e5b7c142
Revises: f1a8c3d5e702

Une table ``mark_depense_roles`` : par organisation, par rôle (« appelant » ou « juge ») et par mois civil (UTC), le nombre d'appels
au modèle, les jetons et le coût. Le budget du mois de chaque rôle se compare à cette ligne avant chaque appel.

Les réglages existants (ligne ``APPELANT_SIMULE`` de ``organization_configurations``) gagnent l'interrupteur ``actif`` : les
organisations qui ont déjà réglé leur appelant ou leur juge gardent le fonctionnement actuel (``actif`` = vrai, posé seulement
quand le champ est absent, donc rejouable sans effet double) ; une organisation neuve démarre éteinte (réglage coûteux).
Réversible : la descente supprime la table et retire ``actif`` et ``budget_mois`` des deux rôles.
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "a3d9e5b7c142"
down_revision = "f1a8c3d5e702"
branch_labels = None
depends_on = None

CLE = "APPELANT_SIMULE"
ROLES = ("appelant", "juge")


def _lignes(connexion):
    return connexion.execute(
        sa.text("SELECT id, value FROM organization_configurations WHERE key = :cle"), {"cle": CLE}
    ).fetchall()


def _ecrire(connexion, identifiant, valeur):
    connexion.execute(
        sa.text("UPDATE organization_configurations SET value = CAST(:v AS json) WHERE id = :i"),
        {"v": json.dumps(valeur), "i": identifiant},
    )


def allumer_les_roles(connexion):
    """Pose ``actif`` = vrai sur les rôles déjà écrits qui n'ont pas ce champ (rejouable sans effet double)."""
    for identifiant, valeur in _lignes(connexion):
        if not isinstance(valeur, dict):
            continue
        change = False
        for role in ROLES:
            bloc = valeur.get(role)
            if isinstance(bloc, dict) and "actif" not in bloc:
                bloc["actif"] = True
                change = True
        if change:
            _ecrire(connexion, identifiant, valeur)


def upgrade():
    op.create_table(
        "mark_depense_roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("mois", sa.Date(), nullable=False),
        sa.Column("appels", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jetons", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cout", sa.Float(), nullable=False, server_default="0"),
        sa.Column("modifie_le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "role", "mois", name="uq_mark_depense_roles_org_role_mois"),
        sa.CheckConstraint("role IN ('appelant', 'juge')", name="ck_mark_depense_roles_role"),
    )
    allumer_les_roles(op.get_bind())


def downgrade():
    connexion = op.get_bind()
    for identifiant, valeur in _lignes(connexion):
        if not isinstance(valeur, dict):
            continue
        change = False
        for role in ROLES:
            bloc = valeur.get(role)
            if isinstance(bloc, dict):
                for champ in ("actif", "budget_mois"):
                    if champ in bloc:
                        bloc.pop(champ)
                        change = True
        if change:
            _ecrire(connexion, identifiant, valeur)
    op.drop_table("mark_depense_roles")
