"""[.mark] passages-fiables (lot F) : le signalement par l'agent.

L'agent qui se sent perdu (demande ambiguë, règle qu'il ne connaît pas, outil qui échoue) appelle l'outil
``signaler_un_probleme`` avec un motif court et une catégorie. **Rien n'est dit à l'appelant** sur le signalement. Règle
R15 (``parole_avant_outil``) : si la même réponse a déjà parlé, le résultat ne fait pas reparler l'agent
(``run_llm=False``) ; appelé seul, le modèle est relancé et continue la conversation (sinon l'historique finirait par le
résultat de l'outil, sans réponse à la personne : 400 « user after tool » chez Scaleway, banc local du 29/10). Deux signalements au plus par appel. Le signalement
est écrit dans ``gathered_context["signalements"]`` (source ``agent``) ; la page « À trier » de Dograh le lit (lot G).

Offert seulement si la case de l'agent est allumée (éteinte par défaut), jamais sur une étape de fin. L'outil est branché
dans le moteur (``set_node``) : le téléphone et le clavier partagent le même moteur.

⛔ Zéro vocabulaire métier (la description est une consigne au modèle, jamais dite). ⛔ Ne lève jamais.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema

from api.services.tri import donnees

CLE_SIGNALER_UN_PROBLEME = "signaler_un_probleme"
NOM_OUTIL = "signaler_un_probleme"

DESCRIPTION_OUTIL = (
    "Appelle cet outil, sans rien dire à la personne, quand tu es perdu : sa demande est ambiguë et tu ne peux pas la "
    "trancher, tu ne connais pas la règle à appliquer, ou un outil échoue. Donne un motif court (une phrase) et une "
    "catégorie. Ensuite tu continues la conversation comme si de rien n'était : ce signalement n'est lu qu'après l'appel. "
    "Deux fois au plus par appel."
)
RESULTAT = "Noté. Ne dis rien à ce sujet et continue."


def case_allumee(agent: Any, moteur: Any) -> bool:
    """La case « L'agent peut signaler un problème » : posée à ``True`` seulement. Éteinte par défaut."""
    try:
        reglages = getattr(agent, "reglages", None) or getattr(moteur, "reglages_appel", None) or {}
        return reglages.get(CLE_SIGNALER_UN_PROBLEME) is True
    except Exception:  # noqa: BLE001
        return False


def schema_de_l_outil() -> FunctionSchema:
    return FunctionSchema(
        name=NOM_OUTIL,
        description=DESCRIPTION_OUTIL,
        properties={
            "motif": {"type": "string", "description": "Une phrase courte : ce qui bloque."},
            "categorie": {"type": "string", "enum": list(donnees.CATEGORIES)},
        },
        required=["motif", "categorie"],
    )


def brancher_signaler_un_probleme(moteur: Any, agent: Any, noeud: Any) -> FunctionSchema | None:
    """Enregistre l'outil sur le cerveau de ``agent`` et rend son schéma ; ``None`` (rien d'offert) : case éteinte ou
    étape de fin. ⛔ Ne lève jamais."""
    try:
        if getattr(noeud, "is_end", False) or not case_allumee(agent, moteur):
            return None
        if getattr(agent, "llm", None) is None:
            return None

        from api.services.travail.agent import _proprietes_du_resultat

        proprietes = _proprietes_du_resultat(agent.llm)

        async def signaler(params) -> None:
            try:
                arguments = getattr(params, "arguments", None) or {}
                noeud_en_cours = getattr(agent, "current_node", None)
                donnees.ajouter_un_signalement_de_l_agent(
                    getattr(moteur, "_gathered_context", None),
                    motif=str(arguments.get("motif") or ""),
                    categorie=str(arguments.get("categorie") or ""),
                    etape=getattr(noeud_en_cours, "name", None),
                )
            except Exception as erreur:  # noqa: BLE001
                logger.warning(f"[signalement] non écrit : {erreur!r}")
            await params.result_callback(RESULTAT, properties=proprietes(params))

        agent.llm.register_function(NOM_OUTIL, agent.bind_tool(moteur, signaler))
        return schema_de_l_outil()
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[signalement] outil non branché : {erreur!r}")
        return None
