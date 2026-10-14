"""[.mark] Chantier correctifs-modules, lot 4 bis : le schéma du parcours.

Plan : ``Labo-agent-vocal/plans/correctifs-modules/2026-09-28-plan-correctifs-modules.md``.

Réglage d'agent ``generer_schema_parcours`` (« Generate the flow map »), éteint par
défaut. Allumé, chaque enregistrement de l'agent lit son graphe et écrit :

- à la fin du prompt global, un bloc ``<parcours_genere>`` : chaque étape, et sous elle
  ses portes (le nom de la fonction que le modèle appelle → l'étape d'arrivée) ;
- à la fin du prompt de chaque étape, ``<position_generee>Tu es ici : <étape></position_generee>``.

Pourquoi dans le code : écrit à la main (le ``schema.js`` des agents de la
refonte), le schéma finit faux dès qu'une porte change. Généré à l'enregistrement,
il ne peut pas diverger du graphe.

⛔ Ce qui n'y entre jamais : autre chose que les noms d'étapes et de portes
(aucun rôle, aucun mot de métier). Exception, case ``parcours_lisible`` (lot 4 ter de
repliques-coupees) : chaque étape porte son rôle, recopié de la ligne sous « # Ta mission
ici » de son prompt (notre texte, pas celui du code), et la carte ne liste plus les portes. ⛔ Les blocs sont délimités et remplacés à
chaque enregistrement : jamais empilés, jamais au contact du texte écrit à la main
(une ligne vide les sépare). Éteint : les blocs laissés sont retirés, et un agent
qui n'en a jamais eu s'enregistre exactement comme avant.
"""

from __future__ import annotations

import copy
import re

from api.services.workflow.workflow_graph import transition_tool_name

CLE_REGLAGE = "generer_schema_parcours"
# Chantier repliques-coupees, lot 4 ter (D12, D13) : la carte lisible. Une ligne par étape,
# son nom et son rôle ; ni portes ni « → » (les sorties sont dans le bloc de fin d'étape, et
# « → » ne sert qu'à changer d'étape) ; plus de « Tu es ici » à part (le bloc de fin d'étape
# le dit). Le rôle est la ligne sous « # Ta mission ici » du prompt de l'étape, écrite par
# nous : le code n'y met aucun mot de métier.
CLE_LISIBLE = "parcours_lisible"
_MISSION = re.compile(r"^#\s*Ta mission ici[ \t]*\n+[ \t]*(\S.*)$", re.MULTILINE)

# ⛔ Des repères propres au code (revue du 28/09) : ``<parcours>`` est ce qu'écrit
# à la main le ``schema.js`` des agents de la refonte (n° 34). Des repères
# identiques effaçaient ce texte à tout enregistrement, case éteinte.
DEBUT_PARCOURS, FIN_PARCOURS = "<parcours_genere>", "</parcours_genere>"
DEBUT_POSITION, FIN_POSITION = "<position_generee>", "</position_generee>"
# Les étapes d'un appel ; le nœud global, les déclencheurs et les webhooks n'en sont pas.
TYPES_ETAPE = ("startCall", "agentNode", "endCall")
TYPE_GLOBAL = "globalNode"

_BLOCS = re.compile(
    rf"\s*(?:{re.escape(DEBUT_PARCOURS)}.*?{re.escape(FIN_PARCOURS)}"
    rf"|{re.escape(DEBUT_POSITION)}.*?{re.escape(FIN_POSITION)})",
    re.DOTALL,
)


def retirer(prompt: str | None) -> str | None:
    """Le prompt sans les blocs générés. Sans bloc, le prompt tel quel."""
    if not prompt or (DEBUT_PARCOURS not in prompt and DEBUT_POSITION not in prompt):
        return prompt
    return _BLOCS.sub("", prompt).rstrip()


def _ajouter(prompt: str | None, bloc: str) -> str:
    texte = (prompt or "").rstrip()
    return f"{texte}\n\n{bloc}" if texte else bloc


def _nom(noeud: dict) -> str:
    return str((noeud.get("data") or {}).get("name") or noeud.get("id"))


def _ordre_des_etapes(etapes: list[dict], edges: list[dict]) -> list[dict]:
    """Dans l'ordre d'un appel : en largeur depuis l'étape de départ, puis les
    étapes qu'aucune porte n'atteint, dans l'ordre du graphe."""
    par_id = {n["id"]: n for n in etapes}
    depart = [n["id"] for n in etapes if n.get("type") == "startCall"]
    vues: list[str] = list(depart)
    for courante in vues:
        for edge in edges:
            if edge.get("source") == courante and edge.get("target") in par_id and edge["target"] not in vues:
                vues.append(edge["target"])
    vues += [n["id"] for n in etapes if n["id"] not in vues]
    return [par_id[i] for i in vues]


