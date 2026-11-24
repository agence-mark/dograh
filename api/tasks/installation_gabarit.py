"""[.mark] Chantier Partie 1, lot 4 (n° 141) : l'installation d'un restaurant depuis le gabarit, en tâche de fond.

La route répond tout de suite (l'identifiant de l'installation) ; le travail est dans ``services/gabarits/installation.py`` (``installer_un_restaurant``), qui
reprend où l'installation s'était arrêtée : les étapes closes sont sautées, l'étape 6 est reprise par son bail. Rejouée, la tâche ne refait rien de fait.
"""

from __future__ import annotations

from typing import Any

from arq import Retry
from loguru import logger

from api.db import db_client
from api.services.gabarits.installation import installer_un_restaurant
from api.services.installation_client.moteur import RefusInstallation

ATTENTE_D_UNE_AUTRE_TENTATIVE_S = 60


async def installer_un_restaurant_en_tache(ctx: Any, installation_id: int, user_id: int, formulaire: dict[str, Any], nom_base: str) -> None:
    """L'organisation est celle de l'installation, relue en base ici (jamais celle d'un argument ni du formulaire) ; l'utilisateur doit en être encore membre."""
    installation = await db_client.installation_a_reprendre(installation_id)
    if installation is None or installation["etat"] != "ouverte":
        logger.warning(f"[.mark] Restaurant installation {installation_id} is gone or closed: nothing to resume")
        return
    organization_id = installation["organization_id"]
    user = await db_client.get_user_by_id(user_id)
    membres = {m.id for m in await db_client.get_organization_users(organization_id)}
    if user is None or user.id not in membres:
        logger.error(f"[.mark] Restaurant installation {installation_id}: the user {user_id} is no longer a member of organization {organization_id}")
        return
    user.selected_organization_id = organization_id
    try:
        resultat = await installer_un_restaurant(user, organization_id, formulaire, nom_base=nom_base)
    except RefusInstallation as refus:
        if refus.code == "en_cours":  # une autre tentative tient encore l'étape : on reprend plus tard, sans rien refaire
            raise Retry(defer=ATTENTE_D_UNE_AUTRE_TENTATIVE_S) from None
        raise
    if resultat["echec"] is not None:
        logger.warning(f"[.mark] Restaurant installation of organization {organization_id} stopped at step {resultat['echec'].get('etape')}: {resultat['echec'].get('code')}")
