"""[.mark] Builder, lot 6 : où vivent les tests et leurs résultats (R0-6, aucune migration).

* ``MARK_TESTS:<agent>:<test>``            le test (format ``tests_rejouables`` v1 étendu : ``criteres``, ``obligatoire``, ``dossier``,
  ``origine``, ``scenario``) ;
* ``MARK_TESTS_RESULTATS:<agent>:<test>``  les 3 dernières exécutions.

Un seul point d'accès à la base : ``builder.stock`` (les tests le remplacent par une mémoire).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

from api.services.builder import stock
from api.services.builder.constantes import PREFIXE_RESULTATS, PREFIXE_TESTS, cle_resultats, cle_test

EXECUTIONS_GARDEES = 3
VERSION = 1
ORIGINES = ("client", "recette", "code", "manuel", "fiche")
TESTS_MAX = 300
OCTETS_MAX = 60_000


class ErreurTest(Exception):
    """Un refus normal (test inconnu, trop gros, plafond), dit en une phrase."""


def maintenant() -> str:
    return datetime.now(UTC).isoformat()


def slug_de(nom: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")[:64] or "test"


async def lister(organization_id: int, workflow_id: int) -> list[dict[str, Any]]:
    """Les tests de l'agent, dans l'ordre des noms."""
    prefixe = f"{PREFIXE_TESTS}{workflow_id}:"
    return [valeur for _cle, valeur in await stock.lister(organization_id, prefixe)]


async def lire(organization_id: int, workflow_id: int, slug: str) -> dict[str, Any]:
    test = await stock.lire(organization_id, cle_test(workflow_id, slug))
    if test is None:
        raise ErreurTest(f"Unknown test: {slug}.")
    return test


async def ecrire(organization_id: int, workflow_id: int, test: dict[str, Any]) -> dict[str, Any]:
    import json

    if len(json.dumps(test, ensure_ascii=False).encode("utf-8")) > OCTETS_MAX:
        raise ErreurTest("The test is too large to keep.")
    if test.get("origine") not in ORIGINES:
        raise ErreurTest(f"Unknown origin (expected: {', '.join(ORIGINES)}).")
    existe = await stock.lire(organization_id, cle_test(workflow_id, test["slug"]))
    if existe is None and len(await lister(organization_id, workflow_id)) >= TESTS_MAX:
        raise ErreurTest(f"At most {TESTS_MAX} tests per agent.")
    await stock.ecrire(organization_id, cle_test(workflow_id, test["slug"]), test)
    return test


async def supprimer(organization_id: int, workflow_id: int, slug: str) -> bool:
    await stock.supprimer(organization_id, cle_resultats(workflow_id, slug))
    return await stock.supprimer(organization_id, cle_test(workflow_id, slug))


async def changer(organization_id: int, workflow_id: int, slug: str, **champs: Any) -> dict[str, Any]:
    """Change ``obligatoire`` et/ou ``dossier`` d'un test existant (le reste d'un test ne se réécrit pas)."""
    for cle in champs:
        if cle not in ("obligatoire", "dossier"):
            raise ErreurTest(f"« {cle} » cannot be changed on an existing test.")

    def transformer(test):
        if test is None:
            raise ErreurTest(f"Unknown test: {slug}.")
        return {**test, **{cle: valeur for cle, valeur in champs.items() if valeur is not None}}

    # Revue R6 : deux changements simultanés (« obligatoire » et « dossier ») ne s'écrasent pas.
    return await stock.modifier(organization_id, cle_test(workflow_id, slug), transformer) or {}


async def resultats(organization_id: int, workflow_id: int, slug: str) -> list[dict[str, Any]]:
    ligne = await stock.lire(organization_id, cle_resultats(workflow_id, slug)) or {}
    return list(ligne.get("executions") or [])


async def ajouter_un_resultat(organization_id: int, workflow_id: int, slug: str, execution: dict[str, Any]) -> None:
    """Range une exécution en tête ; seules les 3 dernières restent."""
    await stock.modifier(
        organization_id,
        cle_resultats(workflow_id, slug),
        lambda ligne: {"executions": [execution, *list((ligne or {}).get("executions") or [])][:EXECUTIONS_GARDEES]},
    )


async def derniere_execution(organization_id: int, workflow_id: int, slug: str) -> dict[str, Any] | None:
    executions = await resultats(organization_id, workflow_id, slug)
    return executions[0] if executions else None


def prefixe_des_resultats(workflow_id: int) -> str:
    return f"{PREFIXE_RESULTATS}{workflow_id}:"
