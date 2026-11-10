"""[.mark] Clôture, lot B (D7) : sur un agent dont la version en ligne est protégée, les corrections en un clic et les modèles de réglages passent par
une copie de travail (une branche), sans exception.

``sur_une_branche_si_protegee`` : si la principale de l'agent est protégée et qu'aucune branche n'est ouverte par la requête, une branche « Correction … »
est créée depuis la version en ligne, ouverte pour la durée du geste (le geste écrit alors le brouillon de la personne sur cette branche), puis la requête
retrouve la principale. La branche se relit, se teste et se fusionne comme toute branche. Hors protection, ou si la personne est déjà sur une branche, rien
ne change (``None``). Un nom de branche pris se décale (« … 2 », « … 3 »).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from loguru import logger

from api.db import branche_ouverte, db_client
from api.services.branches import service
from api.services.branches.service import ErreurDeBranche

ESSAIS_DE_NOM = 20


@asynccontextmanager
async def sur_une_branche_si_protegee(organization_id: int, agent: Any, user: Any, sujet: str) -> AsyncIterator[dict[str, Any] | None]:
    if branche_ouverte.courante().branch_id is not None:
        yield None
        return
    protegee, _ = await db_client.protection_de_la_principale(organization_id, agent.id)
    if not protegee:
        yield None
        return
    base = service.nom_valide(f"Correction {sujet}"[:50])
    creee: dict[str, Any] | None = None
    for numero in range(1, ESSAIS_DE_NOM + 1):
        nom = base if numero == 1 else f"{base} {numero}"
        try:
            creee = await service.creer(organization_id, agent, nom, depuis_version=None, user_id=getattr(user, "id", None), protegee=False)
            break
        except ErreurDeBranche as erreur:
            if erreur.code != "nom_pris":
                raise
    if creee is None:
        raise ErreurDeBranche("A branch name for this fix could not be found", "nom_pris")
    avant = branche_ouverte.courante()
    branche_ouverte.ouvrir(creee["id"], getattr(user, "id", None))
    try:
        yield {"id": creee["id"], "nom": creee["nom"]}
    except Exception:
        # SA-9 (7) : la correction a échoué APRÈS la création de la copie de travail : on ne laisse pas une branche « Correction … » orpheline.
        branche_ouverte.ouvrir(avant.branch_id, avant.user_id)
        try:
            await db_client.archiver_une_branche_ouverte_en_vain(organization_id, agent.id, creee["id"])
        except Exception as erreur:  # noqa: BLE001 -- l'erreur d'origine reste celle qu'on relève
            logger.warning(f"[branches] branche de correction non archivée après un échec ({type(erreur).__name__})")
        raise
    finally:
        branche_ouverte.ouvrir(avant.branch_id, avant.user_id)
