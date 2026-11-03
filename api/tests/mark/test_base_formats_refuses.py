"""[.mark] Constat C9 (builder partie 2, lot 0) : la base de connaissances refuse en le disant ce qu'elle ne sait pas lire.

| Test | Ce qu'il prouve |
|---|---|
| formats | PDF, Word, Markdown, texte acceptés ; image, présentation, tableur refusés |
| route d'envoi | ``/upload-url`` refuse une image AVANT l'envoi, avec le message clair (422), sans toucher au stockage |
| tâche | un format refusé ne part jamais au service de l'éditeur (coupé) : la tâche échoue avec le message clair |
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.services.gen_ai.documents_locaux import MESSAGE_FORMAT_REFUSE, format_accepte


@pytest.mark.parametrize("nom", ["a.pdf", "a.docx", "a.md", "a.txt", "A.PDF"])
def test_les_formats_lus_sur_place_sont_acceptes(nom):
    assert format_accepte(nom, "application/octet-stream")


@pytest.mark.parametrize("nom", ["photo.png", "photo.jpg", "deck.pptx", "deck.key", "tableau.xlsx", "vieux.doc", "sans-extension"])
def test_les_autres_formats_sont_refuses(nom):
    assert not format_accepte(nom, "application/octet-stream")


async def test_la_route_d_envoi_refuse_une_image_avant_l_envoi():
    from api.routes import knowledge_base as route
    from api.schemas.knowledge_base import DocumentUploadRequestSchema

    stockage = AsyncMock()
    with patch.object(route.storage_fs, "aget_presigned_put_url", stockage):
        with pytest.raises(HTTPException) as refus:
            await route.get_upload_url(
                DocumentUploadRequestSchema(filename="photo.png", mime_type="image/png"),
                user=SimpleNamespace(id=1, selected_organization_id=7),
            )
    assert refus.value.status_code == 422 and refus.value.detail == MESSAGE_FORMAT_REFUSE
    stockage.assert_not_awaited()


async def test_la_tache_refuse_un_format_sans_appeler_le_service_de_l_editeur(monkeypatch):
    from api.tasks import knowledge_base_processing as tache

    async def telecharger(_cle, destination):
        with open(destination, "wb") as f:
            f.write(b"\x89PNG faux")
        return True

    db = MagicMock()
    for nom in ("update_document_status", "update_document_metadata", "replace_chunks_for_document", "get_document_by_hash"):
        setattr(db, nom, AsyncMock(return_value=None))
    db.get_document_by_id = AsyncMock(return_value=SimpleNamespace(organization_id=7))
    db.compute_file_hash = MagicMock(return_value="h")
    db.get_mime_type = MagicMock(return_value="image/png")
    embeddings = SimpleNamespace(embeddings=None)
    service_editeur = AsyncMock()
    with (
        patch.object(tache, "db_client", db),
        patch.object(tache.storage_fs, "adownload_file", telecharger),
        patch.object(tache.mps_service_key_client, "process_document", service_editeur),
        patch("api.services.configuration.ai_model_configuration.get_resolved_ai_model_configuration", AsyncMock(return_value=SimpleNamespace(effective=embeddings))),
        patch("api.services.cles_reference.resoudre_les_cles", AsyncMock(return_value=embeddings)),
    ):
        with pytest.raises(ValueError, match="Format not supported"):
            await tache.process_knowledge_base_document({}, 1, "org/7/photo.png", 7, "evan", retrieval_mode="chunked")
    service_editeur.assert_not_awaited()
    dernier = db.update_document_status.await_args_list[-1]
    assert dernier.args[1] == "failed" and "Format not supported" in str(dernier.kwargs.get("error_message"))