def parcours(definition: dict) -> str:
    """Le bloc ``<parcours_genere>`` du graphe."""
    noeuds = definition.get("nodes") or []
    edges = definition.get("edges") or []
    etapes = [n for n in noeuds if n.get("type") in TYPES_ETAPE]
    par_id = {n["id"]: n for n in etapes}
    lignes = [DEBUT_PARCOURS]
    for etape in _ordre_des_etapes(etapes, edges):
        lignes.append(_nom(etape))
        for edge in edges:
            if edge.get("source") != etape["id"] or edge.get("target") not in par_id:
                continue
            porte = transition_tool_name(str((edge.get("data") or {}).get("label") or ""))
            lignes.append(f"  {porte} → {_nom(par_id[edge['target']])}")
    lignes.append(FIN_PARCOURS)
    return "\n".join(lignes)


def _role(noeud: dict) -> str:
    """La ligne sous « # Ta mission ici » du prompt de l'étape, sans point final."""
    trouve = _MISSION.search(retirer((noeud.get("data") or {}).get("prompt")) or "")
    return trouve.group(1).strip().rstrip(".") if trouve else ""


def parcours_lisible(definition: dict) -> str:
    """Lot 4 ter de repliques-coupees : la carte des étapes et de leur rôle."""
    noeuds = definition.get("nodes") or []
    etapes = [n for n in noeuds if n.get("type") in TYPES_ETAPE]
    lignes = [DEBUT_PARCOURS, "# Les étapes de l'appel"]
    for etape in _ordre_des_etapes(etapes, definition.get("edges") or []):
        role = _role(etape)
        lignes.append(f"{_nom(etape)} : {role}" if role else _nom(etape))
    lignes.append(FIN_PARCOURS)
    return "\n".join(lignes)


def appliquer(
    definition: dict | None, allume: bool, lisible: bool = False
) -> dict | None:
    """La définition avec les blocs à jour (allumé) ou retirés (éteint).
    ``lisible`` (lot 4 ter de repliques-coupees) : la carte des rôles, sans « Tu es ici ».

    Toujours une copie ; une définition sans bloc, éteinte, revient identique."""
    if not definition:
        return definition
    resultat = copy.deepcopy(definition)
    bloc = (parcours_lisible(resultat) if lisible else parcours(resultat)) if allume else None
    for noeud in resultat.get("nodes") or []:
        data = noeud.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("prompt"), (str, type(None))):
            continue
        type_noeud = noeud.get("type")
        if type_noeud != TYPE_GLOBAL and type_noeud not in TYPES_ETAPE:
            continue
        propre = retirer(data.get("prompt"))
        if allume and type_noeud == TYPE_GLOBAL:
            propre = _ajouter(propre, bloc)
        elif allume and not lisible:
            propre = _ajouter(propre, f"{DEBUT_POSITION}Tu es ici : {_nom(noeud)}{FIN_POSITION}")
        if propre != data.get("prompt"):
            data["prompt"] = propre
    return resultat


def reglage_allume(configurations: dict | None) -> bool | None:
    """La valeur de la case dans ces configurations, ``None`` si elle n'y est pas."""
    if not configurations or CLE_REGLAGE not in configurations:
        return None
    return bool(configurations[CLE_REGLAGE])


async def a_l_enregistrement(
    workflow_id: int,
    organization_id: int,
    definition: dict | None,
    configurations: dict | None,
) -> dict | None:
    """La définition à enregistrer, ou ``None`` s'il n'y a rien à écrire.

    - Le graphe est enregistré : ses blocs suivent la case (celle de cet
      enregistrement, sinon celle déjà enregistrée).
    - La case seule est enregistrée : le graphe enregistré est mis à jour, et
      renvoyé seulement s'il change.
    """
    from api.db import db_client

    allume = reglage_allume(configurations)
    lisible = _lisible(configurations)
    if allume is None and definition is None:
        return None
    existante = None
    # Revue du 14/10 (retouche 2, Evan) : la base n'est lue que si une valeur manque
    # vraiment ; la case lisible ne compte que schéma allumé (éteint, les blocs sont retirés).
    if allume is None or definition is None or (allume and lisible is None):
        workflow = await db_client.get_workflow(workflow_id, organization_id=organization_id)
        brouillon = await db_client.get_draft_version(workflow_id) if workflow else None
        active = (brouillon or workflow.released_definition) if workflow else None
        if active is None:
            # Comme avant le chantier : un graphe fourni avec la case du schéma est traité.
            if definition is not None and allume is not None:
                return appliquer(definition, allume, bool(lisible))
            return definition
        if allume is None:
            allume = bool(reglage_allume(active.workflow_configurations))
        if lisible is None:
            lisible = bool(_lisible(active.workflow_configurations))
        existante = active.workflow_json
    if definition is not None:
        return appliquer(definition, allume, bool(lisible))
    nouvelle = appliquer(existante, allume, bool(lisible))
    return nouvelle if nouvelle != existante else None


def _lisible(configurations: dict | None) -> bool | None:
    """La case du parcours lisible de ces configurations ; ``None`` si elle n'y est pas
    (comme ``reglage_allume`` : on lit alors la case déjà enregistrée)."""
    if not configurations or CLE_LISIBLE not in configurations:
        return None
    return configurations[CLE_LISIBLE] is True
