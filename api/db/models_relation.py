"""[.mark] Le Hub « Relation clients » en tables : fils (messages et demandes de logiciel), messages, notes sur un client,
témoignages et entrées dans les portails. Builder partie 2, U3 septies (E78).

Dans un module à part (comme ``models_equipe``) : aucun fichier d'amont touché. La migration ``mark_relation_hub`` crée
ces cinq tables. Chacune porte ``organization_id`` et toute lecture ou écriture le filtre (R0).

* un fil = un échange entre un client et .mark ; une demande de logiciel (E93) est un fil qui porte en plus le logiciel
  et son état propre ;
* un message a un côté : ``client``, ``mark`` ou ``interne`` (la note interne ne sort JAMAIS par l'API du client) ;
* l'entrée dans un portail ne garde jamais le jeton, seulement son empreinte (SHA-256), valable une minute, à usage unique.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)

from api.db.models import Base


def _maintenant():
    return datetime.now(UTC)


class MarkRelationFilModel(Base):
    __tablename__ = "mark_relation_fils"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # "message" | "demande_logiciel" | "signalement" (un appel signalé par le client, partie 3 sous-lot 17b)
    sorte = Column(String(24), nullable=False, default="message", server_default="message")
    sujet = Column(String(200), nullable=False)
    # "nouveau" | "en_cours" | "repondu" | "clos"
    etat = Column(String(16), nullable=False, default="nouveau", server_default="nouveau")
    suivi_par = Column(Integer, nullable=True)
    suivi_nom = Column(String(120), nullable=True)
    lu_par_mark = Column(Boolean, nullable=False, default=False, server_default="false")
    # Demande de logiciel seulement.
    logiciel = Column(String(120), nullable=True)
    catalogue = Column(String(120), nullable=True)
    # "nouvelle" | "proposee" | "a_coder" | "refusee"
    etat_demande = Column(String(16), nullable=True)
    # Signalement seulement : l'appel signalé (le lien tombe si l'appel est supprimé) et le problème « À améliorer » créé dans le même geste.
    run_id = Column(Integer, ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True)
    amelioration_id = Column(Integer, nullable=True)
    # Qui a ouvert le fil (« portail : prénom nom » pour le client), pour le filtre « les miens ».
    ouvert_par = Column(String(160), nullable=True)
    cree_le = Column(DateTime(timezone=True), nullable=False, default=_maintenant)
    modifie_le = Column(DateTime(timezone=True), nullable=False, default=_maintenant)

    __table_args__ = (
        Index("ix_mark_relation_fils_org", "organization_id", "modifie_le"),
        Index("ix_mark_relation_fils_ouvert_par", "organization_id", "ouvert_par", "modifie_le"),
    )


class MarkRelationMessageModel(Base):
    __tablename__ = "mark_relation_messages"

    id = Column(BigInteger, primary_key=True)
    fil_id = Column(
        Integer, ForeignKey("mark_relation_fils.id", ondelete="CASCADE"), nullable=False
    )
    organization_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # "client" | "mark" | "interne"
    cote = Column(String(8), nullable=False)
    auteur = Column(String(160), nullable=False)
    texte = Column(Text, nullable=False)
    cree_le = Column(DateTime(timezone=True), nullable=False, default=_maintenant)

    __table_args__ = (Index("ix_mark_relation_messages_fil", "fil_id", "id"),)


class MarkRelationNoteModel(Base):
    """Une note de .mark sur un client : interne, jamais lue par l'API du client."""

    __tablename__ = "mark_relation_notes"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    auteur = Column(String(160), nullable=False)
    texte = Column(Text, nullable=False)
    cree_le = Column(DateTime(timezone=True), nullable=False, default=_maintenant)

    __table_args__ = (Index("ix_mark_relation_notes_org", "organization_id", "id"),)


class MarkRelationTemoignageModel(Base):
    """Un témoignage publiable ; ``accord`` dit que le client a donné son accord (jamais lu par l'API du client)."""

    __tablename__ = "mark_relation_temoignages"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    texte = Column(Text, nullable=False)
    auteur = Column(String(160), nullable=False)
    accord = Column(Boolean, nullable=False, default=False, server_default="false")
    cree_le = Column(DateTime(timezone=True), nullable=False, default=_maintenant)

    __table_args__ = (Index("ix_mark_relation_temoignages_org", "organization_id"),)


class MarkRelationEntreeModel(Base):
    """Une entrée de .mark dans le portail d'un client : le lien signé (empreinte seulement) et sa trace."""

    __tablename__ = "mark_relation_entrees"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(Integer, nullable=True)
    auteur = Column(String(160), nullable=False)
    motif = Column(String(200), nullable=True)
    empreinte_jeton = Column(String(64), nullable=False, unique=True)
    cree_le = Column(DateTime(timezone=True), nullable=False, default=_maintenant)
    expire_le = Column(DateTime(timezone=True), nullable=False)
    utilise_le = Column(DateTime(timezone=True), nullable=True)
    # V4 : la sortie, dite par le portail du client ; la durée de la visite est ``fin_le - utilise_le``.
    fin_le = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_mark_relation_entrees_org", "organization_id", "id"),)
