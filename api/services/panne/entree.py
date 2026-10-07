"""[.mark] What follows the stream in the inbound instruction (L7, PN5, constat C1).

Twilio runs the verb after ``<Connect>`` only when the stream drops WITHOUT a hang-up: a normal
end and a transfer hang up or redirect through the API first (F2, F4, rechecked on this branch).
So that verb is reached exactly when our server died in the middle of the call. Today it is
``<Pause length="40"/>``: 40 s of silence. For an agent that switched the fallback on, with an
emergency address set for its organization, it becomes a ``<Redirect>`` to the TwiML Bin, the
second number of the establishment the caller dialled in its address.

⛔ Never raises; anything missing or unreadable gives the pause of before, word for word.
"""

from __future__ import annotations

from loguru import logger

PAUSE = '<Pause length="40"/>'


async def apres_le_flux(workflow_run_id: int | None) -> str:
    if not workflow_run_id:
        return PAUSE
    try:
        from api.db import db_client
        from api.schemas.panne import panne_de_lagent
        from api.services.etablissements.appel import etablissement_de_lappel
        from api.services.panne import consigne
        from api.services.panne.routes import lire_reglages

        run = await db_client.get_workflow_run_by_id(workflow_run_id)
        configurations = (
            getattr(getattr(run, "definition", None), "workflow_configurations", None)
            or {}
        )
        if run is None or not panne_de_lagent(configurations).actif:
            return PAUSE
        workflow = await db_client.get_workflow_by_id(run.workflow_id)
        organization_id = getattr(workflow, "organization_id", None)
        if organization_id is None:
            return PAUSE
        reglages = await lire_reglages(organization_id)
        if not (reglages.url_secours or reglages.url_secours_promesse):
            return PAUSE
        servi = await etablissement_de_lappel(
            organization_id, run.workflow_id, dict(run.initial_context or {})
        )
        numero = (
            getattr(getattr(servi, "etablissement", None), "second_numero", None)
            or None
        )
        adresse, numero = consigne.bin_de_secours(
            reglages.url_secours, reglages.url_secours_promesse, numero
        )
        return consigne.redirection_de_secours(adresse, numero)
    except Exception as erreur:  # noqa: BLE001 -- the call must be answered
        logger.warning(
            f"[.mark] Emergency instruction not built, the 40 s pause stays: {erreur!r}"
        )
        return PAUSE
