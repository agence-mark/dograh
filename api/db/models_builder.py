"""[.mark] Le builder en tables : ses conversations et leurs événements (builder partie 2, D1 du 03/11).

Dans un module à part (comme ``models_site``). La migration ``mark_builder_conversations`` crée ces deux tables.
Une conversation appartient à une organisation et, le plus souvent, à un agent ; ``parent_id`` relie une conversation
enfant (sous-agent du builder) à son parent. ``historique`` garde ce que le cerveau relit (résumé, messages, dépense) ;
``mark_builder_evenements`` garde ce que l'écran rejoue, dans l'ordre de l'identifiant (la vérité du flux : Redis ne fait
que réveiller les lecteurs).
"""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Text,
    func,
    text,
)

from api.db.models import Base


class MarkBuilderConversationModel(Base):
    __tablename__ = "mark_builder_conversations"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id = Column(Integer, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=True, index=True)
    parent_id = Column(
        Integer, ForeignKey("mark_builder_conversations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id = Column(Integer, nullable=True)
    titre = Column(String(200), nullable=False, default="")
    # nouvelle | en_cours | terminee | arretee | erreur
    etat = Column(String(20), nullable=False, default="nouvelle", server_default="nouvelle")
    demarrage = Column(String(120), nullable=True)
    historique = Column(JSON, nullable=False, default=dict)
    jetons = Column(Integer, nullable=False, default=0, server_default="0")
    cout = Column(Float, nullable=False, default=0.0, server_default="0")
    jauge = Column(Float, nullable=False, default=0.0, server_default="0")
    changements = Column(Integer, nullable=False, default=0, server_default="0")
    # C2 (E96) : un sous-agent est une conversation enfant (genre « sous_agent ») ; le parent garde l'interrupteur des sous-agents.
    genre = Column(String(20), nullable=False, default="principal", server_default="principal")
    delegation_id = Column(String(40), nullable=True)
    usage = Column(String(20), nullable=True)
    tache = Column(Text, nullable=True)
    modele = Column(String(120), nullable=True)
    resultat = Column(JSON, nullable=True)
    sous_agents_actifs = Column(Boolean, nullable=False, default=True, server_default="true")
    # U12 (I1) : une conversation recopiée depuis Claude Code (genre « claude_code ») garde sa session et son auteur.
    session_externe = Column(String(80), nullable=True)
    auteur = Column(String(120), nullable=True)
    cree_le = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=lambda: datetime.now(UTC)
    )
    modifie_le = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class MarkBuilderEvenementModel(Base):
    __tablename__ = "mark_builder_evenements"
    __table_args__ = (Index("ix_mark_builder_evenements_fil", "conversation_id", "id"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(
        Integer, ForeignKey("mark_builder_conversations.id", ondelete="CASCADE"), nullable=False
    )
    type = Column(String(40), nullable=False)
    donnees = Column(JSON, nullable=False, default=dict)
    cree_le = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=lambda: datetime.now(UTC)
    )


class MarkModificationModel(Base):
    """U12 : une écriture sur un élément (agent, brouillon, tests, bibliothèque...), pour la mise à jour en direct de l'écran."""

    __tablename__ = "mark_modifications"
    __table_args__ = (
        Index("ix_mark_modifications_org", "organization_id", "id"),
        Index("ix_mark_modifications_objet", "organization_id", "objet", "id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    objet = Column(String(80), nullable=False)
    action = Column(String(80), nullable=False)
    source = Column(String(20), nullable=False)
    auteur = Column(String(120), nullable=True)
    cree_le = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=lambda: datetime.now(UTC)
    )


class MarkDepenseRoleModel(Base):
    """Partie 3, lot 12 (SE-23) : la dépense du mois de l'appelant simulé ou du juge, par organisation (une ligne par rôle et par mois)."""

    __tablename__ = "mark_depense_roles"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)
    mois = Column(Date, nullable=False)
    appels = Column(Integer, nullable=False, default=0, server_default="0")
    jetons = Column(BigInteger, nullable=False, default=0, server_default="0")
    cout = Column(Float, nullable=False, default=0.0, server_default="0")
    modifie_le = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), default=lambda: datetime.now(UTC))

    __table_args__ = (UniqueConstraint("organization_id", "role", "mois", name="uq_mark_depense_roles_org_role_mois"),)


