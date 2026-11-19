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


def _fiche(moteur: Any) -> dict:
    fiche = getattr(moteur, "_gathered_context", None)
    return fiche if isinstance(fiche, dict) else {}


def _connecteur_de(moteur: Any, nom: str):
    from api.services.integrations.connectors.catalogue import connecteur
    from api.services.workflow.etat_des_connecteurs import ATTRIBUT, _normaliser

    table = getattr(moteur, ATTRIBUT, None)
    nom_du_connecteur = table.get(_normaliser(nom)) if isinstance(table, dict) else None
    return connecteur(nom_du_connecteur) if nom_du_connecteur else None


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
        if c is None or c.cases_visibles is None:
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


def contexte_avec_les_cases_de_l_etat(moteur: Any, context: Any) -> Any | None:
    """Une COPIE du contexte dont chaque outil de connecteur ne garde que ses cases visibles, pour CETTE requête ; ``None`` quand aucun outil n'en
    déclare. Les cases montrées sont gardées dans le tour. Lève ``CasesIllisibles`` (D52)."""
    resultat = outils_selon_l_etat(moteur, getattr(context, "tools", None))
    if resultat is None:
        return None
    outils, montrees = resultat
    garder_les_cases_montrees(moteur, montrees)
    from pipecat.processors.aggregators.llm_context import LLMContext

    return LLMContext(messages=list(context.get_messages()), tools=outils, tool_choice=context.tool_choice)
