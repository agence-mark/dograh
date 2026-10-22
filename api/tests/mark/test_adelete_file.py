"""La purge de conservation supprime une copie de stockage, et une copie absente n'est pas une erreur.

Lot 6.2 de `cloture-code-avant-migration`. Une classe, un test : le fichier est posé puis
supprimé, un second appel sur un fichier absent renvoie vrai. S3 et MinIO sont joués sur un
client factice (pas de service réel dans la CI) ; le local passe par un vrai fichier.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from botocore.exceptions import ClientError
from minio.error import S3Error

from api.services.filesystem.local import LocalFileSystem
from api.services.filesystem.minio import MinioFileSystem
from api.services.filesystem.null import NullFileSystem
from api.services.filesystem.s3 import S3FileSystem


class _LocalSansLeReste(LocalFileSystem):
    """Constat (lot 6.2, à reprendre au formulaire) : `LocalFileSystem` n'est pas instanciable
    dans `b2211709` : quatre méthodes abstraites de la base n'y sont jamais implémentées, et
    aucun code ne l'instancie hors de ce test. Le test ne touche que `adelete_file`."""

    async def aget_file_metadata(self, file_path):
        raise NotImplementedError

    async def aget_presigned_put_url(self, file_path, *args, **kwargs):
        raise NotImplementedError

    async def adownload_file(self, source_path, local_path):
        raise NotImplementedError

    async def acopy_file(self, source_path, destination_path):
        raise NotImplementedError


@pytest.mark.asyncio
async def test_local_supprime_le_fichier_puis_absent_renvoie_vrai(tmp_path):
    fs = _LocalSansLeReste(str(tmp_path))
    (tmp_path / "appels").mkdir()
    (tmp_path / "appels" / "run-1.txt").write_text("texte", encoding="utf-8")

    assert await fs.adelete_file("appels/run-1.txt") is True
    assert not (tmp_path / "appels" / "run-1.txt").exists()
    assert await fs.adelete_file("appels/run-1.txt") is True


@pytest.mark.asyncio
async def test_s3_appelle_delete_object_et_erreur_renvoie_faux():
    client = SimpleNamespace(delete_object=AsyncMock(return_value={}))

    @asynccontextmanager
    async def _client(*_args, **_kwargs):
        yield client

    fs = S3FileSystem(bucket_name="mark-appels")
    fs.session = SimpleNamespace(client=_client)

    assert await fs.adelete_file("appels/run-1.txt") is True
    client.delete_object.assert_awaited_once_with(
        Bucket="mark-appels", Key="appels/run-1.txt"
    )

    client.delete_object = AsyncMock(
        side_effect=ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "refusé"}}, "DeleteObject"
        )
    )
    assert await fs.adelete_file("appels/run-1.txt") is False


@pytest.mark.asyncio
async def test_minio_appelle_remove_object_et_erreur_renvoie_faux():
    # Construit sans __init__ : celui-ci contacte le serveur MinIO pour le bucket.
    fs = MinioFileSystem.__new__(MinioFileSystem)
    fs.bucket_name = "mark-appels"
    fs.client = MagicMock()

    assert await fs.adelete_file("appels/run-1.txt") is True
    fs.client.remove_object.assert_called_once_with("mark-appels", "appels/run-1.txt")

    fs.client.remove_object.side_effect = S3Error(
        "AccessDenied", "refusé", "appels/run-1.txt", "req", "host", None
    )
    assert await fs.adelete_file("appels/run-1.txt") is False


@pytest.mark.asyncio
async def test_null_echoue_bruyamment():
    with pytest.raises(RuntimeError, match="NullFileSystem.adelete_file"):
        await NullFileSystem().adelete_file("appels/run-1.txt")