class WorkflowBranchModel(Base):
    """[.mark] Partie 3, SA-L3b (05 § 12) : une branche d'agent, ligne de versions d'un agent.

    « Principale » existe toujours (une seule par agent, ``est_principale``), ne se supprime pas. Une version est immuable : elle
    reste dans ``workflow_definitions`` (``branch_id`` NULL = principale ; sinon cette branche, statut ``archived`` : la version en
    ligne d'une branche est ``head_definition_id``, jamais le pointeur ``released_definition_id`` de la principale).

    ``part_trafic`` : la part des appels (0 à 99) que reçoit une branche NON principale ; la principale reçoit le reste (le total
    fait toujours 100). ``head_definition_id`` d'une non-principale : la version qu'elle sert ; de la principale : NULL = la version
    publiée de l'agent (suit les publications), sinon une version épinglée (déploiement migré, ou retour en arrière).
    """

    __tablename__ = "workflow_branches"
    __table_args__ = (
        UniqueConstraint("workflow_id", "nom", name="uq_workflow_branches_agent_nom"),
        Index("ix_workflow_branches_org_agent", "organization_id", "workflow_id"),
        Index("uq_workflow_branches_principale", "workflow_id", unique=True, postgresql_where=text("est_principale")),
    )

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    workflow_id = Column(Integer, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    nom = Column(String(60), nullable=False)
    est_principale = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    # active | archivee (une fusion archive sa source, voir SA-L3c)
    statut = Column(String(12), nullable=False, default="active", server_default="active")
    part_trafic = Column(Integer, nullable=False, default=0, server_default="0")
    head_definition_id = Column(Integer, ForeignKey("workflow_definitions.id", use_alter=True, name="fk_workflow_branches_head"), nullable=True)
    base_definition_id = Column(Integer, nullable=True)
    protegee = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    cree_par = Column(Integer, nullable=True)
    cree_le = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), default=lambda: datetime.now(UTC))
    archivee_le = Column(DateTime(timezone=True), nullable=True)


class ToolVersionModel(Base):
    """[.mark] Partie 3, SA-L3d (décision 21) : une version immuable d'un outil.

    Enregistrer un outil modifié range son nouveau contenu ici sous le numéro suivant ; la ligne ne change jamais. Une version
    d'agent épingle un numéro par outil (``workflow_definitions.outils_epingles``) et joue CE contenu, pas le contenu courant.
    ``organization_id`` est redondant avec l'outil exprès : chaque lecture filtre par organisation dans la requête.
    """

    __tablename__ = "tool_versions"
    __table_args__ = (
        UniqueConstraint("tool_id", "version", name="uq_tool_versions_outil_version"),
        Index("ix_tool_versions_org_outil", "organization_id", "tool_id"),
    )

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    tool_id = Column(Integer, ForeignKey("tools.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(String, nullable=True)
    category = Column(String(50), nullable=False)
    definition = Column(JSON, nullable=False, default=dict)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), default=lambda: datetime.now(UTC))


class MarkBuilderJournalModel(Base):
    """[.mark] Partie 3, N1 (SA-N1b, 05 « Trois gardes ») : le journal de ce que le builder ÉCRIT, une ligne par action.

    Qui (``auteur``, ``user_id``), quoi (``action``, ``famille``, ``arguments`` sans secret), quand (``quand``), dans quel mode du
    chat et avec quelle autorisation, et l'état avant et après (``avant``, ``apres``, jamais une valeur de clé). ``annulation``
    dit comment « Annuler » défait l'action (un instantané à restaurer ou l'état d'avant à réécrire), ``NULL`` quand elle ne se
    défait pas (``non_annulable`` en donne la raison). Une ligne ne se réécrit que pour sa clôture et son annulation : l'historique
    ne se supprime pas. Pourquoi pas ``mark_journal`` : celui de l'équipe est un journal de gestes d'équipe sans état avant/après ni
    annulation, lu à travers les clients ; celui-ci est lu par organisation, plus gros, et porte l'état d'annulation.
    """

    __tablename__ = "mark_builder_journal"
    __table_args__ = (
        Index("ix_mark_builder_journal_org_quand", "organization_id", "quand"),
        Index("ix_mark_builder_journal_org_agent", "organization_id", "workflow_id", "id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    quand = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), default=lambda: datetime.now(UTC))
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    workflow_id = Column(Integer, nullable=True)
    fil_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)
    auteur = Column(String(255), nullable=False)
    # ``ecran`` (le chat du builder) ou ``mcp`` (Claude Code)
    porte = Column(String(12), nullable=False, default="ecran", server_default="ecran")
    action = Column(String(120), nullable=False)
    famille = Column(String(24), nullable=False)
    # le mode du chat (``demander``, ``agent``, ``tout``, ``plan``), ``NULL`` hors chat (la personne agit par une route, ou Claude Code)
    mode = Column(String(12), nullable=True)
    # ``mode`` | ``une_fois`` | ``pour_ce_chat`` | ``depense`` | ``personne`` (hors chat) | ``claude_code``
    autorisation = Column(String(16), nullable=False, default="mode", server_default="mode")
    # ``en_cours`` | ``fait`` | ``echec``
    statut = Column(String(10), nullable=False, default="en_cours", server_default="en_cours")
    arguments = Column(JSON, nullable=True)
    avant = Column(JSON, nullable=True)
    apres = Column(JSON, nullable=True)
    annulation = Column(JSON, nullable=True)
    non_annulable = Column(String(24), nullable=True)
    annule_le = Column(DateTime(timezone=True), nullable=True)
    annule_par = Column(String(255), nullable=True)
