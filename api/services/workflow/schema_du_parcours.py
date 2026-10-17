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

Chantier agents-specialises (Evan, 16/10) : le bloc de fin de global dépend du TYPE de workflow,
lu dans les réglages enregistrés : accueil (``agents_specialises`` non vide), spécialiste
(``agent_principal_id`` posé) ou agent seul. Dans un groupe, le schéma est toujours généré : la
case est ignorée. Agent seul : inchangé. Accueil et spécialiste : un bloc « # Ton équipe » (qui je
suis, comment passer ou rendre la main) précède « # Tes étapes ».

⛔ Ce qui n'y entre jamais : autre chose que les noms d'étapes et leur rôle, recopié de
notre prompt (aucun mot de métier dans le code). ⛔ Les blocs sont délimités et remplacés à
chaque enregistrement : jamais empilés, jamais au contact du texte écrit à la main
(une ligne vide les sépare). Éteint : les blocs laissés sont retirés, et un agent
qui n'en a jamais eu s'enregistre exactement comme avant.
"""

from __future__ import annotations

import copy
import re

from loguru import logger

from api.services.groupe.passations import (
    CLE_AGENTS_SPECIALISES,
    MARQUEUR_RETOUR,
    agent_principal_de,
)
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_CHAMPS,
    CLE_INTERRUPTEUR,
    CLE_MODE,
    CLE_PORTES_DANS_LA_REPONSE,
    CLE_SCHEMA_DU_PARCOURS,
    MODE_GREFFIER,
)

CLE_REGLAGE = CLE_SCHEMA_DU_PARCOURS

# Les trois types de workflow (agents-specialises), lus dans les réglages enregistrés.
TYPE_SEUL, TYPE_ACCUEIL, TYPE_SPECIALISTE = "seul", "accueil", "specialiste"
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


def type_de_workflow(configurations: dict | None) -> str:
    """Accueil (``agents_specialises`` non vide), spécialiste (``agent_principal_id`` posé), sinon
    agent seul. ⛔ Ne lève jamais (illisible = agent seul)."""
    try:
        liste = (configurations or {}).get(CLE_AGENTS_SPECIALISES)
        if isinstance(liste, (list, tuple)) and len(liste) > 0:
            return TYPE_ACCUEIL
        if agent_principal_de(configurations) is not None:
            return TYPE_SPECIALISTE
    except Exception:  # noqa: BLE001
        pass
    return TYPE_SEUL


def _une_ligne(texte: str | None) -> str:
    return " ".join((texte or "").split())


def _equipe_accueil(collegues: list[tuple[str, str]]) -> list[str]:
    lignes = [
        "# Ton équipe",
        "Tu es l'accueil. Pour passer la main à un collègue, tu appelles son outil, sans rien dire. "
        "Quand un collègue te rend la main, tu lis la réponse à sa dernière question.",
    ]
    if collegues:
        lignes.append("Tes collègues :")
        for nom, description in collegues:
            lignes.append(f"- {nom} : {description}" if description else f"- {nom}")
    return lignes


def _equipe_specialiste(etapes: list[dict]) -> list[str]:
    depart = next((n for n in etapes if n.get("type") == "startCall"), None)
    mission = _role(depart) if depart else ""
    retours = [
        _nom(n) for n in etapes if (n.get("data") or {}).get(MARQUEUR_RETOUR) is True
    ]
    # Relecture du lot 6 : une fin encore « à rédiger » n'est pas une sortie citée (elle n'est offerte
    # à aucune porte tant que son texte n'est pas écrit, voir ``sortie_en_attente``).
    from api.services.groupe.passations import _texte_en_attente

    fins = [
        _nom(n)
        for n in etapes
        if n.get("type") == "endCall"
        and (n.get("data") or {}).get(MARQUEUR_RETOUR) is not True
        and not _texte_en_attente((n.get("data") or {}).get("prompt"))
    ]
    phrases = [f"Ton rôle : {mission}."] if mission else []
    phrases.append("Tu reçois un appel déjà commencé : tout ce qui a été dit compte.")
    if retours and fins:
        # Lot 2 d'orchestrateur-trois-cerveaux (D5) : deux sorties pour chaque collègue. Plusieurs
        # étapes de chaque sorte : toutes sont citées, chacune est une sortie valable.
        clore = " ou ".join(f"la sortie {nom}" for nom in fins)
        rendre = " ou ".join(f"la sortie {nom}" for nom in retours)
        phrases.append(
            f"Tu as deux sorties : pour clore l'appel, tu écris {clore} ; "
            f"pour rendre la main à l'accueil, tu écris {rendre}."
        )
    elif retours:
        # Plusieurs étapes marquées : toutes sont citées, chacune est une sortie valable.
        sorties = " ou ".join(f"la sortie {nom}" for nom in retours)
        phrases.append(
            f"Pour rendre la main à l'accueil, tu écris {sorties}, "
            "dès que la demande n'est pas la tienne ou que ton travail est fini."
        )
    return ["# Ton équipe", " ".join(phrases)]


def parcours(
    definition: dict,
    type_workflow: str = TYPE_SEUL,
    collegues: list[tuple[str, str]] | None = None,
) -> str:
    """Le bloc ``<parcours_genere>`` : la carte des étapes et de leur rôle, précédée pour un
    accueil ou un spécialiste du bloc « # Ton équipe »."""
    noeuds = definition.get("nodes") or []
    etapes = [n for n in noeuds if n.get("type") in TYPES_ETAPE]
    lignes = [DEBUT_PARCOURS]
    if type_workflow == TYPE_ACCUEIL:
        lignes += _equipe_accueil(collegues or []) + [""]
    elif type_workflow == TYPE_SPECIALISTE:
        lignes += _equipe_specialiste(etapes) + [""]
    lignes.append("# Les étapes de l'appel" if type_workflow == TYPE_SEUL else "# Tes étapes")
    for etape in _ordre_des_etapes(etapes, definition.get("edges") or []):
        role = _role(etape)
        lignes.append(f"{_nom(etape)} : {role}" if role else _nom(etape))
    lignes.append(FIN_PARCOURS)
    return "\n".join(lignes)


