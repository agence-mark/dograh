"""[.mark] V1b : la route d'un appel rend la note du juge et la version jouée.

La question de ce fichier : la page d'une conversation peut-elle écrire « 4,6 / 5 » et « v4 » d'après la route de
l'appel, et un appel pas encore jugé rend-il une note vide (jamais 0) ?
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from api.routes import workflow as routes


def _run(note, definition):
    return SimpleNamespace(
        id=7, workflow_id=3, name="WR-7", mode="twilio", is_completed=True, public_access_token="t",
        transcript_url=None, recording_url=None, extra={}, cost_info={}, usage_info={}, created_at=None,
        definition_id=1, definition=definition, initial_context={}, gathered_context={}, call_type="inbound",
        logs=None, annotations=None, note_juge=note,
    )


async def _lire(run):
    user = SimpleNamespace(selected_organization_id=1)
    with patch.object(routes.db_client, "get_workflow_run", AsyncMock(return_value=run)):
        return await routes.get_workflow_run(3, 7, user)


async def test_la_route_rend_la_note_et_la_version():
    r = await _lire(_run(4.6, SimpleNamespace(version_number=4)))
    assert r["note_juge"] == 4.6
    assert r["version_number"] == 4


async def test_un_appel_non_juge_rend_une_note_vide():
    r = await _lire(_run(None, None))
    assert r["note_juge"] is None
    assert r["version_number"] is None
