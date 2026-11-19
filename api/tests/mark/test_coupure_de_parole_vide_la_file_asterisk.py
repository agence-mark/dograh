"""[.mark] Coupure de parole pendant un appel Asterisk : le fork demande à Asterisk de vider sa file audio.

| Test | Ce qu'il prouve |
|---|---|
| coupure de parole | par la vraie fabrique du transport, une coupure de parole fait partir vers Asterisk exactement une trame texte ``FLUSH_MEDIA`` et aucune autre trame texte, pendant que le son de la ligne et le raccrochage de fin d'appel passent toujours par le sérialiseur de l'amont |

Les deux premières assertions sont des témoins du montage : sans elles, une liste de trames texte
fausse pourrait venir d'une liaison morte ou d'une couture qui n'a pas pris, et non du code testé.
"""

from pipecat.frames.frames import InterruptionFrame
from pipecat.tests.utils import run_test
from starlette.websockets import WebSocketState

from api.services.pipecat.audio_config import create_audio_config
from api.services.telephony.providers.ari import transport as transport_asterisk
from api.services.telephony.providers.ari.strategies import ARIHangupStrategy

# Ce qu'Asterisk attend sur la liaison, écrit en dur : le test ne lit pas la constante du code,
# sinon il ne verrait pas un changement de sa valeur.
COMMANDE_DE_VIDAGE = "FLUSH_MEDIA"
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


async def test_la_coupure_de_parole_envoie_a_asterisk_exactement_une_commande_de_vidage(monkeypatch):
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
        frames_to_send=[InterruptionFrame()],
        start_timeout=DEMARRAGE_S,
    )

    assert liaison.trames_binaires, (
        "aucune trame binaire : le son de la ligne n'a pas traversé le sérialiseur, le montage est mort"
    )
    assert raccrochages == [CANAL], (
        "le raccrochage de fin d'appel n'a pas été remis une fois au sérialiseur de l'amont"
    )
    assert liaison.trames_texte == [COMMANDE_DE_VIDAGE]
