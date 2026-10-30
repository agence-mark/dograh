"""[.mark] agent-facon-tala, lot 7 (F3) : une issue de transfert ne sort que d'un VRAI résultat de l'outil de transfert.

Constat du banc 1 (run 210, 211) : un appel qui n'a jamais lancé de transfert (la personne a demandé quelqu'un, l'agent a
annoncé une mise en relation puis fini l'appel) s'est terminé avec l'issue « une personne du magasin a pris la main ».
Cause : ``DispositionExtractionService.extract`` (``disposition_extraction.py``, ``_build_user_prompt``) offrait au
classement final TOUTES les issues de la liste de l'agent, y compris celle qu'un outil de transfert pose lui-même à sa
réussite (``call_disposition`` de l'outil, ``pipecat_engine_custom_tools._handle_transfer_result``) ; le classement,
qui lit seulement la conversation, la choisissait sur une phrase d'annonce. Le lot 4 (C4) fait tourner ce classement à
toute fin d'appel, ce qui a rendu le défaut visible à chaque fin sans issue posée.

Règle : une issue réglée comme issue de réussite d'un outil de transfert est **réservée** à cet outil. Elle est posée
quand l'outil rend sa réussite ; le classement final ne la voit pas, ne peut pas la rendre, et ne la recopie jamais
depuis la conversation. Générique : aucun mot de métier, le code vient de la configuration de l'outil.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from loguru import logger

CATEGORIE_TRANSFERT_D_APPEL = "transfer_call"


def codes_reserves(outils: Iterable[Any]) -> set[str]:
    """Les issues de réussite réglées sur les outils de transfert d'appel de ``outils``. ⛔ Ne lève jamais."""
    codes: set[str] = set()
    try:
        for outil in outils or []:
            if getattr(outil, "category", None) != CATEGORIE_TRANSFERT_D_APPEL:
                continue
            config = ((getattr(outil, "definition", None) or {}).get("config")) or {}
            code = config.get("call_disposition")
            if isinstance(code, str) and code.strip():
                codes.add(code.strip().casefold())
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[issue] issues réservées illisibles : {erreur!r}")
    return codes


def sans_les_reservees(options: Iterable[Any], reservees: Iterable[str]) -> list[Any]:
    """Les options du classement, moins les issues réservées à un outil de transfert."""
    interdites = {str(c).casefold() for c in reservees or []}
    if not interdites:
        return list(options)
    return [o for o in options if str(getattr(o, "code", "")).casefold() not in interdites]


async def issues_reservees(
    uuids: Iterable[str],
    organization_id: int | None,
    lire: Callable[[list[str], int], Awaitable[Iterable[Any]]],
) -> set[str]:
    """Les issues réservées par les outils ``uuids`` (lus par ``lire``). Vide sur la moindre difficulté : le
    classement garde alors l'état d'avant. ⛔ Ne lève jamais."""
    try:
        liste = sorted({u for u in uuids or [] if isinstance(u, str)})
        if not liste or not organization_id:
            return set()
        return codes_reserves(await lire(liste, organization_id))
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[issue] outils de transfert non lus : {erreur!r}")
        return set()


def _uuids_d_une_definition(workflow: Any) -> list[str]:
    definition = getattr(workflow, "released_definition", None) or getattr(workflow, "current_definition", None)
    noeuds = (getattr(definition, "workflow_json", None) or {}).get("nodes") or []
    return [
        u
        for n in noeuds
        if isinstance(n, dict)
        for u in ((n.get("data") or {}).get("tool_uuids") or [])
        if isinstance(u, str)
    ]


async def uuids_des_outils_du_groupe(
    depart_id: int | None,
    organization_id: int | None,
    lire_workflow: Callable[[int, int], Awaitable[Any]],
) -> list[str]:
    """Les outils posés sur les étapes de TOUS les agents du groupe de ``depart_id`` : le principal et ses
    spécialisés, quel que soit l'agent sur lequel l'appel finit. Même lecture au téléphone et au clavier.
    Un agent seul : ses propres outils. ⛔ Ne lève jamais."""
    try:
        if not depart_id or not organization_id:
            return []
        from api.services.groupe.groupe import specialises_de
        from api.services.groupe.passations import agent_principal_de

        depart = await lire_workflow(depart_id, organization_id)
        if depart is None:
            return []
        principal_id = agent_principal_de(getattr(depart, "workflow_configurations", None)) or depart_id
        principal = depart if principal_id == depart_id else await lire_workflow(principal_id, organization_id)
        ids = [principal_id, *specialises_de(getattr(principal, "workflow_configurations", None))]
        if depart_id not in ids:
            ids.append(depart_id)
        uuids: list[str] = []
        for i in dict.fromkeys(ids):
            if i == depart_id:
                workflow = depart
            elif i == principal_id:
                workflow = principal
            else:
                workflow = await lire_workflow(i, organization_id)
            if workflow is not None:
                uuids += _uuids_d_une_definition(workflow)
        return list(dict.fromkeys(uuids))
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[issue] outils du groupe non lus : {erreur!r}")
        return []


async def issues_reservees_du_groupe(
    depart_id: int | None,
    organization_id: int | None,
    lire_workflow: Callable[[int, int], Awaitable[Any]],
    lire_outils: Callable[[list[str], int], Awaitable[Iterable[Any]]],
) -> set[str]:
    """Les issues réservées par tout outil de transfert d'appel du groupe (téléphone et clavier : ce seul chemin)."""
    uuids = await uuids_des_outils_du_groupe(depart_id, organization_id, lire_workflow)
    return await issues_reservees(uuids, organization_id, lire_outils)
