"""[.mark] U3 sexies point 5 : la lecture des appels d'outils pour les statistiques.

Un module à part, mélangé à ``DBClient`` par une ligne. Aucune table : les appels d'outils sont lus dans les
événements du journal de chaque appel (``logs.realtime_feedback_events``), pour UNE organisation et une fenêtre bornée.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from api.db.base_client import BaseDBClient
from api.db.models import WorkflowModel, WorkflowRunModel

TYPES_LUS = ("rtf-function-call-start", "rtf-function-call-end")


class OutilsMarkClient(BaseDBClient):
    async def evenements_d_outils(
        self, organization_id: int, *, jours: int = 30, limite: int = 2000
    ) -> list[dict[str, Any]]:
        """Pour les ``limite`` appels les plus récents des ``jours`` derniers jours de l'organisation :
        ``{run_id, workflow_id, created_at, evenements}`` où ``evenements`` ne garde que début et fin d'appel d'outil."""
        depuis = datetime.now(UTC) - timedelta(days=jours)
        async with self.async_session() as session:
            lignes = await session.execute(
                select(
                    WorkflowRunModel.id,
                    WorkflowRunModel.workflow_id,
                    WorkflowRunModel.created_at,
                    WorkflowRunModel.logs,
                )
                .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
                .where(
                    WorkflowModel.organization_id == organization_id,
                    WorkflowRunModel.created_at >= depuis,
                )
                .order_by(WorkflowRunModel.id.desc())
                .limit(limite)
            )
            sortie = []
            for run_id, workflow_id, cree, logs in lignes.all():
                evenements = [
                    e
                    for e in ((logs or {}).get("realtime_feedback_events") or [])
                    if isinstance(e, dict) and e.get("type") in TYPES_LUS
                ]
                if evenements:
                    sortie.append(
                        {"run_id": run_id, "workflow_id": workflow_id, "created_at": cree, "evenements": evenements}
                    )
            return sortie
