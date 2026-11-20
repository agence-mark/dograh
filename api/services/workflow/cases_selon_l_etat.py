"""[.mark] Chantier Partie 1, lot 2 (E26, le ``requires`` de Rasa) : une case sans objet à ce moment n'existe pas pour le modèle.

Un connecteur qui le déclare dit, d'après la fiche de l'appel, les cases de ses outils qui ont un objet maintenant
(``Connecteur.cases_visibles(fiche) -> frozenset`` de chemins : ``reponse``, ``reponse.sens``, ``ajouter[].composition``) et la forme qui change
avec l'état (``Connecteur.forme_selon_l_etat(fiche) -> {"requises": {chemin: [...]}, "descriptions": {chemin: texte}}``). Le connecteur dit ; ce
mécanisme ne sait aucun métier.

Appliqué juste avant chaque requête (``avant_la_requete``, après les portes fermées), sur une COPIE du contexte : l'historique n'est pas touché.
**La liste exacte des cases envoyées au modèle est gardée dans le tour** (D52) : ``fiche["cases_montrees"] = {nom de l'outil: [chemins]}``, lue par la
barrière du lot 3, jamais recalculée après coup.

⛔ Contrairement à ``portes_fermees``, une erreur n'est JAMAIS avalée (D52) : si ``cases_visibles`` lève, l'erreur est journalisée avec l'outil et
l'état, et ``CasesIllisibles`` est levée : la requête ne part pas avec toutes les cases (le tour échoue, visible au journal ; le repli est au lot 6).
"""

from __future__ import annotations

import copy
from typing import Any

from loguru import logger

CLE_DES_CASES_MONTREES = "cases_montrees"


class CasesIllisibles(RuntimeError):
    """Les cases d'un outil n'ont pas pu être calculées : la requête ne part pas (D52)."""


def chemins_du_schema(proprietes: dict[str, Any], prefixe: str = "") -> list[str]:
    """Tous les chemins de cases d'un schéma JSON : ``a``, ``a.b`` (objet), ``a[].b`` (élément d'une liste d'objets)."""
    sortie: list[str] = []
    for nom, schema in (proprietes or {}).items():
        chemin = f"{prefixe}{nom}"
        sortie.append(chemin)
        if isinstance(schema.get("properties"), dict):
            sortie += chemins_du_schema(schema["properties"], chemin + ".")
        elements = schema.get("items")
        if isinstance(elements, dict) and isinstance(elements.get("properties"), dict):
            sortie += chemins_du_schema(elements["properties"], chemin + "[].")
    return sortie


def _filtrer(proprietes: dict[str, Any], visibles: frozenset[str], forme: dict[str, Any], prefixe: str = "") -> dict[str, Any]:
    gardees: dict[str, Any] = {}
    descriptions = forme.get("descriptions") or {}
    requises = forme.get("requises") or {}
    for nom, schema in proprietes.items():
        chemin = f"{prefixe}{nom}"
        if chemin not in visibles:
            continue
        s = copy.deepcopy(schema)
        if chemin in descriptions:
            s["description"] = descriptions[chemin]
        if isinstance(s.get("properties"), dict):
            s["properties"] = _filtrer(s["properties"], visibles, forme, chemin + ".")
            if chemin in requises:
                s["required"] = list(requises[chemin])
            elif "required" in s:
                s["required"] = [r for r in s["required"] if r in s["properties"]]
        elements = s.get("items")
        if isinstance(elements, dict) and isinstance(elements.get("properties"), dict):
            elements["properties"] = _filtrer(elements["properties"], visibles, forme, chemin + "[].")
            if "required" in elements:
                elements["required"] = [r for r in elements["required"] if r in elements["properties"]]
        gardees[nom] = s
    return gardees


