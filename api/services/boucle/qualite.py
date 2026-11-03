"""[.mark] U8 (lots C, D, E) : la page Qualité, calculée depuis ce que l'après-appel a rangé dans ``annotations['boucle']``.

Aucune donnée nouvelle : les indicateurs de chaque appel (``indicateurs.py``), sa version (``version.py``) et le verdict du juge sont
agrégés par agent, par motif d'appel et par version. Une lecture bornée par la base (R7) : les ``LIGNES_QUALITE_MAX`` appels les plus
récents de la fenêtre, jamais un journal.

* la note du juge est sur 5 : 5 × (critères réussis ÷ critères jugés) ; « non vérifiable » compte comme raté (règle du juge) ;
* le taux de résolution d'un motif est la part de ses appels qui ont obtenu une issue ;
* la comparaison avant / après compare, par agent, les versions vues dans la fenêtre (l'appel porte sa version).

⛔ Ne lève jamais sur une ligne illisible : elle est ignorée. Zéro vocabulaire métier (les motifs sont ceux de la fiche de l'agent).
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any

from api.db import db_client

JOURS_PAR_DEFAUT = 7
MOTIFS_MAX = 30
VERSIONS_PAR_AGENT_MAX = 4


def note_du_juge(juge: dict[str, Any]) -> float | None:
    verdicts = juge.get("verdicts") if isinstance(juge, dict) and juge.get("etat") == "juge" else None
    if not isinstance(verdicts, list) or not verdicts:
        return None
    reussis = sum(1 for v in verdicts if isinstance(v, dict) and v.get("verdict") == "reussi")
    return round(5 * reussis / len(verdicts), 2)


def part(numerateur: int, denominateur: int) -> float | None:
    return round(numerateur / denominateur, 4) if denominateur > 0 else None


def _moyenne(valeurs: list[float]) -> float | None:
    return round(sum(valeurs) / len(valeurs), 2) if valeurs else None


def _resume(lignes: list[dict[str, Any]]) -> dict[str, Any]:
    """Les chiffres d'un groupe d'appels (tous, un agent, une version)."""
    notes, latences, couts = [], [], []
    avec_bilan = issues = transferts = raccroches = impasses = 0
    for ligne in lignes:
        bilan = (ligne["annotations"].get("boucle") or {}) if isinstance(ligne["annotations"], dict) else {}
        i = bilan.get("indicateurs") or {}
        note = note_du_juge(ligne["annotations"].get("juge") or {})
        if note is not None:
            notes.append(note)
        if not i:
            continue
        avec_bilan += 1
        issues += bool(i.get("issue_obtenue"))
        transferts += bool(i.get("transfert"))
        raccroches += bool(i.get("raccroche_avant_la_fin"))
        impasses += 1 if i.get("impasses") else 0
        if isinstance(i.get("latence_mediane"), (int, float)):
            latences.append(float(i["latence_mediane"]))
        if isinstance(i.get("cout"), (int, float)):
            couts.append(float(i["cout"]))
    return {
        "appels": len(lignes),
        "appels_mesures": avec_bilan,
        "juges": len(notes),
        "note": _moyenne(notes),
        "issues": issues,
        "part_issue": part(issues, avec_bilan),
        "transferts": transferts,
        "part_transferts": part(transferts, avec_bilan),
        "raccroches": raccroches,
        "part_raccroches": part(raccroches, avec_bilan),
        "avec_impasse": impasses,
        "part_impasse": part(impasses, avec_bilan),
        "reponse_mediane": round(median(latences), 2) if latences else None,
        "cout": round(sum(couts), 4) if couts else None,
    }


def _motifs(lignes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    par_motif: dict[str, list[bool]] = defaultdict(list)
    for ligne in lignes:
        i = ((ligne["annotations"].get("boucle") or {}).get("indicateurs")) or {}
        if i.get("motif"):
            par_motif[i["motif"]].append(bool(i.get("issue_obtenue")))
    classes = [
        {"motif": m, "appels": len(r), "part_resolu": part(sum(r), len(r))} for m, r in par_motif.items()
    ]
    return sorted(classes, key=lambda x: (-x["appels"], x["motif"]))[:MOTIFS_MAX]


def _versions(lignes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Par agent qui a eu au moins deux versions en ligne dans la fenêtre : les versions vues, de la plus récente à la plus ancienne."""
    par_agent: dict[int, dict[int, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    noms: dict[int, str] = {}
    for ligne in lignes:
        version = ligne.get("version")
        if version is None:
            version = (((ligne["annotations"].get("boucle") or {}).get("version")) or {}).get("version")
        if version is None:
            continue
        par_agent[ligne["workflow_id"]][int(version)].append(ligne)
        noms[ligne["workflow_id"]] = ligne["workflow_nom"]
    sortie = []
    for wf, versions in par_agent.items():
        if len(versions) < 2:
            continue
        for numero in sorted(versions, reverse=True)[:VERSIONS_PAR_AGENT_MAX]:
            sortie.append({"workflow_id": wf, "workflow_nom": noms[wf], "version": numero, **_resume(versions[numero])})
    return sortie


async def calculer(organisation_id: int, *, jours: int = JOURS_PAR_DEFAUT, workflow_id: int | None = None) -> dict[str, Any]:
    lignes = await db_client.runs_pour_la_qualite(organisation_id, jours=jours, workflow_id=workflow_id)
    par_agent: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for ligne in lignes:
        par_agent[ligne["workflow_id"]].append(ligne)
    agents = []
    for wf, appels in par_agent.items():
        dernier = next((a["version"] for a in appels if a.get("version") is not None), None)
        agents.append({"workflow_id": wf, "workflow_nom": appels[0]["workflow_nom"], "version": dernier, **_resume(appels)})
    agents.sort(key=lambda a: (-a["appels"], a["workflow_nom"]))
    return {
        "jours": jours,
        "global": _resume(lignes),
        "motifs": _motifs(lignes),
        "agents": agents,
        "versions": _versions(lignes),
    }
