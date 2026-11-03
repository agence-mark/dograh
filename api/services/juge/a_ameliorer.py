"""[.mark] U12 : l'entrée UNIQUE par laquelle un verdict du juge remplit « À améliorer » (clé d'API et Claude Code, un seul chemin).

Le module de tri de « À améliorer » est celui du lot G1 : tant qu'il n'est pas sur la base de ce lot, cette fonction range les points
dans une ligne de ``organization_configurations`` (``MARK_A_AMELIORER_JUGE``, bornée). À la fusion de G1, ``signaler`` est la SEULE fonction à
rebrancher sur son module (``ajouter``) ; les appelants (``juge_ecrire``, l'après-appel sur clé) ne changent pas.

Un point = un critère raté ou non vérifiable d'un élément jugé (vrai appel ou test), avec la réplique citée et la preuve. Idempotent :
rejuger un élément remplace ses points, jamais ne les double.
"""

from __future__ import annotations

from typing import Any

from api.services.builder import stock
from api.services.juge import file

CLE = "MARK_A_AMELIORER_JUGE"
POINTS_MAX = 300
RATES = ("rate", "non_verifiable")


def points_de(item: dict[str, Any], verdicts: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    return [
        {
            "id": f"{item['id']}::{v['critere'][:80]}",
            "element": item["id"],
            "type": item.get("type"),
            "workflow_id": item.get("workflow_id"),
            "run_id": item.get("run_id"),
            "test": item.get("test"),
            "critere": v["critere"],
            "verdict": v["verdict"],
            "replique": v.get("replique"),
            "preuve": v.get("preuve"),
            "source": source,
            "le": file.maintenant(),
        }
        for v in verdicts
        if v.get("verdict") in RATES
    ]


async def signaler(organisation: int, item: dict[str, Any], verdicts: list[dict[str, Any]], source: str) -> int:
    """Range les points ratés de l'élément (ceux d'un jugement précédent du même élément sont remplacés). Rend leur nombre."""
    nouveaux = points_de(item, verdicts, source)

    def transformer(ligne):
        anciens = [p for p in (ligne or {}).get("points") or [] if p.get("element") != item["id"]]
        return {"points": [*anciens, *nouveaux][-POINTS_MAX:]}

    await stock.modifier(organisation, CLE, transformer)
    return len(nouveaux)


async def lister(organisation: int, workflow_id: int | None = None, depuis: str | None = None) -> list[dict[str, Any]]:
    points = list((await stock.lire(organisation, CLE) or {}).get("points") or [])
    return [
        p
        for p in points
        if (workflow_id is None or p.get("workflow_id") == workflow_id) and (depuis is None or str(p.get("le") or "") > depuis)
    ]