def appliquer(
    definition: dict | None,
    allume: bool,
    position: bool = True,
    type_workflow: str = TYPE_SEUL,
    collegues: list[tuple[str, str]] | None = None,
) -> dict | None:
    """La définition avec les blocs à jour (allumé) ou retirés (éteint).
    ``position`` : « Tu es ici » en fin d'étape ; faux en greffier avec les portes dans la
    réponse, où le bloc de fin d'étape le dit (C4). ``type_workflow`` et ``collegues`` (nom de
    l'outil, description) : le bloc « # Ton équipe » d'un accueil ou d'un spécialiste.

    Toujours une copie ; une définition sans bloc, éteinte, revient identique."""
    if not definition:
        return definition
    resultat = copy.deepcopy(definition)
    bloc = parcours(resultat, type_workflow, collegues) if allume else None
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
    """La valeur de la case dans ces configurations, ``None`` si elle n'y est pas. Dans un
    groupe (accueil ou spécialiste), toujours vrai : la case est ignorée."""
    if not configurations:
        return None
    if type_de_workflow(configurations) != TYPE_SEUL:
        return True
    if CLE_REGLAGE not in configurations:
        return None
    return bool(configurations[CLE_REGLAGE])


async def collegues_de(
    definition: dict | None, organization_id: int
) -> list[tuple[str, str]] | None:
    """Les collègues d'un accueil : ``(nom de l'outil, description)`` de chaque outil de
    passation (``transfer_agent``) posé sur une étape du graphe, dans l'ordre du graphe, sans
    doublon. Lu en base par la couche ``db_client``. ⛔ Ne lève jamais ; ``None`` si la base ne
    répond pas (jamais ``[]``, qui voudrait dire « aucun collègue » et ferait réécrire un bloc
    sans eux : l'appelant garde alors le bloc déjà écrit)."""
    from api.db import db_client
    from api.enums import ToolCategory
    from api.services.workflow.tools.custom_tool import custom_tool_function_name

    try:
        uuids: list[str] = []
        for noeud in (definition or {}).get("nodes") or []:
            for u in (noeud.get("data") or {}).get("tool_uuids") or []:
                if isinstance(u, str) and u not in uuids:
                    uuids.append(u)
        if not uuids:
            return []
        outils = await db_client.get_tools_by_uuids(uuids, organization_id)
        par_uuid = {
            o.tool_uuid: o for o in outils if o.category == ToolCategory.TRANSFER_AGENT.value
        }
        vus: set[str] = set()
        sortie: list[tuple[str, str]] = []
        for u in uuids:
            outil = par_uuid.get(u)
            if outil is None:
                continue
            nom = custom_tool_function_name(outil.name)
            if nom and nom not in vus:
                vus.add(nom)
                sortie.append((nom, _une_ligne(outil.description)))
        return sortie
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[schema du parcours] outils de passation illisibles, bloc d'équipe gardé tel quel : {e!r}"
        )
        return None


async def _ecrire(
    definition: dict | None,
    allume: bool,
    configurations: dict,
    organization_id: int,
) -> dict | None:
    """``appliquer`` avec le type et les collègues lus dans ``configurations`` ; la base ne se lit
    que pour un accueil. Si elle ne répond pas, la définition est rendue telle quelle (le bloc
    déjà écrit reste, ce qui vaut mieux qu'un accueil sans collègues)."""
    type_workflow = type_de_workflow(configurations)
    collegues: list[tuple[str, str]] | None = []
    if allume and type_workflow == TYPE_ACCUEIL:
        collegues = await collegues_de(definition, organization_id)
        if collegues is None:
            return definition
    return appliquer(definition, allume, _position(configurations), type_workflow, collegues)


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
        return await _ecrire(
            definition, bool(reglage_allume(configurations)), configurations, organization_id
        )
    workflow = await db_client.get_workflow(workflow_id, organization_id=organization_id)
    brouillon = await db_client.get_draft_version(workflow_id) if workflow else None
    active = (brouillon or workflow.released_definition) if workflow else None
    if active is None:
        return definition
    reglages = configurations if configurations is not None else (active.workflow_configurations or {})
    allume = bool(reglage_allume(reglages))
    if definition is not None:
        return await _ecrire(definition, allume, reglages, organization_id)
    nouvelle = await _ecrire(active.workflow_json, allume, reglages, organization_id)
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
