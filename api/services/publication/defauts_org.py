"""[.mark] Builder partie 3, sous-lot 3 (SE-12 / D-1) : les réglages de publication PAR DÉFAUT de l'organisation (thème « Publication »).

Une ligne de ``organization_configurations`` (``MARK_PUBLICATION_DEFAUT``) qui a la forme des réglages d'un agent (``Publication``) :
l'interrupteur du déploiement progressif (ÉTEINT par défaut) et la position de chaque contrôle. Un agent qui a ses propres
réglages (clé ``publication`` de son brouillon) les garde ; sinon il reçoit ceux de l'organisation, puis ceux du code (la garde
d'avant). Les réglages de l'organisation sont recopiés dans le brouillon À LA PUBLICATION : la lecture à la création d'un appel
(``deploiement_actif``) reste celle d'un dictionnaire déjà en mémoire, jamais une lecture de plus par appel.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.schemas.publication import Publication
from api.services.builder import stock
from api.services.publication import reglages

CLE = "MARK_PUBLICATION_DEFAUT"


async def lire(organisation_id: int) -> Publication | None:
    """Les défauts de l'organisation, ou ``None`` (aucun écrit, ou ligne illisible : les défauts du code)."""
    try:
        ligne = await stock.lire(organisation_id, CLE)
        return Publication.model_validate(ligne) if ligne else None
    except Exception as erreur:  # noqa: BLE001 -- une ligne illisible ne bloque jamais une publication
        logger.warning(f"[publication] défauts de l'organisation illisibles ({type(erreur).__name__})")
        return None


async def ecrire(organisation_id: int, publication: Publication) -> None:
    await stock.ecrire(organisation_id, CLE, publication.model_dump())


async def effectives(organisation_id: int, configurations: dict[str, Any] | None) -> dict[str, Any]:
    """Les réglages d'un agent, ``publication`` complétée par celle de l'organisation quand l'agent n'a pas la sienne."""
    resultat = dict(configurations or {})
    if isinstance(resultat.get(reglages.CLE), dict):
        return resultat
    defauts = await lire(organisation_id)
    if defauts is not None:
        resultat[reglages.CLE] = defauts.model_dump()
    return resultat
