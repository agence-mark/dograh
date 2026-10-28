"""[.mark] passages-fiables (lot E) : laisser la parole.

Quand la personne demande un moment (chercher, vérifier), l'agent appelle l'outil ``laisser_la_parole`` (offert seulement
si la case de l'agent est allumée). Le moniteur de silence (``CallMonitorProcessor``) passe en ATTENTE : le délai est celui
de la phrase ``attente_accordee`` du catalogue (défaut 45 s), puis cette phrase douce (modifiable à l'écran) remplace la
relance normale, jamais de raccrochage pendant l'attente ; la personne qui reparle la lève, puis le comportement normal
reprend.

L'attente s'accorde avec une phrase dite dans la MÊME réponse (« je vous attends ») : le résultat ne fait alors pas
reparler l'agent (R15, ``parole_avant_outil``). Outil appelé seul, sans phrase (banc local du 29/10, runs 22, 30 et 33 :
le modèle l'a appelé au moment de passer d'étape, sur « oui, je veux bien » ou une adresse donnée) : rien n'est accordé
et le modèle est relancé, il répond à la personne. Jamais de résultat d'outil en fin d'historique sans réponse derrière
(la parole suivante de la personne derrière un rôle ``tool`` est refusée par certains gabarits : 400 chez Scaleway).
Sans suivi de la parole (service sans les points d'accroche), l'attente est accordée et le modèle relancé, comme R15.

Branchements existants du moteur : ``call_monitor.delai_de_relance`` et ``handle_user_idle`` (``pipecat_engine_callbacks``).
Le clavier n'a pas de silence (aucun agrégateur de parole n'est lié au moniteur) : l'outil y est offert et tracé, sans
relance (écart écrit dans ``test_parite_clavier_telephone``).

⛔ Zéro vocabulaire métier (la description de l'outil est une consigne au modèle, jamais dite). ⛔ Ne lève jamais.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.frames.frames import FunctionCallResultProperties

CLE_LAISSER_LA_PAROLE = "laisser_la_parole"
NOM_OUTIL = "laisser_la_parole"
# La trace de l'appel, lue par l'analyse : ce qui s'est passé de l'attente.
CLE_TRACE = "attentes_accordees"

DESCRIPTION_OUTIL = (
    "Appelle cet outil seulement quand la personne te demande explicitement du temps pour chercher ou vérifier quelque "
    "chose avant de te répondre. Dans la même réponse, dis d'abord une phrase très courte pour lui dire que tu "
    "l'attends : sans cette phrase, rien n'est accordé. Ensuite tu te tais jusqu'à ce qu'elle reprenne la parole : elle "
    "ne sera pas relancée pendant un bon moment. Cet outil ne répond pas à la personne et ne fait passer à aucune autre "
    "étape."
)
RESULTAT = "La personne prend son temps. Ne dis rien de plus : attends qu'elle reprenne la parole."
# Sans suivi de la parole : l'attente est accordée et le modèle relancé, il dit qu'il attend.
RESULTAT_A_DIRE = "La personne prend son temps. Dis-lui seulement, en une phrase très courte, que tu l'attends."
# Outil appelé seul, sans phrase : rien n'est accordé, le modèle relancé répond à la personne.
RESULTAT_REFUSE = "Rien n'est accordé. Réponds à ce que la personne vient de dire."


def case_allumee(agent: Any, moteur: Any) -> bool:
    """La case « Laisser l'appelant prendre son temps » de l'agent : posée à ``True`` seulement."""
    try:
        reglages = getattr(agent, "reglages", None) or getattr(moteur, "reglages_appel", None) or {}
        return reglages.get(CLE_LAISSER_LA_PAROLE) is True
    except Exception:  # noqa: BLE001
        return False


def schema_de_l_outil() -> FunctionSchema:
    return FunctionSchema(name=NOM_OUTIL, description=DESCRIPTION_OUTIL, properties={}, required=[])


def tracer(moteur: Any, evenement: str, **detail: Any) -> None:
    """Une ligne dans la fiche de l'appel (``attentes_accordees``). ⛔ Ne lève jamais."""
    try:
        contexte = getattr(moteur, "_gathered_context", None)
        if isinstance(contexte, dict):
            contexte.setdefault(CLE_TRACE, []).append({"evenement": evenement, **detail})
    except Exception:  # noqa: BLE001
        pass


def brancher_laisser_la_parole(moteur: Any, agent: Any, noeud: Any) -> FunctionSchema | None:
    """Enregistre l'outil sur le cerveau de ``agent`` et rend son schéma ; ``None`` (rien d'offert) : case éteinte, étape de
    fin, ou pas de moniteur. ⛔ Ne lève jamais."""
    try:
        if getattr(noeud, "is_end", False) or not case_allumee(agent, moteur):
            return None
        if getattr(moteur, "call_monitor", None) is None or getattr(agent, "llm", None) is None:
            return None

        from api.services.pipecat.parole_avant_outil import suivre_la_parole

        suivi = suivre_la_parole(agent.llm)

        async def laisser(params) -> None:
            noeud_en_cours = getattr(agent, "current_node", None)
            # R15 : la même réponse a-t-elle parlé ? (inconnu sans suivi)
            a_parle = None if suivi is None else suivi.a_parle_avant(getattr(params, "tool_call_id", None))
            if a_parle is False:
                tracer(moteur, "refusee_sans_phrase", etape=getattr(noeud_en_cours, "name", None))
                await params.result_callback(RESULTAT_REFUSE)
                return
            try:
                moniteur = moteur.call_monitor
                moniteur.sur_attente_levee = lambda: tracer(moteur, "levee_la_personne_reparle")
                moniteur.accorder_l_attente()
                tracer(moteur, "accordee", etape=getattr(noeud_en_cours, "name", None))
            except Exception as erreur:  # noqa: BLE001
                logger.warning(f"[parole] attente non accordée : {erreur!r}")
            if a_parle:
                await params.result_callback(RESULTAT, properties=FunctionCallResultProperties(run_llm=False))
            else:
                await params.result_callback(RESULTAT_A_DIRE)

        agent.llm.register_function(NOM_OUTIL, agent.bind_tool(moteur, laisser))
        return schema_de_l_outil()
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[parole] outil non branché : {erreur!r}")
        return None
