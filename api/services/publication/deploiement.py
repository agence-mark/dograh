"""[.mark] U11 (E103) : le déploiement progressif. Construit et testé, ÉTEINT par défaut.

Éteint (réglage ``publication.deploiement.actif``) : une publication vaut pour tous les appels, aucune ligne n'est lue.
Allumé et une part en cours (ligne ``MARK_DEPLOIEMENT:<agent>``) : l'appel reçoit sa version à son début, d'après le numéro de
l'appelant. Le même numéro tombe toujours du même côté (empreinte du numéro, jamais le numéro écrit). Chaque appel porte déjà sa
version (``workflow_runs.definition_id``).

⛔ Aucune bascule ni retour en arrière automatique : « passer à 100 % » et « revenir à la vN » sont des gestes humains.
La ligne ne contient que des numéros de versions et un pourcentage, jamais de donnée personnelle.
"""

from __future__ import annotations

import hashlib
from typing import Any

from loguru import logger

from api.services.builder import stock

PREFIXE = "MARK_DEPLOIEMENT:"


class ErreurDeploiement(Exception):
    pass


def cle(workflow_id: int) -> str:
    return f"{PREFIXE}{workflow_id}"


def part_de(workflow_id: int, appelant: str | None) -> int | None:
    """La place stable (0 à 99) d'un appelant pour cet agent. ``None`` : numéro absent ou masqué (aucune place)."""
    chiffres = "".join(c for c in (appelant or "") if c.isdigit())
    if not chiffres:
        return None
    # Les 9 derniers chiffres : « +33 6 12... » et « 06 12... » sont le même appelant.
    empreinte = hashlib.sha256(f"{workflow_id}:{chiffres[-9:]}".encode()).hexdigest()
    return int(empreinte[:8], 16) % 100


def version_attribuee(ligne: dict[str, Any] | None, workflow_id: int, appelant: str | None) -> int | None:
    """Le ``definition_id`` à donner à cet appel, ou ``None`` (= la version publiée, comme sans déploiement)."""
    if not ligne:
        return None
    nouvelle, precedente = ligne.get("nouvelle"), ligne.get("precedente")
    if not isinstance(nouvelle, int) or not isinstance(precedente, int):
        return None
    pourcentage = int(ligne.get("pourcentage") or 0)
    place = part_de(workflow_id, appelant)
    if place is None:  # appelant masqué : la version qui tenait avant, jamais un tirage
        return precedente
    return nouvelle if place < pourcentage else precedente


async def lire(organization_id: int, workflow_id: int) -> dict[str, Any] | None:
    return await stock.lire(organization_id, cle(workflow_id))


async def definition_pour_l_appel(workflow: Any, appelant: str | None) -> int | None:
    """Appelé à la création d'un appel entrant. Rien à lire quand le déploiement est éteint."""
    from api.services.publication.reglages import deploiement_actif

    configurations = getattr(getattr(workflow, "released_definition", None), "workflow_configurations", None) or getattr(
        workflow, "workflow_configurations", None
    )
    if not deploiement_actif(configurations):
        return None
    try:
        ligne = await lire(workflow.organization_id, workflow.id)
    except Exception as erreur:  # noqa: BLE001 -- une panne de lecture : la version publiée, comme avant
        logger.warning(f"[publication] déploiement non lu ({type(erreur).__name__})")
        return None
    return version_attribuee(ligne, workflow.id, appelant)


async def demarrer(
    organization_id: int, workflow_id: int, nouvelle: int, precedente: int | None, pourcentage: int, par: str
) -> dict[str, Any]:
    if not 1 <= pourcentage <= 99:
        raise ErreurDeploiement("The share of calls is between 1 and 99 (100 is a normal publication).")
    if precedente is None:
        raise ErreurDeploiement("There is no earlier published version to keep the rest of the calls on.")
    ligne = {"nouvelle": nouvelle, "precedente": precedente, "pourcentage": pourcentage, "par": par}
    await stock.ecrire(organization_id, cle(workflow_id), ligne)
    return ligne


async def passer_a_100(organization_id: int, workflow_id: int) -> dict[str, Any]:
    """Un geste humain : la version publiée prend tous les appels (la ligne disparaît)."""
    return {"supprime": await stock.supprimer(organization_id, cle(workflow_id))}


async def revenir(organization_id: int, workflow_id: int, definition_id: int, numero: int | None, par: str) -> dict[str, Any]:
    """Un geste humain : tous les appels repartent sur la version ``definition_id`` (0 % à la version publiée)."""
    from api.db import db_client

    workflow = await db_client.get_workflow(workflow_id, organization_id=organization_id)
    nouvelle = getattr(getattr(workflow, "released_definition", None), "id", None)
    if not isinstance(nouvelle, int):
        raise ErreurDeploiement("No published version.")
    ligne = {"nouvelle": nouvelle, "precedente": definition_id, "pourcentage": 0, "par": par, "revenu_a": numero}
    await stock.ecrire(organization_id, cle(workflow_id), ligne)
    return ligne

