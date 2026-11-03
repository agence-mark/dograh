"""[.mark] C4 : les colonnes, filtres et la recherche de la liste des appels (Conversations), en expressions SQL.

Toutes lisent une donnée réelle du run : le motif et le nom du client dans la fiche (``gathered_context``), la note du juge dans sa
colonne, la version jouée dans ``workflow_definitions`` (``definition_id`` du run), le canal dans le mode du run et la marque du widget
(``annotations['embed']``). Aucune ne demande une requête de plus : elles s'ajoutent à la requête de la liste.
"""

from __future__ import annotations

from sqlalchemy import Text, and_, case, cast, exists, func, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONB

from api.db.models import WorkflowDefinitionModel, WorkflowRunModel

CHAMPS_MOTIF = ("motif_appel", "motif")
RECHERCHE_MIN = 3
RECHERCHE_MAX = 80
# Une recherche ne balaie jamais plus que ces appels, les plus récents de l'organisation dans la période.
RECHERCHE_APPELS_MAX = 2000
RECHERCHE_JOURS_PAR_DEFAUT = 30
GENRES_DE_TRANSCRIPTION = ("rtf-user-transcription", "rtf-bot-text")


def _texte(colonne, cle: str):
    return cast(cast(colonne, JSONB).op("->>")(literal(cle)), Text)


def motif():
    """Le motif d'appel classé : le premier champ présent de la fiche (même règle que les indicateurs de la boucle)."""
    return func.nullif(func.coalesce(*[func.nullif(_texte(WorkflowRunModel.gathered_context, c), "") for c in CHAMPS_MOTIF]), "")


def client():
    """Qui a appelé : « prénom nom » de la fiche, sinon rien (l'écran montre alors le numéro)."""
    prenom = func.coalesce(_texte(WorkflowRunModel.gathered_context, "prenom"), "")
    nom = func.coalesce(_texte(WorkflowRunModel.gathered_context, "nom"), "")
    return func.nullif(func.trim(prenom + literal(" ") + nom), "")


def version_jouee():
    return (
        select(WorkflowDefinitionModel.version_number)
        .where(WorkflowDefinitionModel.id == WorkflowRunModel.definition_id)
        .correlate(WorkflowRunModel)
        .scalar_subquery()
    )


def depuis_le_site():
    """Vrai pour une conversation lancée depuis le widget d'un site (voix ou écrit)."""
    return cast(WorkflowRunModel.annotations, JSONB).op("->")(literal("embed")).op("->>")(literal("source")) == "embed_widget"


def echapper_like(terme: str) -> str:
    return terme.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def filtre_motif(terme: str):
    return motif().ilike(f"%{echapper_like(terme)}%", escape="\\")


def filtre_client(terme: str):
    modele = f"%{echapper_like(terme)}%"
    numero = _texte(WorkflowRunModel.initial_context, "caller_number")
    return or_(client().ilike(modele, escape="\\"), numero.ilike(modele, escape="\\"))


def filtre_version(numero: int):
    return WorkflowRunModel.definition_id.in_(select(WorkflowDefinitionModel.id).where(WorkflowDefinitionModel.version_number == numero))


def terme_de_recherche(brut: str | None) -> str | None:
    """Le terme nettoyé, ou ``None`` s'il est trop court pour chercher."""
    terme = " ".join((brut or "").split())[:RECHERCHE_MAX]
    return terme if len(terme) >= RECHERCHE_MIN else None


def contient_dans_la_transcription(terme: str):
    """Une réplique (de l'appelant ou de l'agent) du journal du run contient le terme, sans tenir compte de la casse."""
    journal = cast(WorkflowRunModel.logs, JSONB).op("->")(literal("realtime_feedback_events"))
    sain = case((func.jsonb_typeof(journal) == "array", journal), else_=cast(literal("[]"), JSONB))
    evenements = func.jsonb_array_elements(sain).table_valued("value")
    valeur = evenements.c.value
    return exists(
        select(literal(1))
        .select_from(evenements)
        .where(
            and_(
                valeur.op("->>")(literal("type")).in_(GENRES_DE_TRANSCRIPTION),
                valeur.op("->")(literal("payload")).op("->>")(literal("text")).ilike(f"%{echapper_like(terme)}%", escape="\\"),
            )
        )
        .correlate(WorkflowRunModel)
    )
