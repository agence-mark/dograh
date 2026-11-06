"""[.mark] L'équipe en tables : rôles, permissions, membres, invitations, journal.

Revision ID: b4e2a7c19d30
Revises: 7c4e1a9b2d58

Chantier builder partie 2, U2 ter. Migration .mark permise (additive, nommée ``mark_*``, rien d'amont modifié).
Graine : le rôle Administrateur (fixe, toutes les permissions, le Labo et tous les clients) et le rôle Membre
(quatre permissions courantes). Revue serveur M8 : seuls des comptes NOMMÉS deviennent Administrateurs, jamais tous
les comptes présents :

* ``MARK_ADMINISTRATEURS`` (adresses séparées par des virgules, casse ignorée) : ces comptes-là ;
* variable absente ou vide, ou aucune adresse trouvée : le plus ancien compte seul (le premier compte, comme A2),
  pour qu'une installation ne reste jamais sans administrateur ;
* tous les autres comptes restent sans rôle (ils ne voient que leurs organisations, routes ``MEMBRE``).

Réversible : ``downgrade`` retire les six tables.
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "b4e2a7c19d30"
down_revision = "7c4e1a9b2d58"
branch_labels = None
depends_on = None

# Les 15 permissions (même liste que api/services/equipe/permissions.py ; recopiée : une migration ne dépend pas du code vivant).
PERMISSIONS = [
    "agents.modifier",
    "agents.publier",
    "agents.supprimer",
    "builder.lancer",
    "tests.jouer",
    "clients.creer",
    "clients.exporter_ramener",
    "clients.ouvrir_portail",
    "cles.gerer",
    "telephonie.gerer",
    "conversations.voir",
    "donnees.exporter",
    "equipe.gerer",
    "roles.gerer",
    "atelier.regler",
]
PERMISSIONS_MEMBRE = ["agents.modifier", "builder.lancer", "tests.jouer", "conversations.voir"]
VARIABLE_ADMINISTRATEURS = "MARK_ADMINISTRATEURS"


def adresses_des_administrateurs(brut: str | None) -> list[str]:
    """Les adresses de ``MARK_ADMINISTRATEURS``, en minuscules, sans doublon ni vide."""
    return sorted({a.strip().lower() for a in (brut or "").split(",") if a.strip()})


def promotion(connexion, brut: str | None) -> tuple[list[int], list[str], str]:
    """(comptes à promouvoir, adresses nommées mais introuvables, raison) : les comptes nommés par la variable ; à défaut, le
    plus ancien compte seul ; aucun si la base n'a aucun compte. Revue de contrôle, point 7 : l'adresse mal tapée se voit."""
    adresses = adresses_des_administrateurs(brut)
    introuvables: list[str] = list(adresses)
    if adresses:
        trouves = connexion.execute(
            sa.text("SELECT id, lower(email) FROM users WHERE lower(email) IN :adresses ORDER BY id").bindparams(
                sa.bindparam("adresses", expanding=True)
            ),
            {"adresses": adresses},
        ).all()
        introuvables = [a for a in adresses if a not in {mail for _, mail in trouves}]
        if trouves:
            return [i for i, _ in trouves], introuvables, "nommés"
    premier = connexion.execute(
        sa.text("SELECT id FROM users ORDER BY created_at ASC NULLS LAST, id ASC LIMIT 1")
    ).scalar()
    raison = "aucun compte nommé trouvé : repli sur le plus ancien compte" if adresses else "variable absente : plus ancien compte"
    return ([premier] if premier is not None else []), introuvables, raison


def comptes_a_promouvoir(connexion, brut: str | None) -> list[int]:
    return promotion(connexion, brut)[0]


def rapport_de_promotion(promus: list[int], introuvables: list[str], raison: str) -> list[str]:
    """Les lignes écrites dans la sortie de la migration : les identifiants promus et les adresses nommées introuvables.
    Jamais l'adresse d'un autre compte (seules celles de la variable, qu'on vient de taper, reviennent)."""
    lignes = [f"[.mark] {VARIABLE_ADMINISTRATEURS} ({raison}) : comptes promus Administrateurs (id) : {', '.join(map(str, promus)) or 'aucun'}"]
    if introuvables:
        lignes.append(f"[.mark] {VARIABLE_ADMINISTRATEURS} : adresses introuvables, ignorées : {', '.join(introuvables)}")
    return lignes


def upgrade():
    op.create_table(
        "mark_roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nom", sa.String(80), nullable=False),
        sa.Column("fixe", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("labo_ouvert", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("tous_les_clients", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("cree_le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ux_mark_roles_nom_lower", "mark_roles", [sa.text("lower(nom)")], unique=True)
    op.create_table(
        "mark_role_permissions",
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("mark_roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission", sa.String(64), primary_key=True),
    )
    op.create_table(
        "mark_role_organisations",
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("mark_roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "mark_membres",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("mark_roles.id"), nullable=False),
        sa.Column("prenom", sa.String(120), nullable=True),
        sa.Column("nom", sa.String(120), nullable=True),
        sa.Column("cree_le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_mark_membres_role_id", "mark_membres", ["role_id"])
    op.create_table(
        "mark_invitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("mark_roles.id"), nullable=False),
        sa.Column("empreinte_jeton", sa.String(64), nullable=False),
        sa.Column("cree_par", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cree_le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expire_le", sa.DateTime(timezone=True), nullable=False),
        sa.Column("utilisee_le", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("empreinte_jeton", name="uq_mark_invitations_empreinte"),
    )
    op.create_index("ix_mark_invitations_email", "mark_invitations", [sa.text("lower(email)")])
    op.create_table(
        "mark_journal",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("quand", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("auteur", sa.String(255), nullable=False),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
    )
    op.create_index("ix_mark_journal_quand", "mark_journal", ["quand"])
    op.create_index("ix_mark_journal_organization_id", "mark_journal", ["organization_id"])

    # Graine : Administrateur (fixe) et Membre.
    connexion = op.get_bind()
    admin_id = connexion.execute(
        sa.text(
            "INSERT INTO mark_roles (nom, fixe, labo_ouvert, tous_les_clients) "
            "VALUES ('Administrateur', true, true, true) RETURNING id"
        )
    ).scalar()
    membre_id = connexion.execute(
        sa.text(
            "INSERT INTO mark_roles (nom, fixe, labo_ouvert, tous_les_clients) "
            "VALUES ('Membre', false, true, true) RETURNING id"
        )
    ).scalar()
    for permission in PERMISSIONS:
        connexion.execute(
            sa.text("INSERT INTO mark_role_permissions (role_id, permission) VALUES (:r, :p)"),
            {"r": admin_id, "p": permission},
        )
    for permission in PERMISSIONS_MEMBRE:
        connexion.execute(
            sa.text("INSERT INTO mark_role_permissions (role_id, permission) VALUES (:r, :p)"),
            {"r": membre_id, "p": permission},
        )
    promus, introuvables, raison = promotion(connexion, os.environ.get(VARIABLE_ADMINISTRATEURS))
    for ligne in rapport_de_promotion(promus, introuvables, raison):
        print(ligne)
    for user_id in promus:
        connexion.execute(
            sa.text("INSERT INTO mark_membres (user_id, role_id) VALUES (:u, :r)"),
            {"u": user_id, "r": admin_id},
        )


def downgrade():
    op.drop_index("ix_mark_journal_organization_id", table_name="mark_journal")
    op.drop_index("ix_mark_journal_quand", table_name="mark_journal")
    op.drop_table("mark_journal")
    op.drop_index("ix_mark_invitations_email", table_name="mark_invitations")
    op.drop_table("mark_invitations")
    op.drop_index("ix_mark_membres_role_id", table_name="mark_membres")
    op.drop_table("mark_membres")
    op.drop_table("mark_role_organisations")
    op.drop_table("mark_role_permissions")
    op.drop_index("ux_mark_roles_nom_lower", table_name="mark_roles")
    op.drop_table("mark_roles")
