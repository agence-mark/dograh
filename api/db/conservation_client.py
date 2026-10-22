"""[.mark] Where the retention of a call's copies reads and empties (chantier cloture-code-avant-migration, lot 6).

The nightly purge (``services/conservation_appels/purge.py``) works run by run, always scoped to ONE
organization through the run's agent (``workflow_runs`` -> ``workflows.organization_id``): another
organization's run is never read nor emptied. No migration: the markers of what was done live in the run's
``extra`` (``extra["conservation"] = {"texte": <iso>, "audio": <iso>}``), a technical column the purge keeps.

What is emptied (the plan, lot 6): everything that carries the text of the conversation -- ``logs``,
``initial_context``, ``gathered_context`` (the trace and ``tool_results`` with it), ``annotations``, the
transcript's address, the text session's ``session_data`` and ``checkpoint``, the payload of the webhook
deliveries already sent. What stays: the run's row (cost, duration, state) and ``extra``.
"""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select, update

from api.db.base_client import BaseDBClient
from api.db.models import (
    OrganizationModel,
    WebhookDeliveryModel,
    WorkflowModel,
    WorkflowRunModel,
    WorkflowRunTextSessionModel,
)

CLE_MARQUEUR = "conservation"


class ConservationClient(BaseDBClient):
    async def lister_ids_organisations(self) -> list[int]:
        async with self.async_session() as session:
            resultat = await session.execute(select(OrganizationModel.id).order_by(OrganizationModel.id))
            return [ligne[0] for ligne in resultat.all()]

    async def lister_runs_a_purger(
        self,
        organization_id: int,
        *,
        avant: datetime,
        partie: str,
        apres_id: int = 0,
        limite: int = 200,
    ) -> list[dict[str, Any]]:
        """The runs of the organization older than ``avant`` whose ``partie`` ("texte" or "audio") was not
        emptied yet, by increasing id, after ``apres_id``. Only what the purge needs is read."""
        requete = (
            select(
                WorkflowRunModel.id,
                WorkflowRunModel.transcript_url,
                WorkflowRunModel.recording_url,
                WorkflowRunModel.storage_backend,
                WorkflowRunModel.extra,
            )
            .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
            .where(
                WorkflowModel.organization_id == organization_id,
                WorkflowRunModel.created_at < avant,
                WorkflowRunModel.id > apres_id,
                WorkflowRunModel.extra[CLE_MARQUEUR][partie].as_string().is_(None),
            )
            .order_by(WorkflowRunModel.id)
            .limit(limite)
        )
        if partie == "audio":
            requete = requete.where(
                or_(
                    WorkflowRunModel.recording_url.isnot(None),
                    WorkflowRunModel.extra["recordings"].as_string().isnot(None),
                )
            )
        async with self.async_session() as session:
            resultat = await session.execute(requete)
            return [
                {
                    "id": ligne.id,
                    "transcript_url": ligne.transcript_url,
                    "recording_url": ligne.recording_url,
                    "storage_backend": getattr(ligne.storage_backend, "value", ligne.storage_backend),
                    "extra": ligne.extra or {},
                }
                for ligne in resultat.all()
            ]

    async def vider_les_copies_texte(self, run_id: int, organization_id: int, quand: str) -> bool:
        """Empty what carries the text of the conversation, keep the rest. False: not this organization's run."""
        async with self.async_session() as session:
            resultat = await session.execute(
                select(WorkflowRunModel)
                .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
                .where(WorkflowRunModel.id == run_id, WorkflowModel.organization_id == organization_id)
                .with_for_update(of=WorkflowRunModel)
            )
            run = resultat.scalars().first()
            if run is None:
                return False
            run.logs = {}
            run.initial_context = {}
            run.gathered_context = {}
            run.annotations = {}
            run.transcript_url = None
            run.extra = _avec_marqueur(run.extra, "texte", quand)
            await session.execute(
                update(WorkflowRunTextSessionModel)
                .where(WorkflowRunTextSessionModel.workflow_run_id == run_id)
                .values(session_data={}, checkpoint={})
            )
            # A delivery still pending is sent from its payload: only the ones already settled are emptied.
            await session.execute(
                update(WebhookDeliveryModel)
                .where(WebhookDeliveryModel.workflow_run_id == run_id, WebhookDeliveryModel.status != "pending")
                .values(payload={})
            )
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            return True

    async def marquer_audio_supprime(self, run_id: int, organization_id: int, quand: str) -> bool:
        """The audio files of the run are gone from storage: forget their addresses."""
        async with self.async_session() as session:
            resultat = await session.execute(
                select(WorkflowRunModel)
                .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
                .where(WorkflowRunModel.id == run_id, WorkflowModel.organization_id == organization_id)
                .with_for_update(of=WorkflowRunModel)
            )
            run = resultat.scalars().first()
            if run is None:
                return False
            run.recording_url = None
            extra = _avec_marqueur(run.extra, "audio", quand)
            extra.pop("recordings", None)
            run.extra = extra
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            return True


def _avec_marqueur(extra: dict | None, partie: str, quand: str) -> dict:
    """A new dict (the JSON column does not track an in-place change) with the marker of ``partie`` set."""
    nouveau = copy.deepcopy(dict(extra or {}))
    marqueur = dict(nouveau.get(CLE_MARQUEUR) or {})
    marqueur[partie] = quand
    nouveau[CLE_MARQUEUR] = marqueur
    return nouveau
