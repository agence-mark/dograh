"""[.mark] passages-fiables (lot E) : laisser la parole.

Quand la personne demande un moment (chercher, vérifier), l'agent appelle l'outil ``laisser_la_parole`` (offert seulement
si la case de l'agent est allumée). Le moniteur de silence (``CallMonitorProcessor``) passe en ATTENTE : le délai est celui
de la phrase ``attente_accordee`` du catalogue (défaut 45 s), puis cette phrase douce (modifiable à l'écran) remplace la
relance normale, jamais de raccrochage pendant l'attente ; la personne qui reparle la lève, puis le comportement normal
reprend. L'outil rend un résultat qui ne fait pas reparler l'agent.

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
    "Appelle cet outil quand la personne te demande du temps pour chercher ou vérifier quelque chose avant de te "
    "répondre. Tu peux dire une phrase très courte dans la même réponse pour confirmer que tu attends. Ensuite tu te tais "
    "jusqu'à ce qu'elle reprenne la parole : elle ne sera pas relancée pendant un bon moment."
)
RESULTAT = "La personne prend son temps. Ne dis rien de plus : attends qu'elle reprenne la parole."


def case_allumee(agent: Any, moteur: Any) -> bool:
    """La case « Laisser la personne prendre son temps » de l'agent : posée à ``True`` seulement."""
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

        async def laisser(params) -> None:
            try:
                moniteur = moteur.call_monitor
                moniteur.sur_attente_levee = lambda: tracer(moteur, "levee_la_personne_reparle")
                moniteur.accorder_l_attente()
                noeud_en_cours = getattr(agent, "current_node", None)
                tracer(moteur, "accordee", etape=getattr(noeud_en_cours, "name", None))
            except Exception as erreur:  # noqa: BLE001
                logger.warning(f"[parole] attente non accordée : {erreur!r}")
            await params.result_callback(RESULTAT, properties=FunctionCallResultProperties(run_llm=False))

        agent.llm.register_function(NOM_OUTIL, agent.bind_tool(moteur, laisser))
        return schema_de_l_outil()
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[parole] outil non branché : {erreur!r}")
        return None
