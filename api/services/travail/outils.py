"""[.mark] Lot 4 d'orchestrateur-trois-cerveaux (D8, D13) : les outils du cerveau de fond.

Le fond reçoit les outils CHOISIS à l'écran (``travail_outils``, tous ceux du catalogue de
l'organisation : connecteurs, outils HTTP, MCP, actions internes) **moins** tout ce qui agit sur
l'appel lui-même : transfert vers un numéro, passation à un agent, fin d'appel, et les actions
internes qui peuvent transférer l'appel (l'équipe). Un travail de fond ne raccroche jamais, ne
transfère jamais.

Ses outils s'enregistrent sur le MODÈLE DU FOND, par un gestionnaire dédié : ``CustomToolManager``
est réutilisé tel quel, mais devant un faux agent (le modèle du fond, aucune garde « l'agent a-t-il
la main ») et un moteur muet (les phrases d'outil ne sont jamais dites : leur texte est gardé et
rendu à la trace, pas à la voix).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from loguru import logger

from api.enums import ToolCategory
from api.services.pipecat.speech_playback import PlaybackOutcome

# Les catégories d'outils qui agissent sur l'appel : jamais données au fond.
CATEGORIES_INTERDITES = frozenset(
    {
        ToolCategory.END_CALL.value,
        ToolCategory.TRANSFER_CALL.value,
        ToolCategory.TRANSFER_AGENT.value,
    }
)


def outil_permis_au_fond(outil: Any) -> bool:
    """L'outil peut-il être donné au cerveau de fond ? Faux pour un transfert, une passation, la
    fin d'appel, et une action interne qui peut transférer l'appel. ⛔ Ne lève jamais."""
    try:
        if str(getattr(outil, "category", "")) in CATEGORIES_INTERDITES:
            return False
        if getattr(outil, "category", None) == ToolCategory.INTEGRATION.value:
            from api.services.integrations.connectors import outil as integration

            interne = integration.connecteur_interne(outil)
            if interne is not None and interne.peut_transferer:
                return False
        return True
    except Exception as erreur:  # noqa: BLE001 -- dans le doute, l'outil n'est pas donné
        logger.warning(f"[travail] outil écarté du fond (illisible) : {erreur!r}")
        return False


def uuids_permis(outils: list[Any]) -> list[str]:
    """Les UUID des outils lus que le fond peut recevoir, dans l'ordre de lecture."""
    return [o.tool_uuid for o in outils if outil_permis_au_fond(o)]


class MoteurDeFond:
    """Le moteur de l'appel vu par les outils du fond : le même, SAUF qu'il ne parle jamais.

    Tout se lit sur le vrai moteur (fiche, contexte de l'appel, organisation). ``queue_speech`` et
    ``queue_text_message`` (la phrase de patience, le message avant un appel HTTP, la phrase de
    repli) ne disent rien : leur texte est gardé dans ``non_dites`` pour la trace, et un
    ``SpeechPlayback`` déjà fini est rendu pour que l'appelant de la phrase n'attende rien."""

    def __init__(self, moteur: Any):
        object.__setattr__(self, "_moteur", moteur)
        object.__setattr__(self, "non_dites", [])

    def __getattr__(self, nom: str) -> Any:
        return getattr(object.__getattribute__(self, "_moteur"), nom)

    def __setattr__(self, nom: str, valeur: Any) -> None:
        setattr(object.__getattribute__(self, "_moteur"), nom, valeur)

    async def queue_speech(self, text: str | None = None, **_options: Any):
        if isinstance(text, str) and text.strip():
            self.non_dites.append(text.strip())
        parole = self._moteur.speech_playback.create(timeout=1.0)
        parole.finish(PlaybackOutcome.SKIPPED)
        return parole

    async def queue_text_message(self, text: str, **_options: Any) -> bool:
        await self.queue_speech(text)
        return False


class AgentDeFond:
    """L'agent devant lequel les outils du fond s'enregistrent : le modèle du fond, et rien qui
    puisse les refuser (``bind_tool`` rend le gestionnaire tel quel). Les sessions MCP sont celles
    de l'agent qui confie (le même dictionnaire, lu au moment de l'enregistrement)."""

    def __init__(self, *, llm: Any, agent: Any):
        self.llm = llm
        self.mcp_sessions = getattr(agent, "mcp_sessions", {})
        self.workflow_id = getattr(agent, "workflow_id", None)
        self.reglages = getattr(agent, "reglages", None)
        self.visit_id = getattr(agent, "visit_id", "")
        self.current_node = None
        self.runtime_configuration = SimpleNamespace()

    def bind_tool(self, _moteur: Any, gestionnaire: Any, **_options: Any):
        # Lot 3 de cloture-code (b10e829f) : ``CustomToolManager`` passe désormais
        # ``is_node_transition`` et ``timeout_secs``. Sans ``**_options``, l'enregistrement des
        # outils du fond levait et le fond perdait ses outils en silence (R1).
        return gestionnaire


async def preparer_les_outils(
    moteur: Any,
    agent: Any,
    llm: Any,
    uuids: tuple[str, ...] | list[str],
    muet: "MoteurDeFond | None" = None,
) -> tuple[list[Any], list[str]]:
    """Enregistre sur ``llm`` (le modèle du fond) les outils réglés que le fond peut recevoir, et
    rend (leurs schémas, leurs noms). Aucun outil réglé : ``([], [])``, sans lire la base. Ne
    lève jamais : un échec = un fond sans outil, journalisé. ``muet`` : le moteur muet que les
    outils tiendront (l'appelant garde la main dessus pour lire ce qu'ils auraient dit)."""
    if not uuids:
        return [], []
    try:
        from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager

        muet = muet if muet is not None else MoteurDeFond(moteur)
        gestionnaire = CustomToolManager(muet, AgentDeFond(llm=llm, agent=agent))
        organisation = await gestionnaire.get_organization_id()
        if not organisation:
            logger.warning("[travail] outils du fond : organisation inconnue, aucun outil")
            return [], []
        lus = await gestionnaire._lire_outils(list(uuids), organisation)
        permis = uuids_permis(lus)
        ecartes = len(lus) - len(permis)
        if ecartes:
            logger.info(
                f"[travail] {ecartes} outil(s) écarté(s) du fond (transfert, fin d'appel)"
            )
        if not permis:
            return [], []
        await gestionnaire.register_handlers(permis)
        schemas = await gestionnaire.get_tool_schemas(permis)
        return list(schemas), [s.name for s in schemas]
    except Exception as erreur:  # noqa: BLE001 -- un fond sans outil, jamais un appel cassé
        logger.error(f"[travail] outils du fond non préparés : {type(erreur).__name__}")
        return [], []
