"""[.mark] Builder, lot 6 : la garde de publication (Q12, B38, B42).

La publication est refusée si :

* le **contrôle du prompt** a un défaut bloquant sur le brouillon ;
* un **test obligatoire** échoue, n'a jamais été rejoué, ou a été rejoué sur une AUTRE version du brouillon (B38 : après toute
  modification, la suite est rejouée avant de publier).

Jamais la moyenne (B42) : un seul test obligatoire rouge suffit. Les tests non obligatoires informent, ils ne bloquent pas.

**Portée** : seuls les agents SUIVIS par le builder (qui ont des tests, ou une trace du builder) sont gardés. Un agent qui n'a
rien de tout cela se publie comme avant (aucun agent existant n'est bloqué sans raison). Interrupteur d'urgence côté serveur :
``MARK_PUBLICATION_SANS_GARDE=1``.

La forme rendue est celle de la validation (``is_valid`` + ``errors``) que l'écran sait déjà afficher, plus le détail.
"""

from __future__ import annotations

import os
from typing import Any

from api.services.builder import stock
from api.services.builder.constantes import PREFIXE_BUILDER
from api.services.builder.controle.service import controler_l_agent
from api.services.builder.tests_agent import stockage

INTERRUPTEUR = "MARK_PUBLICATION_SANS_GARDE"


async def agent_suivi(organization_id: int, workflow_id: int) -> bool:
    if await stockage.lister(organization_id, workflow_id):
        return True
    return bool(await stock.lister(organization_id, f"{PREFIXE_BUILDER}{workflow_id}:"))


async def problemes_des_tests_obligatoires(organization_id: int, workflow_id: int, version: int | None) -> list[dict[str, Any]]:
    problemes = []
    for test in await stockage.lister(organization_id, workflow_id):
        if not test.get("obligatoire"):
            continue
        derniere = await stockage.derniere_execution(organization_id, workflow_id, test["slug"])
        if derniere is None:
            raison = "never replayed"
        elif derniere.get("version") != version:
            raison = f"replayed on version {derniere.get('version')}, the draft is now version {version}: replay the suite"
        elif derniere.get("statut") != "ok":
            raison = f"failed ({derniere.get('reussis')}/{derniere.get('total')})"
        else:
            continue
        problemes.append({"slug": test["slug"], "nom": test["nom"], "raison": raison})
    return problemes


async def verifier_avant_publication(workflow: Any, brouillon: Any, organization_id: int) -> dict[str, Any] | None:
    """``None`` : on peut publier. Sinon le corps du refus (``is_valid`` faux + ``errors`` + détail)."""
    if os.environ.get(INTERRUPTEUR) == "1":
        return None
    if not await agent_suivi(organization_id, workflow.id):
        return None
    controle = await controler_l_agent(workflow, organization_id, graphe=brouillon.workflow_json)
    tests = await problemes_des_tests_obligatoires(organization_id, workflow.id, getattr(brouillon, "version_number", None))
    if controle["ok"] and not tests:
        return None
    erreurs = [{"kind": "node", "id": None, "field": "data.prompt", "message": f"[Prompt check] {e['message']}"} for e in controle["elements"] if e["statut"] == "echec"]
    erreurs += [{"kind": "node", "id": None, "field": None, "message": f"[Required test] {t['nom']}: {t['raison']}"} for t in tests]
    return {
        "is_valid": False,
        "errors": erreurs,
        "garde": "builder",
        "controle": controle["bloquants"],
        "tests_obligatoires": tests,
    }
