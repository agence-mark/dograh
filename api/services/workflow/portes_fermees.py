"""[.mark] Agent fiable (Evan, 17/11 : « regarder le problème à la source ») : une porte se FERME selon l'état de l'appel.

Avant, le modèle gardait à tout moment la sortie de fin, et un garde-fou rattrapait ses mauvais choix (refus de fin, une fois par appel :
l'appel 2624 a perdu une commande à l'approbation de sa relecture). Ici, c'est l'état qui ouvre les portes : une liaison réglée
``fermee_si_action_ouverte`` est retirée des outils de la requête tant qu'un connecteur déclare une action ouverte
(``Connecteur.action_ouverte``). Le connecteur dit ce qui est ouvert ; ce mécanisme ne sait rien d'un métier.

Appliqué juste avant chaque requête (``avant_la_requete``), sur une COPIE du contexte : l'historique n'est pas touché. Un agent sans porte
réglée n'a rien de posé. ⛔ Ne lève jamais : dans le doute, la requête part telle quelle.
"""

from __future__ import annotations

from typing import Any

from loguru import logger


def porte_fermable(arete: Any) -> bool:
    return getattr(getattr(arete, "data", None), "fermee_si_action_ouverte", None) is True


def agent_a_une_porte_fermable(agent: Any) -> bool:
    try:
        noeuds = getattr(getattr(agent, "workflow", None), "nodes", None) or {}
        return any(porte_fermable(a) for n in noeuds.values() for a in (getattr(n, "out_edges", None) or ()))
    except Exception:  # noqa: BLE001
        return False


def second_passage(context: Any) -> bool:
    """Clôture de la Partie 1, lot B5 (audit des textes § 2.5, « un merci ou un ok n'est pas une fin ») : la requête suit un résultat d'outil de ce
    tour, la personne n'a rien dit depuis. Lu sur les messages : le dernier qui compte est un résultat d'outil. ⛔ Ne lève jamais (faux)."""
    from api.services.pipecat.ordre_outil_puis_parole import APPELANT, PAROLE, RESULTAT, _nature

    try:
        for message in reversed(list(context.get_messages())):
            nature = _nature(message)
            if nature in (RESULTAT, APPELANT, PAROLE):
                return nature == RESULTAT
    except Exception:  # noqa: BLE001
        pass
    return False


def portes_fermees(moteur: Any, context: Any = None) -> set[str]:
    """Les noms des portes de l'étape en cours fermées en ce moment (vide : tout est ouvert) : tant qu'une action est ouverte, et au second
    passage d'un tour (B5 : la personne n'a rien dit depuis l'outil, elle n'a donc pas dit au revoir ; la fin ne se décide qu'à sa parole)."""
    try:
        noeud = getattr(getattr(moteur, "active_agent", None), "current_node", None)
        fermables = [a for a in (getattr(noeud, "out_edges", None) or ()) if porte_fermable(a)]
        if not fermables:
            return set()
        from api.services.workflow.action_non_aboutie import actions_ouvertes

        if not actions_ouvertes(moteur) and not (context is not None and second_passage(context)):
            return set()
        return {a.get_function_name() for a in fermables}
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[portes] état des portes illisible : {erreur!r}")
        return set()


def sans_les_noms(outils: Any, noms: set[str]) -> Any:
    """Les outils du contexte sans ``noms`` (un ``ToolsSchema`` ou une liste au format OpenAI)."""
    if not noms or outils is None:
        return outils
    if hasattr(outils, "standard_tools"):
        from pipecat.adapters.schemas.tools_schema import ToolsSchema

        gardes = [t for t in outils.standard_tools if getattr(t, "name", None) not in noms]
        return ToolsSchema(standard_tools=gardes, custom_tools=getattr(outils, "custom_tools", None))
    if isinstance(outils, list):
        return [t for t in outils if ((t.get("function") or {}).get("name") if isinstance(t, dict) else None) not in noms]
    return outils


def contexte_sans_les_portes_fermees(moteur: Any, context: Any) -> Any | None:
    """Une COPIE du contexte sans les portes fermées, pour CETTE requête ; ``None`` quand rien n'est fermé."""
    try:
        noms = portes_fermees(moteur, context)
        if not noms:
            return None
        from pipecat.processors.aggregators.llm_context import LLMContext

        logger.info(f"[portes] fermées (action ouverte ou second passage) : {', '.join(sorted(noms))}")
        return LLMContext(messages=list(context.get_messages()), tools=sans_les_noms(context.tools, noms), tool_choice=context.tool_choice)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[portes] portes non fermées : {erreur!r}")
        return None
