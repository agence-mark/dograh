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


def motif_de_la_fiche(fiche) -> str | None:
    """Le motif d'appel d'une fiche déjà lue (même règle que ``motif()``, en Python). Pur."""
    fiche = fiche if isinstance(fiche, dict) else {}
    for champ in CHAMPS_MOTIF:
        valeur = str(fiche.get(champ) or "").strip()
        if valeur:
            return valeur
    return None


def juge_par(annotations) -> str | None:
    """Qui a jugé l'appel (RA-B R6, 05 § 9) : « Claude Code », ou le modèle du juge sur clé d'API, lu dans l'annotation
    ``juge`` du run ; ``None`` tant que rien ne l'a jugé (juge éteint, non réglé, budget atteint…). Pur."""
    juge = annotations.get("juge") if isinstance(annotations, dict) else None
    if not isinstance(juge, dict):
        return None
    if juge.get("source") == "claude_code":
        # Clôture SA-5 : la personne derrière la session, quand le portail ou la clé la dit (jamais une adresse).
        par = juge.get("par")
        return f"Claude Code · {par.strip()}" if isinstance(par, str) and par.strip() else "Claude Code"
    modele = juge.get("modele")
    return modele.strip() or None if isinstance(modele, str) else None


def issue():
    """L'issue de l'appel : le code rangé par le classement de fin d'appel (``mapped_call_disposition``)."""
    return func.nullif(_texte(WorkflowRunModel.gathered_context, "mapped_call_disposition"), "")


def _texte_imbrique(colonne, *chemin: str):
    expression = cast(colonne, JSONB)
    for cle in chemin[:-1]:
        expression = expression.op("->")(literal(cle))
    return cast(expression.op("->>")(literal(chemin[-1])), Text)


def filtre_recherche(terme: str, *autres):
    """Clôture SA-5 (É8, É35) : « Chercher un mot » de la liste : le motif, l'issue, le résumé de l'après-appel ou celui du modèle
    contient le terme (casse ignorée, jokers = texte). ``autres`` : d'autres colonnes de la requête (nom de l'agent, du client)."""
    modele = f"%{echapper_like(terme)}%"
    colonnes = [
        motif(),
        issue(),
        _texte_imbrique(WorkflowRunModel.annotations, "mark_apres_appel", "synthese"),
        _texte_imbrique(WorkflowRunModel.annotations, "resume_appel", "texte"),
        *autres,
    ]
    return or_(*[c.ilike(modele, escape="\\") for c in colonnes])


def motif_replie():
    """Le motif, espaces repliés et sans casse : la clé qui réunit « Devis » et « devis »."""
    return func.lower(func.regexp_replace(func.trim(motif()), literal(r"\s+"), literal(" "), literal("g")))


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
    """N3b : le motif est un filtre EXACT (le motif classé de la fiche, sans tenir compte de la casse ni des espaces autour), pas un
    morceau de texte : « Devis » ne prend plus « Devis urgent ». Les jokers sont du texte."""
    # Espaces repliés comme le fait le bilan de la boucle (``" ".join(valeur.split())``), pour que liste et statistiques s'accordent.
    replie = func.regexp_replace(func.trim(motif()), literal(r"\s+"), literal(" "), literal("g"))
    return func.lower(replie) == " ".join(terme.split()).lower()


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
