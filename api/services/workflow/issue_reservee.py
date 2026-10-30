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
