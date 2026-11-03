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
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
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
