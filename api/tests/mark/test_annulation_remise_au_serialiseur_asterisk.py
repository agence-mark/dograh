"""[.mark] Annulation d'un appel Asterisk : la trame passe par le sérialiseur de l'amont, comme avant le lot 1.

| Test | Ce qu'il prouve |
|---|---|
| annulation | par la vraie fabrique du transport, une trame d'annulation fait raccrocher le canal une fois, par la stratégie de l'amont, et ne fait partir aucune trame texte : la sous-classe rend pour cette trame exactement ce que rendait le sérialiseur de l'amont |

Aucune trame de fin n'est envoyée après l'annulation : sinon le raccrochage de fin d'appel
masquerait un raccrochage manqué à l'annulation, la stratégie ne raccrochant qu'une fois.
"""

from pipecat.frames.frames import CancelFrame
from pipecat.tests.utils import run_test
from starlette.websockets import WebSocketState

from api.services.pipecat.audio_config import create_audio_config
from api.services.telephony.providers.ari import transport as transport_asterisk
from api.services.telephony.providers.ari.strategies import ARIHangupStrategy

CANAL = "canal-de-test"
DEMARRAGE_S = 15


class _FausseLiaison:
    """La liaison WebSocket vers Asterisk : garde ce que le transport lui envoie, par type de trame."""

    def __init__(self) -> None:
        self.client_state = WebSocketState.CONNECTED
        self.application_state = WebSocketState.CONNECTED
        self.headers: dict[str, str] = {}
        self.trames_texte: list[str] = []
        self.trames_binaires: list[bytes] = []

    async def send_text(self, data: str) -> None:
        self.trames_texte.append(data)

    async def send_bytes(self, data: bytes) -> None:
        self.trames_binaires.append(data)

    async def close(self) -> None:
        return None


async def test_l_annulation_est_remise_au_serialiseur_de_l_amont(monkeypatch):
    monkeypatch.delenv("PIPECAT_ALLOWED_ORIGINS", raising=False)

    async def faux_identifiants(organization_id, telephony_configuration_id, expected_provider):
        return {
            "provider": "ari",
            "ari_endpoint": "http://asterisk.invalid:8088",
            "app_name": "application-factice",
            "app_password": "factice",
        }

    monkeypatch.setattr(transport_asterisk, "load_credentials_for_transport", faux_identifiants)

    raccrochages: list[str] = []

    async def faux_raccrochage(self, context):
        raccrochages.append(context["channel_id"])
        return True

    monkeypatch.setattr(ARIHangupStrategy, "execute_hangup", faux_raccrochage)

    liaison = _FausseLiaison()
    transport = await transport_asterisk.create_transport(
        liaison,
        1,
        create_audio_config("ari"),
        1,
        channel_id=CANAL,
    )

    await run_test(
        transport.output(),
        frames_to_send=[CancelFrame()],
        send_end_frame=False,
        start_timeout=DEMARRAGE_S,
    )

    assert raccrochages == [CANAL], (
        "l'annulation n'a pas été remise une fois au sérialiseur de l'amont : le canal ne raccroche pas"
    )
    assert liaison.trames_texte == []
