"""[.mark] Partie 3, SA-L3d (décision 21) : les versions des outils et leur épinglage par version d'agent.

Revision ID: d4b8f1a6c9e3
Revises: c7a2e9d4b1f6

Une table ``tool_versions`` (une ligne immuable par version d'un outil), une colonne ``tools.version_courante`` et une colonne
``workflow_definitions.outils_epingles`` (``{tool_uuid: numéro}``, la version de chaque outil que cette version d'agent joue).

Montée, sans rien perdre ni réécrire :
1. chaque outil existant reçoit sa **version 1** (le contenu d'aujourd'hui), ``NOT EXISTS`` : rejouable sans effet double ;
2. chaque version d'agent (publiée, archivée ou brouillon) dont ``outils_epingles`` est vide est épinglée sur la version 1 des
   outils que son graphe cite (aucun outil n'a encore de version 2 : épingler 1 = jouer exactement ce qui jouait). Les versions
   déjà épinglées ne sont pas retouchées (rejouable).

Descente : retire la colonne des épingles, la table et la colonne ; les outils gardent leur contenu courant (rien d'autre n'a
bougé), les numéros de version sont perdus.
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "d4b8f1a6c9e3"
down_revision = "c7a2e9d4b1f6"
branch_labels = None
depends_on = None


def poser_les_versions_un(connexion):
    """La version 1 de chaque outil qui n'a encore aucune version (rejouable)."""
    connexion.execute(
        sa.text(
            "INSERT INTO tool_versions (organization_id, tool_id, version, name, description, category, definition, created_by) "
            "SELECT t.organization_id, t.id, 1, t.name, t.description, t.category::text, t.definition, t.created_by FROM tools t "
            "WHERE NOT EXISTS (SELECT 1 FROM tool_versions v WHERE v.tool_id = t.id)"
        )
    )


def _uuids_du_graphe(graphe) -> list[str]:
    if isinstance(graphe, str):
        try:
            graphe = json.loads(graphe)
        except ValueError:
            return []
    vus: list[str] = []
    for noeud in (graphe or {}).get("nodes") or [] if isinstance(graphe, dict) else []:
        donnees = noeud.get("data") if isinstance(noeud, dict) else None
        for u in (donnees or {}).get("tool_uuids") or []:
            if isinstance(u, str) and u not in vus:
                vus.append(u)
    return vus


def epingler_les_versions_existantes(connexion):
    """Épingle sur la version 1 les outils cités par chaque version d'agent encore sans épingle (rejouable)."""
    outils = {
        uuid: org
        for uuid, org in connexion.execute(sa.text("SELECT tool_uuid, organization_id FROM tools")).all()
    }
    lignes = connexion.execute(
        sa.text(
            "SELECT d.id, d.workflow_json, w.organization_id FROM workflow_definitions d "
            "JOIN workflows w ON w.id = d.workflow_id WHERE d.outils_epingles IS NULL"
        )
    ).all()
    for identifiant, graphe, organisation in lignes:
        epingles = {u: 1 for u in _uuids_du_graphe(graphe) if outils.get(u) == organisation}
        if not epingles:
            continue
        connexion.execute(
            sa.text("UPDATE workflow_definitions SET outils_epingles = CAST(:valeur AS json) WHERE id = :id"),
            {"valeur": json.dumps(epingles), "id": identifiant},
        )


def upgrade():
    op.create_table(
        "tool_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_id", sa.Integer(), sa.ForeignKey("tools.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tool_id", "version", name="uq_tool_versions_outil_version"),
    )
    op.create_index("ix_tool_versions_org_outil", "tool_versions", ["organization_id", "tool_id"])
    op.add_column("tools", sa.Column("version_courante", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("workflow_definitions", sa.Column("outils_epingles", sa.JSON(), nullable=True))
    connexion = op.get_bind()
    poser_les_versions_un(connexion)
    epingler_les_versions_existantes(connexion)


def downgrade():
    op.drop_column("workflow_definitions", "outils_epingles")
    op.drop_column("tools", "version_courante")
    op.drop_index("ix_tool_versions_org_outil", table_name="tool_versions")
    op.drop_table("tool_versions")
