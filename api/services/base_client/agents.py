"""[.mark] Chantier agents-specialises, lot 8 : la base du client sait quel agent sert quel établissement.

``agent_site`` est remplie DEPUIS Dograh, qui reste la seule vérité (M3, M9) : à la publication d'un agent
(ce que les appels lisent), à la reprise des fiches, et au rattachement d'un agent au portail. Jamais le
contraire : rien ici ne lit ``agent_site`` pour décider quoi que ce soit dans un appel.

Sans base du client rattachée, ou base injoignable, ou base en version 14 : rien n'est écrit, et le
geste d'origine (publier, reprendre) n'en est jamais gêné. ⛔ Ne lève jamais.
"""

from __future__ import annotations

from loguru import logger

from api.db.bases_clients.connexion import BaseClientIndisponible, connecter
from api.services.base_client.rattachement import nom_de_la_base


async def synchroniser_agent_site(
    organization_id: int | None,
    workflow_id: int,
    nom: str | None,
    etablissement_id: str | None,
) -> bool:
    """Écrit dans la base du client de CETTE organisation le choix de fiche d'un agent. ``True`` : écrit."""
    if organization_id is None:
        return False
    try:
        base = await nom_de_la_base(organization_id)
        if not base:
            return False
        from api.db.bases_clients.traces import ecrire_agent_site

        connexion = await connecter(base)
        try:
            return await ecrire_agent_site(
                connexion,
                dograh_workflow_id=workflow_id,
                nom=nom,
                site_cle=etablissement_id or None,
            )
        finally:
            await connexion.close()
    except BaseClientIndisponible as erreur:
        logger.warning(f"[.mark] agent_site of agent {workflow_id} not written: {erreur}")
    except Exception as erreur:  # noqa: BLE001 -- jamais une raison de rater une publication
        logger.warning(f"[.mark] agent_site of agent {workflow_id} not written ({type(erreur).__name__}): {erreur}")
    return False