def schema_selon_l_etat(proprietes: dict[str, Any], requis: list[str], visibles: frozenset[str], forme: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Le schéma (propriétés, requis du premier niveau) que voit le modèle maintenant : les cases visibles, avec la forme de l'état."""
    gardees = _filtrer(proprietes, visibles, forme)
    requises = (forme.get("requises") or {}).get("") or [r for r in requis if r in gardees]
    return gardees, [r for r in requises if r in gardees]


def cases_montrees(fiche_de_l_appel: Any) -> list[str] | None:
    """Les cases de la ``fiche`` montrées au modèle dans CE tour (D52), ou ``None`` si elles ne sont pas connues (la barrière refuse alors la fiche)."""
    from api.services.integrations.connectors.outil import nom_vu

    montrees = (fiche_de_l_appel or {}).get(CLE_DES_CASES_MONTREES) or {} if isinstance(fiche_de_l_appel, dict) else {}
    for nom in ("fiche", nom_vu(fiche_de_l_appel, "fiche")):
        if isinstance(montrees.get(nom), list):
            return montrees[nom]
    return None


def _fiche(moteur: Any) -> dict:
    fiche = getattr(moteur, "_gathered_context", None)
    return fiche if isinstance(fiche, dict) else {}


def _connecteur_de(moteur: Any, nom: str):
    from api.services.integrations.connectors.catalogue import connecteur
    from api.services.workflow.etat_des_connecteurs import ATTRIBUT, _normaliser

    table = getattr(moteur, ATTRIBUT, None)
    nom_du_connecteur = table.get(_normaliser(nom)) if isinstance(table, dict) else None
    return connecteur(nom_du_connecteur) if nom_du_connecteur else None


def _action_a_cases(moteur: Any, c: Any, nom: str) -> bool:
    """L'action de cette fonction suit-elle les cases de l'état (``Connecteur.actions_a_cases``, toutes quand il n'en dit rien) ? Une
    fonction dont l'action n'est pas connue garde ses cases selon l'état, comme avant (jamais toutes les cases par défaut, D52)."""
    if c.actions_a_cases is None:
        return True
    from api.services.workflow.etat_des_connecteurs import ATTRIBUT_ACTIONS, _normaliser

    table = getattr(moteur, ATTRIBUT_ACTIONS, None)
    action = table.get(_normaliser(nom)) if isinstance(table, dict) else None
    return action is None or action in c.actions_a_cases


def outils_selon_l_etat(moteur: Any, outils: Any) -> tuple[Any, dict[str, list[str]]] | None:
    """Les outils de la requête, chacun réduit à ses cases visibles, et les cases montrées par outil ; ``None`` quand aucun outil n'a un
    connecteur qui déclare ses cases. Lève ``CasesIllisibles`` (jamais de repli silencieux, D52)."""
    standard = getattr(outils, "standard_tools", None)
    if not standard:
        return None
    fiche = _fiche(moteur)
    touches = False
    gardes, montrees = [], {}
    from pipecat.adapters.schemas.function_schema import FunctionSchema

    for outil in standard:
        nom = getattr(outil, "name", None)
        c = _connecteur_de(moteur, nom) if nom else None
        if c is None or c.cases_visibles is None or not _action_a_cases(moteur, c, nom):
            gardes.append(outil)
            continue
        try:
            visibles = frozenset(c.cases_visibles(fiche))
            forme = c.forme_selon_l_etat(fiche) if c.forme_selon_l_etat is not None else {}
        except Exception as erreur:
            etat = sorted(k for k in fiche if not str(k).startswith("_"))[:20]
            logger.error(f"[cases] cases de l'outil {nom!r} (connecteur {c.nom}) illisibles : {erreur!r} ; clés de la fiche : {etat}")
            raise CasesIllisibles(f"cases de l'outil {nom!r} illisibles") from erreur
        proprietes, requis = schema_selon_l_etat(dict(outil.properties or {}), list(outil.required or []), visibles, forme)
        gardes.append(FunctionSchema(name=nom, description=outil.description, properties=proprietes, required=requis))
        montrees[nom] = chemins_du_schema(proprietes)
        touches = True
    if not touches:
        return None
    from pipecat.adapters.schemas.tools_schema import ToolsSchema

    return ToolsSchema(standard_tools=gardes, custom_tools=getattr(outils, "custom_tools", None)), montrees


def garder_les_cases_montrees(moteur: Any, montrees: dict[str, list[str]]) -> None:
    """Range dans la fiche de l'appel la liste EXACTE des cases envoyées au modèle pour ce tour (une copie : rien ne la change ensuite)."""
    fiche = getattr(moteur, "_gathered_context", None)
    if isinstance(fiche, dict):
        fiche[CLE_DES_CASES_MONTREES] = {nom: list(chemins) for nom, chemins in montrees.items()}


CLE_DU_TOUR = "tour_de_la_personne"
CLE_DES_PAROLES = "paroles_de_la_personne"
CLE_DIT_DANS_L_APPEL = "dit_par_le_code"
CLE_DERNIERE_PAROLE = "_derniere_parole_comptee"


def _texte_du_message(m: Any) -> str:
    contenu = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
    if isinstance(contenu, list):
        return " ".join(str(x.get("text") or "") for x in contenu if isinstance(x, dict))
    return str(contenu or "")


def noter_le_tour(moteur: Any, context: Any) -> None:
    """Le tour de la personne (un de plus à chaque nouvelle parole) et ce qui a été dit dans l'appel, rangés dans la fiche : la barrière « elle l'a
    dit » (D57) les lit, et une question née dans ce tour se reconnaît (B8 point 1). Générique : des messages, aucun métier."""
    fiche = getattr(moteur, "_gathered_context", None)
    if not isinstance(fiche, dict):
        return
    messages = list(context.get_messages()) if hasattr(context, "get_messages") else []
    paroles = [t for m in messages if (m.get("role") if isinstance(m, dict) else getattr(m, "role", None)) == "user" and (t := _texte_du_message(m).strip())]
    dits = [t for m in messages if (m.get("role") if isinstance(m, dict) else getattr(m, "role", None)) == "assistant" and (t := _texte_du_message(m).strip())]
    fiche[CLE_DES_PAROLES] = paroles[-40:]
    fiche[CLE_DIT_DANS_L_APPEL] = dits[-40:]
    if paroles and fiche.get(CLE_DERNIERE_PAROLE) != len(paroles):
        fiche[CLE_DERNIERE_PAROLE] = len(paroles)
        fiche[CLE_DU_TOUR] = int(fiche.get(CLE_DU_TOUR) or 0) + 1


def contexte_avec_les_cases_de_l_etat(moteur: Any, context: Any) -> Any | None:
    """Une COPIE du contexte dont chaque outil de connecteur ne garde que ses cases visibles, pour CETTE requête ; ``None`` quand aucun outil n'en
    déclare. Les cases montrées sont gardées dans le tour. Lève ``CasesIllisibles`` (D52)."""
    noter_le_tour(moteur, context)
    resultat = outils_selon_l_etat(moteur, getattr(context, "tools", None))
    if resultat is None:
        garder_les_cases_montrees(moteur, {})  # P4 : aucun outil à cases cette fois (retour à l'accueil) : les cases du tour d'avant ne valent plus, jamais jugé comme la commande
        return None
    outils, montrees = resultat
    garder_les_cases_montrees(moteur, montrees)
    from pipecat.processors.aggregators.llm_context import LLMContext

    return LLMContext(messages=list(context.get_messages()), tools=outils, tool_choice=context.tool_choice)
