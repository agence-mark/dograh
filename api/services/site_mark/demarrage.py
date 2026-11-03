"""[.mark] S1 : ce que /init écrit sur le run d'une session de widget, et ce que le pipeline en lit.

``/init`` pose sur le run une annotation ``embed`` : la source, la modalité et les réglages de la session
(durée maximale, jeton). Le pipeline la lit au démarrage pour brancher le minuteur de durée. Un run sans annotation
(téléphone, test) n'a ni minuteur ni versement de minutes.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

CLE_ANNOTATION = "embed"
SOURCE_WIDGET = "embed_widget"


def annotation_du_widget(modalite: str, embed_token_id: int, duree_max_s: int) -> dict[str, Any]:
    return {
        "source": SOURCE_WIDGET,
        "modality": modalite,
        "embed_token_id": embed_token_id,
        "duree_max_s": duree_max_s,
    }


def lancer_la_duree_du_widget(engine, workflow_run, organization_id: int | None = None):
    """Branche le minuteur sur le run d'une session de voix du widget ; ``None`` pour tout autre appel."""
    annotations = getattr(workflow_run, "annotations", None) or {}
    embed = annotations.get(CLE_ANNOTATION) if isinstance(annotations, dict) else None
    if not isinstance(embed, dict) or embed.get("source") != SOURCE_WIDGET:
        return None
    duree = embed.get("duree_max_s")
    jeton = embed.get("embed_token_id")
    if not isinstance(duree, int) or isinstance(duree, bool) or duree <= 0:
        return None
    try:
        from api.services.site_mark import plafond
        from api.services.site_mark.duree_max import lancer_pour_moteur

        async def verser(secondes: int) -> None:
            if isinstance(jeton, int):
                await plafond.verser_la_duree(jeton, secondes)

        return lancer_pour_moteur(engine, duree, a_la_fin=verser)
    except Exception:  # noqa: BLE001 -- jamais une raison de ne pas prendre l'appel
        logger.exception("[.mark] Public widget duration timer not started")
        return None
