"""[.mark] U3 sexies point 6 : les serveurs MCP.

R9 (Pipecat d'abord) : le ``MCPClient`` de Pipecat sait déjà le transport SSE (``SseServerParameters``), les en-têtes
et les délais ; rien n'est réécrit, seuls les paramètres sont construits ici et dans ``mcp_tool_session``.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.services.outils_mark import en_tetes as en_tetes_mark
from api.services.workflow.mcp_tool_session import discover_mcp_tools


async def entetes_du_serveur(cfg: dict[str, Any], organization_id: int | None) -> dict[str, str]:
    """Les en-têtes libres du serveur, secrets lus dans les identifiants de l'organisation."""
    entetes, _ = await en_tetes_mark.resoudre(cfg.get("en_tetes_ext"), {}, organization_id)
    return entetes


def filtre_effectif(cfg: dict[str, Any], config_brute: dict[str, Any]) -> list[str]:
    """``tools_filter`` du serveur, où un outil désactivé n'entre jamais.

    * liste d'autorisés écrite : on en retire les désactivés ;
    * liste vide et catalogue connu : tout le catalogue moins les désactivés ;
    * liste vide et catalogue inconnu : vide (le refus des désactivés est alors fait par la session, au moment de
      proposer les outils au modèle)."""
    desactives = {n for n, r in (cfg.get("reglages_outils") or {}).items() if r == "desactive"}
    filtre = list(cfg.get("tools_filter") or [])
    if not desactives:
        return filtre
    if filtre:
        return [n for n in filtre if n not in desactives]
    connus = [d.get("name") for d in (config_brute.get("discovered_tools") or []) if isinstance(d, dict) and d.get("name")]
    return [n for n in connus if n not in desactives]


async def tester_la_connexion(
    *,
    url: str,
    transport: str,
    timeout_secs: int,
    sse_read_timeout_secs: int,
    credential: Any,
    entrees_en_tetes: list[dict[str, Any]],
    organization_id: int,
) -> dict[str, Any]:
    """Découvre les outils du serveur. Jamais d'exception : ``{"ok": bool, "outils": [...], "erreur": str | None}``."""
    try:
        entetes, _ = await en_tetes_mark.resoudre(entrees_en_tetes, {}, organization_id)
        outils = await discover_mcp_tools(
            url=url,
            credential=credential,
            timeout_secs=timeout_secs,
            sse_read_timeout_secs=sse_read_timeout_secs,
            transport=transport,
            extra_headers=entetes or None,
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[outils] test de connexion MCP en échec : {type(erreur).__name__}")
        # Message générique : le nom de la classe d'erreur dit trop de la machine et du réseau (revue serveur, mineur 1).
        return {"ok": False, "outils": [], "erreur": "Connection failed."}
    if not outils:
        return {"ok": False, "outils": [], "erreur": "The server did not answer, or exposes no tool."}
    return {"ok": True, "outils": outils, "erreur": None}
