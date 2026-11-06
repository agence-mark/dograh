"""[.mark] Copier un agent d'une organisation à une autre (U2 quinquies) : les lectures et écritures qui franchissent deux organisations.

Chaque méthode nomme les DEUX organisations et filtre par chacune : la source ne se lit que sous la source, la copie ne s'écrit que
sous la cible. Aucun secret ne passe ici.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import select

from api.db.base_client import BaseDBClient
from api.db.models import KnowledgeBaseChunkModel, KnowledgeBaseDocumentModel, WorkflowRecordingModel


class CopieAgentClient(BaseDBClient):
    async def copier_un_document(
        self, document_uuid: str, source_org: int, cible_org: int, user_id: int
    ) -> Optional[KnowledgeBaseDocumentModel]:
        """Le document (ligne, texte entier, fragments et vecteurs) copié sous la cible, avec un identifiant neuf.

        Le fichier d'origine n'est pas recopié : seul ce que l'agent lit à l'appel (texte et fragments) voyage. ``None`` si le
        document n'est pas, ou plus, prêt sous la source.
        """
        async with self.async_session() as session:
            origine = (
                await session.execute(
                    select(KnowledgeBaseDocumentModel).where(
                        KnowledgeBaseDocumentModel.document_uuid == document_uuid,
                        KnowledgeBaseDocumentModel.organization_id == source_org,
                        KnowledgeBaseDocumentModel.is_active.is_(True),
                        KnowledgeBaseDocumentModel.processing_status == "completed",
                    )
                )
            ).scalar_one_or_none()
            if origine is None:
                return None
            copie = KnowledgeBaseDocumentModel(
                document_uuid=str(uuid.uuid4()),
                organization_id=cible_org,
                filename=origine.filename,
                file_size_bytes=origine.file_size_bytes,
                file_hash=origine.file_hash,
                mime_type=origine.mime_type,
                retrieval_mode=origine.retrieval_mode,
                full_text=origine.full_text,
                source_url=origine.source_url,
                total_chunks=origine.total_chunks,
                processing_status="completed",
                docling_metadata=dict(origine.docling_metadata or {}),
                custom_metadata=dict(origine.custom_metadata or {}),
                created_by=user_id,
                is_active=True,
            )
            session.add(copie)
            await session.flush()
            fragments = (
                await session.execute(
                    select(KnowledgeBaseChunkModel)
                    .where(
                        KnowledgeBaseChunkModel.document_id == origine.id,
                        KnowledgeBaseChunkModel.organization_id == source_org,
                    )
                    .order_by(KnowledgeBaseChunkModel.chunk_index)
                )
            ).scalars().all()
            for f in fragments:
                session.add(
                    KnowledgeBaseChunkModel(
                        document_id=copie.id,
                        organization_id=cible_org,
                        chunk_text=f.chunk_text,
                        contextualized_text=f.contextualized_text,
                        chunk_index=f.chunk_index,
                        chunk_metadata=dict(f.chunk_metadata or {}),
                        embedding_model=f.embedding_model,
                        embedding_dimension=f.embedding_dimension,
                        embedding=f.embedding,
                        token_count=f.token_count,
                    )
                )
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            await session.refresh(copie)
            return copie

    async def copier_un_enregistrement(
        self, recording_id: str, source_org: int, cible_org: int, user_id: int, storage_key: str
    ) -> Optional[WorkflowRecordingModel]:
        """La ligne de l'enregistrement sous la cible, avec la clé de stockage donnée (le fichier est copié par l'appelant)."""
        async with self.async_session() as session:
            origine = (
                await session.execute(
                    select(WorkflowRecordingModel).where(
                        WorkflowRecordingModel.recording_id == recording_id,
                        WorkflowRecordingModel.organization_id == source_org,
                        WorkflowRecordingModel.is_active.is_(True),
                    )
                )
            ).scalar_one_or_none()
            if origine is None:
                return None
            copie = WorkflowRecordingModel(
                recording_id=origine.recording_id,
                workflow_id=None,
                organization_id=cible_org,
                tts_provider=origine.tts_provider,
                tts_model=origine.tts_model,
                tts_voice_id=origine.tts_voice_id,
                transcript=origine.transcript,
                storage_key=storage_key,
                storage_backend=origine.storage_backend,
                recording_metadata=dict(origine.recording_metadata or {}),
                created_by=user_id,
                created_at=datetime.now(UTC),
            )
            session.add(copie)
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            await session.refresh(copie)
            return copie

    async def adresse_de_stockage_d_un_enregistrement(self, recording_id: str, organization_id: int) -> Optional[tuple[str, str]]:
        """(clé, moteur) du fichier d'un enregistrement de CETTE organisation, ou ``None``."""
        async with self.async_session() as session:
            ligne = (
                await session.execute(
                    select(WorkflowRecordingModel.storage_key, WorkflowRecordingModel.storage_backend).where(
                        WorkflowRecordingModel.recording_id == recording_id,
                        WorkflowRecordingModel.organization_id == organization_id,
                        WorkflowRecordingModel.is_active.is_(True),
                    )
                )
            ).first()
            return (ligne[0], ligne[1]) if ligne else None
