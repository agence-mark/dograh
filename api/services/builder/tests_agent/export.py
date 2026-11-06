"""[.mark] Builder, lot 6 : l'export vers le labo (Q2). Un FICHIER téléchargeable, aucune écriture hors de Dograh.

Le fichier est un lot de tests (format ``tests_rejouables`` v1 étendu, données déjà fictives) et, si on le demande, leurs
dernières exécutions : le labo le range où il veut. Rien n'est envoyé nulle part depuis ici.
"""

from __future__ import annotations

import json
from typing import Any

from api.services.builder.tests_agent import stockage

FORMAT = "tests-agent-mark"
VERSION = 1


async def exporter(organization_id: int, workflow_id: int, nom_de_l_agent: str, *, avec_les_resultats: bool = True) -> dict[str, Any]:
    tests = await stockage.lister(organization_id, workflow_id)
    lot: list[dict[str, Any]] = []
    for t in tests:
        entree = {k: v for k, v in t.items() if k != "organisation_id"}
        if avec_les_resultats:
            entree["executions"] = [
                {k: v for k, v in e.items() if k != "essais"} | {"essais": [{"numero": x["numero"], "reussi": x["reussi"]} for x in e.get("essais") or []]}
                for e in await stockage.resultats(organization_id, workflow_id, t["slug"])
            ]
        lot.append(entree)
    return {"format": FORMAT, "version": VERSION, "agent": nom_de_l_agent, "exporte_le": stockage.maintenant(), "tests": lot}


def en_octets(lot: dict[str, Any]) -> bytes:
    return (json.dumps(lot, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
