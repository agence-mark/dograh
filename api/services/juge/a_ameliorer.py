"""[.mark] U12 : l'entrée UNIQUE par laquelle un verdict du juge remplit « À améliorer » (clé d'API et Claude Code, un seul chemin).

Depuis G1b, cette entrée est branchée sur le module de la boucle (``services/boucle/ingestion``, table ``mark_ameliorations``) : un
verdict par clé d'API et le même verdict écrit par Claude Code (``juge_ecrire``) donnent le MÊME problème, regroupé avec ses pareils.
Rejuger un élément (un appel, un test) REMPLACE son jugement précédent, jamais ne le double.

La ligne de stock provisoire ``MARK_A_AMELIORER_JUGE`` (U12, avant G1) n'existe plus : ``verser_le_stock_provisoire`` en verse les
points dans la table (idempotent : un cas déjà compté ne l'est pas deux fois) puis supprime la ligne.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger

from api.db import db_client
from api.services.boucle import ingestion
from api.services.builder import stock

CLE_PROVISOIRE = "MARK_A_AMELIORER_JUGE"
LIMITE = 100


async def signaler(organisation: int, item: dict[str, Any], verdicts: list[dict[str, Any]], lignes: list[tuple[str, str]], source: str) -> int:
    """Range les critères ratés de l'élément jugé (``item`` : un élément de « À juger », appel ou test) dans « À améliorer ».
    Rend le nombre de problèmes touchés. ``source`` (``cle_api`` ou ``claude_code``) ne change rien au résultat : une seule entrée."""
    if item.get("type") == "test":
        if item.get("workflow_id") is None or not item.get("test"):
            return 0
        return await ingestion.ingerer_les_verdicts(
            organisation, int(item["workflow_id"]), None, verdicts, lignes, test=str(item["test"])
        )
    run, organisation_du_run = await db_client.get_workflow_run_with_context(
        int(item["run_id"]), organization_id=organisation
    )
    if run is None or organisation_du_run != organisation:
        return 0
    return await ingestion.ingerer_un_appel_juge(run, organisation, verdicts, lignes)


async def verser_le_stock_provisoire(organisation: int) -> int:
    """Verse dans la table les points de l'ancienne ligne de stock, puis la supprime. Idempotent, ne lève jamais. Rend le nombre de points versés."""
    try:
        ligne = await stock.lire(organisation, CLE_PROVISOIRE)
        if ligne is None:
            return 0
        points = [p for p in ligne.get("points") or [] if isinstance(p, dict) and p.get("workflow_id") is not None]
        par_element: dict[str, list[dict[str, Any]]] = {}
        for p in points:
            par_element.setdefault(str(p.get("element")), []).append(p)
        verses = 0
        for elements in par_element.values():
            premier = elements[0]
            verdicts = [{k: p.get(k) for k in ("critere", "verdict", "replique", "preuve")} | {"confiance": 0.7} for p in elements]
            if premier.get("run_id") is not None:
                run, org_du_run = await db_client.get_workflow_run_with_context(
                    int(premier["run_id"]), organization_id=organisation
                )
                if run is None or org_du_run != organisation:
                    continue
                from api.services.juge import appels

                await ingestion.ingerer_un_appel_juge(run, organisation, verdicts, appels.dossier_d_un_run(run)["lignes"])
            elif premier.get("test"):
                await ingestion.ingerer_les_verdicts(organisation, int(premier["workflow_id"]), None, verdicts, [], test=str(premier["test"]))
            verses += len(elements)
        await stock.supprimer(organisation, CLE_PROVISOIRE)
        return verses
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[boucle] stock provisoire du juge non versé : {type(erreur).__name__}")
        return 0


async def lister(organisation: int, workflow_id: int | None = None, depuis: str | None = None) -> list[dict[str, Any]]:
    """Les problèmes ouverts de la file (ceux que le juge a relevés, mais aussi le code, les tests), changés depuis ``depuis`` (date ISO)."""
    await verser_le_stock_provisoire(organisation)
    limite = datetime.fromisoformat(depuis) if depuis else None
    if limite is not None and limite.tzinfo is None:
        limite = limite.replace(tzinfo=UTC)
    problemes, _ = await db_client.lister_les_ameliorations(organisation, workflow_id=workflow_id, par_page=LIMITE, depuis=limite)
    return [
        {
            "id": p["id"],
            "workflow_id": p["workflow_id"],
            "critere": p.get("critere") or p.get("titre"),
            "titre": p.get("titre"),
            "releve_par": p.get("releve_par"),
            "gravite": p.get("gravite"),
            "etat": p.get("etat"),
            "replique": p.get("replique"),
            "preuve": ((p.get("cas") or [{}])[-1] or {}).get("citation"),
            "le": p["derniere_le"].isoformat() if p.get("derniere_le") else None,
        }
        for p in problemes
        if p.get("etat") == "a_trier"
    ]
