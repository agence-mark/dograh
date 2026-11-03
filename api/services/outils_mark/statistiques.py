"""[.mark] U3 sexies point 5 : les statistiques par outil, calculées à la volée sur les appels.

Aucune table. Source : les événements ``rtf-function-call-start`` / ``rtf-function-call-end`` du journal de chaque appel de
l'organisation, sur les 30 derniers jours et au plus ``LIMITE_APPELS`` appels (les plus récents). Un outil se reconnaît à
son nom de fonction (celui que voit le modèle) ; les outils d'un serveur MCP à leur préfixe ``mcp__<serveur>__``.

* exécutions : appels d'outil commencés ;
* réussite : part des exécutions terminées sans échec (un appel sans fin compte comme un échec) ;
* durée médiane : début à fin, en millisecondes ;
* agents et étapes : lus dans la dernière version de chaque agent (``tool_uuids`` de ses étapes).
"""

from __future__ import annotations

import statistics
from typing import Any

from api.db import db_client
from api.services.analyse_run.mesures import _ms
from api.services.workflow.enveloppe_des_actions import est_un_echec
from api.services.workflow.tools.custom_tool import custom_tool_function_name
from api.services.workflow.tools.mcp_tool import namespace_function_name

JOURS = 30
LIMITE_APPELS = 2000
PAR_PAGE = 25


def reconnait(outil: Any, nom_de_fonction: str) -> bool:
    categorie = str(getattr(outil.category, "value", outil.category))
    if categorie == "mcp":
        prefixe = namespace_function_name(outil.name, "", fallback=outil.tool_uuid[:8])
        return nom_de_fonction.startswith(prefixe)
    if categorie == "calculator":
        return nom_de_fonction == "safe_calculator"
    return nom_de_fonction == custom_tool_function_name(outil.name)


def _executions(lignes: list[dict[str, Any]], outil: Any) -> list[dict[str, Any]]:
    sortie: list[dict[str, Any]] = []
    for ligne in lignes:
        fins = {
            (e.get("payload") or {}).get("tool_call_id"): e
            for e in ligne["evenements"]
            if e.get("type") == "rtf-function-call-end"
        }
        for e in ligne["evenements"]:
            if e.get("type") != "rtf-function-call-start":
                continue
            charge = e.get("payload") or {}
            if not reconnait(outil, str(charge.get("function_name") or "")):
                continue
            fin = fins.get(charge.get("tool_call_id"))
            duree = None
            if fin is not None:
                ecart = _ms(fin.get("timestamp")) - _ms(e.get("timestamp"))
                duree = None if ecart != ecart else max(0, round(ecart))  # NaN : horodatage illisible
            sortie.append(
                {
                    "run_id": ligne["run_id"],
                    "workflow_id": ligne["workflow_id"],
                    "date": ligne["created_at"].isoformat() if ligne.get("created_at") else None,
                    "outil_mcp": charge.get("function_name") if str(getattr(outil.category, "value", outil.category)) == "mcp" else None,
                    "reussie": fin is not None and not est_un_echec((fin.get("payload") or {}).get("result")),
                    "duree_ms": duree,
                    "etape": e.get("node_name"),
                }
            )
    return sortie


async def _agents_et_etapes(organization_id: int, outil: Any) -> list[dict[str, Any]]:
    trouves = []
    for agent in await db_client.get_all_workflows(organization_id=organization_id):
        definition = getattr(agent.current_definition, "workflow_json", None) or {}
        etapes = [
            str((n.get("data") or {}).get("name") or n.get("id"))
            for n in definition.get("nodes", [])
            if outil.tool_uuid in ((n.get("data") or {}).get("tool_uuids") or [])
        ]
        if etapes:
            trouves.append({"agent_id": agent.id, "agent": agent.name, "etapes": etapes})
    return trouves


def _resume(executions: list[dict[str, Any]]) -> dict[str, Any]:
    durees = [x["duree_ms"] for x in executions if x["duree_ms"] is not None]
    reussies = sum(1 for x in executions if x["reussie"])
    return {
        "executions": len(executions),
        "reussies": reussies,
        "echecs": len(executions) - reussies,
        "reussite": None if not executions else round(100 * reussies / len(executions)),
        "duree_mediane_ms": round(statistics.median(durees)) if durees else None,
    }


async def pour_un_outil(organization_id: int, outil: Any, *, page: int = 0) -> dict[str, Any]:
    lignes = await db_client.evenements_d_outils(organization_id, jours=JOURS, limite=LIMITE_APPELS)
    executions = _executions(lignes, outil)
    recentes = sorted(executions, key=lambda x: (x["date"] or "", x["run_id"]), reverse=True)
    debut = max(0, page) * PAR_PAGE
    return {
        **_resume(executions),
        "jours": JOURS,
        "page": page,
        "par_page": PAR_PAGE,
        "total_executions": len(recentes),
        "dernieres_executions": recentes[debut : debut + PAR_PAGE],
        "agents": await _agents_et_etapes(organization_id, outil),
    }


async def pour_les_outils(organization_id: int, outils: list[Any]) -> dict[str, dict[str, Any]]:
    """Le résumé de chaque outil (une seule lecture des appels), par ``tool_uuid`` : pour le tableau des outils."""
    lignes = await db_client.evenements_d_outils(organization_id, jours=JOURS, limite=LIMITE_APPELS)
    agents_par_outil: dict[str, int] = {}
    for agent in await db_client.get_all_workflows(organization_id=organization_id):
        definition = getattr(agent.current_definition, "workflow_json", None) or {}
        utilises = {
            u for n in definition.get("nodes", []) for u in ((n.get("data") or {}).get("tool_uuids") or [])
        }
        for u in utilises:
            agents_par_outil[u] = agents_par_outil.get(u, 0) + 1
    return {
        o.tool_uuid: {**_resume(_executions(lignes, o)), "nb_agents": agents_par_outil.get(o.tool_uuid, 0), "jours": JOURS}
        for o in outils
    }
