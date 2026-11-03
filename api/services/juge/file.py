"""[.mark] La file « À juger » et le réglage « juge des vrais appels » par agent (J3).

Deux lignes de ``organization_configurations`` (aucune migration) :

* ``MARK_JUGE_AGENT:<agent>`` : ``{"actif": bool}``, le réglage de l'agent (éteint par défaut) ;
* ``MARK_JUGE_FILE`` : les éléments à juger, bornés (``FILE_MAX``). Un élément est un vrai appel (``type: appel``, la transcription est
  relue dans le run) ou un test (``type: test``, ses lignes et ses propres questions sont gardées dans l'élément).

La file ne sert qu'à la source Claude Code : sur clé d'API, l'appel est jugé tout de suite.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from api.services.builder import stock

CLE_FILE = "MARK_JUGE_FILE"
PREFIXE_AGENT = "MARK_JUGE_AGENT:"
PREFIXE_VERDICT_TEST = "MARK_JUGE_TEST:"
FILE_MAX = 100
LIGNES_MAX = 40
LIGNE_MAX_CAR = 400


def cle_agent(workflow_id: int) -> str:
    return f"{PREFIXE_AGENT}{workflow_id}"


def maintenant() -> str:
    return datetime.now(UTC).isoformat()


async def juge_des_vrais_appels(organisation: int, workflow_id: int) -> bool:
    return bool((await stock.lire(organisation, cle_agent(workflow_id)) or {}).get("actif"))


async def regler(organisation: int, workflow_id: int, actif: bool) -> bool:
    await stock.ecrire(organisation, cle_agent(workflow_id), {"actif": bool(actif)})
    return bool(actif)


async def lister(organisation: int, workflow_id: int | None = None) -> list[dict[str, Any]]:
    items = list((await stock.lire(organisation, CLE_FILE) or {}).get("items") or [])
    return [i for i in items if workflow_id is None or i.get("workflow_id") == workflow_id]


async def trouver(organisation: int, identifiant: str) -> dict[str, Any] | None:
    return next((i for i in await lister(organisation) if i.get("id") == identifiant), None)


async def ajouter(organisation: int, item: dict[str, Any]) -> None:
    """Un élément par identifiant : le re-poser remplace l'ancien (un test rejoué n'encombre pas la file)."""

    def transformer(ligne):
        items = [i for i in (ligne or {}).get("items") or [] if i.get("id") != item["id"]]
        return {"items": [*items, {**item, "le": item.get("le") or maintenant()}][-FILE_MAX:]}

    await stock.modifier(organisation, CLE_FILE, transformer)


async def retirer(organisation: int, identifiant: str) -> None:
    def transformer(ligne):
        items = (ligne or {}).get("items") or []
        reste = [i for i in items if i.get("id") != identifiant]
        return {"items": reste} if len(reste) != len(items) else None

    await stock.modifier(organisation, CLE_FILE, transformer)


def lignes_compactes(lignes: list[tuple[str, str]]) -> list[list[str]]:
    return [[r, t[:LIGNE_MAX_CAR]] for r, t in lignes[:LIGNES_MAX]]
