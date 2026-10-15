"""[.mark] Chantier correctifs-modules, lot 4 bis : le schéma du parcours.

Plan : ``Labo-agent-vocal/plans/correctifs-modules/2026-09-28-plan-correctifs-modules.md``.

Réglage d'agent ``generer_schema_parcours`` (« Generate the flow map »), éteint par
défaut. Allumé, chaque enregistrement de l'agent lit son graphe et écrit :

- à la fin du prompt global, un bloc ``<parcours_genere>`` : « # Les étapes de l'appel »,
  une ligne par étape et son rôle (la ligne sous « # Ta mission ici » de son prompt) ;
- à la fin du prompt de chaque étape, ``<position_generee>Tu es ici : <étape></position_generee>``,
  sauf en greffier avec les portes dans la réponse : le bloc de fin d'étape, ajouté
  pendant l'appel (``porte_parlee``), le dit déjà (chantier schema-parcours-unique, C4).

Chantier schema-parcours-unique (C1, Evan 15/10) : une seule case. L'ancienne carte (les
portes « → » sous chaque étape) et la case ``parcours_lisible`` ont disparu ; une valeur
encore enregistrée de cette case est sans effet.

Pourquoi dans le code : écrit à la main (le ``schema.js`` des agents de la
refonte), le schéma finit faux dès qu'une porte change. Généré à l'enregistrement,
il ne peut pas diverger du graphe.

⛔ Ce qui n'y entre jamais : autre chose que les noms d'étapes et leur rôle, recopié de
notre prompt (aucun mot de métier dans le code). ⛔ Les blocs sont délimités et remplacés à
chaque enregistrement : jamais empilés, jamais au contact du texte écrit à la main
(une ligne vide les sépare). Éteint : les blocs laissés sont retirés, et un agent
qui n'en a jamais eu s'enregistre exactement comme avant.
"""

from __future__ import annotations

import copy
import re

from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_CHAMPS,
    CLE_INTERRUPTEUR,
    CLE_MODE,
    CLE_PORTES_DANS_LA_REPONSE,
    CLE_SCHEMA_DU_PARCOURS,
    MODE_GREFFIER,
)

CLE_REGLAGE = CLE_SCHEMA_DU_PARCOURS
# Chantier repliques-coupees, lot 4 ter (D12, D13), devenu le seul format (schema-parcours-unique,
# C1) : une ligne par étape, son nom et son rôle ; ni portes ni « → » (les sorties sont en fin
# d'étape, et « → » ne sert qu'à changer d'étape). Le rôle est la ligne sous « # Ta mission
# ici » du prompt de l'étape, écrite par nous : le code n'y met aucun mot de métier.
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


def _role(noeud: dict) -> str:
    """La ligne sous « # Ta mission ici » du prompt de l'étape, sans point final."""
    trouve = _MISSION.search(retirer((noeud.get("data") or {}).get("prompt")) or "")
    return trouve.group(1).strip().rstrip(".") if trouve else ""


def parcours(definition: dict) -> str:
    """Le bloc ``<parcours_genere>`` : la carte des étapes et de leur rôle."""
    noeuds = definition.get("nodes") or []
    etapes = [n for n in noeuds if n.get("type") in TYPES_ETAPE]
    lignes = [DEBUT_PARCOURS, "# Les étapes de l'appel"]
    for etape in _ordre_des_etapes(etapes, definition.get("edges") or []):
        role = _role(etape)
        lignes.append(f"{_nom(etape)} : {role}" if role else _nom(etape))
    lignes.append(FIN_PARCOURS)
    return "\n".join(lignes)


def appliquer(
    definition: dict | None, allume: bool, position: bool = True
) -> dict | None:
    """La définition avec les blocs à jour (allumé) ou retirés (éteint).
    ``position`` : « Tu es ici » en fin d'étape ; faux en greffier avec les portes dans la
    réponse, où le bloc de fin d'étape le dit (C4).

    Toujours une copie ; une définition sans bloc, éteinte, revient identique."""
    if not definition:
        return definition
    resultat = copy.deepcopy(definition)
    bloc = parcours(resultat) if allume else None
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
        elif allume and position:
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

    - Des configurations sont enregistrées : elles REMPLACENT celles en base
      (``configuration_policy``) ; ce sont donc elles seules qui comptent, une clé
      absente vaut sa valeur par défaut (revue du 15/10, schema-parcours-unique).
    - Aucune configuration (graphe seul, outil MCP) : celles déjà enregistrées.
    - La case seule change : le graphe enregistré est mis à jour, et renvoyé
      seulement s'il change.
    """
    from api.db import db_client

    # Des réglages enregistrés sans graphe ni case du schéma : rien à écrire, et surtout aucune
    # lecture de la base (comme avant le chantier ; les 15 tests de route l'ont rappelé le 15/10).
    if definition is None and reglage_allume(configurations) is None:
        return None
    if configurations is not None and definition is not None:
        return appliquer(definition, bool(reglage_allume(configurations)), _position(configurations))
    workflow = await db_client.get_workflow(workflow_id, organization_id=organization_id)
    brouillon = await db_client.get_draft_version(workflow_id) if workflow else None
    active = (brouillon or workflow.released_definition) if workflow else None
    if active is None:
        return definition
    reglages = configurations if configurations is not None else (active.workflow_configurations or {})
    allume = bool(reglage_allume(reglages))
    if definition is not None:
        return appliquer(definition, allume, _position(reglages))
    nouvelle = appliquer(active.workflow_json, allume, _position(reglages))
    return nouvelle if nouvelle != active.workflow_json else None


def _position(configurations: dict) -> bool:
    """C4 : « Tu es ici » partout, sauf quand le bloc de fin d'étape le dit pendant l'appel,
    dans les conditions où ``ReglagesFiche.depuis`` bâtit la fiche : fiche allumée avec au
    moins un champ, greffier, portes dans la réponse. Un modèle temps réel n'a pas de fiche :
    cas non lu ici (aucun agent du labo), documenté dans le plan."""
    return not (
        configurations.get(CLE_INTERRUPTEUR) is True
        and bool(configurations.get(CLE_CHAMPS))
        and configurations.get(CLE_MODE) == MODE_GREFFIER
        and configurations.get(CLE_PORTES_DANS_LA_REPONSE) is True
    )
