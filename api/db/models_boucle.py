"""[.mark] builder partie 2, U8 : la boucle d'amélioration en table (« À améliorer »).

Un problème = une ligne, qui REGROUPE ses cas : même agent, même critère ou contrôle, même étape (``cle``). Chaque cas (un appel, un
test) s'ajoute à la ligne ; la fréquence « N appels sur M » se calcule à la lecture, jamais stockée. L'état (à trier, en cours,
testée, publiée, ignorée) est celui du PROBLÈME, pas d'un appel : c'est ce que la page montre en boîtes de réception.

⛔ Une organisation ne lit jamais les problèmes d'une autre : chaque lecture et chaque écriture passe par ``organization_id``.
Cette table n'est lue par aucun rôle autre que le serveur : pas de RLS ici (règle 31 : RLS pour les tables d'une base de client).
"""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from api.db.models import Base


class MarkAmeliorationModel(Base):
    __tablename__ = "mark_ameliorations"
    __table_args__ = (
        UniqueConstraint("organization_id", "workflow_id", "cle", name="uq_mark_ameliorations_groupe"),
        Index("ix_mark_ameliorations_file", "organization_id", "etat", "derniere_le"),
    )

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    workflow_id = Column(Integer, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    # La clé de regroupement : « <relevé par>:<critère ou contrôle>:<étape> », normalisée.
    cle = Column(String(240), nullable=False)
    # juge | code | test | equipe | client | deploiement
    releve_par = Column(String(16), nullable=False)
    titre = Column(Text, nullable=False)
    critere = Column(String(240), nullable=True)
    etape = Column(String(160), nullable=True)
    gravite = Column(Integer, nullable=False, default=2, server_default="2")
    # prompt | outil | donnee | voix | moteur
    cause = Column(String(16), nullable=True)
    action = Column(String(200), nullable=True)
    # a_trier | en_cours | testee | publiee | ignoree
    etat = Column(String(16), nullable=False, default="a_trier", server_default="a_trier")
    # client | recette | code : l'origine posée par la personne (la suggérée se calcule)
    origine = Column(String(16), nullable=True)
    assigne = Column(Integer, nullable=True)
    replique = Column(Text, nullable=True)
    confiance = Column(Float, nullable=True)
    # Les cas regroupés (au plus 50, les plus récents) : {run_id, test, tour, le, citation}
    cas = Column(JSON, nullable=False, default=list)
    nb_cas = Column(Integer, nullable=False, default=0, server_default="0")
    # La correction proposée : {etape, cible, avant, apres}. Rien d'inventé : absente tant que le builder n'en a pas posé.
    correction = Column(JSON, nullable=True)
    # test_cree | brouillon | rejoue | publie : les quatre temps de l'avancement
    avancement = Column(JSON, nullable=False, default=dict)
    version_numero = Column(Integer, nullable=True)
    premiere_le = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    derniere_le = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    cree_le = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), default=lambda: datetime.now(UTC))
    modifie_le = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
