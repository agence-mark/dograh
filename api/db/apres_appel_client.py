"""[.mark] Where a run's after-call steps are recorded (chantier l-agent-travaille, L4, A9).

The steps of a run (write, summary, mails, modules) run as separate jobs that may
finish together: each one merges ITS step into ``annotations["mark_apres_appel"]``
under a row lock, so two steps never erase each other (``update_workflow_run``
merges the top-level keys only). No migration: ``annotations`` is an existing JSON
column of the run.
"""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import select, text

from api.db.base_client import BaseDBClient
from api.db.models import WorkflowRunModel

CLE_ANNOTATION = "mark_apres_appel"


class ApresAppelClient(BaseDBClient):
    async def fusionner_apres_appel(
        self,
        run_id: int,
        *,
        etape: str | None = None,
        valeur: dict[str, Any] | None = None,
        racine: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Merge ``valeur`` into the step ``etape`` (and ``racine`` into the block itself),
        under ``SELECT … FOR UPDATE``. Returns the block as stored."""
        async with self.async_session() as session:
            result = await session.execute(
                select(WorkflowRunModel)
                .where(WorkflowRunModel.id == run_id)
                .with_for_update()
            )
            run = result.scalars().first()
            if run is None:
                raise ValueError(f"Workflow run with ID {run_id} not found")
            annotations = copy.deepcopy(run.annotations or {})
            bloc = dict(annotations.get(CLE_ANNOTATION) or {})
            if racine:
                bloc.update(racine)
            if etape is not None:
                etapes = dict(bloc.get("etapes") or {})
                etapes[etape] = {**(etapes.get(etape) or {}), **(valeur or {})}
                bloc["etapes"] = etapes
            annotations[CLE_ANNOTATION] = bloc
            run.annotations = annotations
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            return bloc

    async def lire_apres_appel(self, run_id: int) -> dict[str, Any]:
        async with self.async_session() as session:
            result = await session.execute(
                select(WorkflowRunModel.annotations).where(
                    WorkflowRunModel.id == run_id
                )
            )
            annotations = result.scalar_one_or_none() or {}
            return dict(annotations.get(CLE_ANNOTATION) or {})

    async def compter_sms(self, workflow_id: int) -> int:
        """L6, D9: the SMS sent by this agent's calls (the caller checks the organization)."""
        async with self.async_session() as session:
            total = await session.execute(
                text(
                    "SELECT COALESCE(SUM(jsonb_array_length("
                    "COALESCE(annotations::jsonb #> '{mark_apres_appel,etapes,module:sms,envoyes}', '[]'::jsonb)"
                    ")), 0) FROM workflow_runs WHERE workflow_id = :w "
                    "AND annotations::jsonb #> '{mark_apres_appel,etapes,module:sms,envoyes}' IS NOT NULL"
                ),
                {"w": workflow_id},
            )
            return int(total.scalar_one() or 0)

    async def derniere_fiche(self, workflow_id: int) -> tuple[int | None, dict[str, Any]]:
        """L6: the record of this agent's last call that holds one (the SMS preview)."""
        async with self.async_session() as session:
            result = await session.execute(
                select(WorkflowRunModel.id, WorkflowRunModel.gathered_context)
                .where(WorkflowRunModel.workflow_id == workflow_id)
                .order_by(WorkflowRunModel.id.desc())
                .limit(50)
            )
            for run_id, contexte in result.all():
                fiche = (contexte or {}).get("extracted_variables") or {}
                if isinstance(fiche, dict) and fiche:
                    return run_id, fiche
            return None, {}
