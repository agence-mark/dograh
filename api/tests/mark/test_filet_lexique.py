"""[.mark] Non-regression test for the safety net of the list of terms (L2).

The questions this file answers:

    When the transcription refuses the connection because of the list (HTTP
    400), does the service connect again WITHOUT the list, on Flux (the list is
    in the URL) and on the classic models (the list is the ``keyterm``
    argument)? Are the settings emptied, so that a later reconnection does not
    send the refused list again? Is the refusal said once, with the provider's
    message? And is everything else -- a wrong key (401), a refusal with no
    list, a list accepted -- left exactly as it was?

Why it exists
-------------
Plan « le lexique » (2026-09-26), L2, question 181 of the labo: on 2026-09-18 a
refused list made every agent of the organization fall silent.

⚠️ What this file does NOT prove: that the net is ARMED on the real route of a
call. That is ``test_traversants_appel.py``
(``test_une_liste_refusee_ne_fait_pas_tomber_l_appel``).
"""

from types import SimpleNamespace

import pytest
from websockets.datastructures import Headers
from websockets.exceptions import InvalidStatus
from websockets.http11 import Response

from api.services.configuration.plafond_lexique import plafond_du_lexique
from api.services.lexique.ecoute import ListeEcoutee
from api.services.pipecat.filet_lexique import (
    ETAT_AUCUN_TERME,
    ETAT_ENVOYE,
    ETAT_REFUSE,
    ETAT_SANS_PLAFOND,
    _sans_la_liste,
    armer_filet_lexique,
    estampille_de_la_liste,
    noter_le_refus,
)

URL = "wss://api.eu.deepgram.com/v2/listen?model=flux-general-multi&keyterm=Edilkamin&encoding=linear16&keyterm=MCZ"


def refus(statut: int) -> InvalidStatus:
    return InvalidStatus(Response(statut, "Refused", Headers(), b""))


class FauxFlux:
    """What the net touches on ``DeepgramFluxSTTService``, nothing more."""

    def __init__(self, statut_du_refus: int | None = 400):
        self._settings = SimpleNamespace(keyterm=["Edilkamin", "MCZ"])
        self._websocket_url = URL
        self.essais: list[str] = []
        self.statut_du_refus = statut_du_refus

    async def _websocket_connect(self, uri: str, **kwargs):
        self.essais.append(uri)
        if self.statut_du_refus is not None and "keyterm=" in uri:
            raise refus(self.statut_du_refus)
        return "connexion"


class ApiError(Exception):
    """Same shape as ``deepgram.core.api_error.ApiError``: a ``status_code``."""

    def __init__(self, status_code: int):
        super().__init__(f"status_code: {status_code}")
        self.status_code = status_code


class FauxClassique:
    """What the net touches on ``DeepgramSTTService``: ``_client.listen.v1.connect``."""

    def __init__(self, statut_du_refus: int | None = 400):
        self._settings = SimpleNamespace(keyterm=["Edilkamin"])
        self.essais: list[dict] = []
        self.fermees = 0
        faux = self

        class Connexion:
            async def __aenter__(self):
                return "connexion"

            async def __aexit__(self, *exc):
                faux.fermees += 1
                return False

        class Refus:
            async def __aenter__(self):
                raise ApiError(statut_du_refus)

            async def __aexit__(self, *exc):
                return False

        def connect(**kwargs):
            faux.essais.append(kwargs)
            if statut_du_refus is not None and kwargs.get("keyterm"):
                return Refus()
            return Connexion()

        self._client = SimpleNamespace(listen=SimpleNamespace(v1=SimpleNamespace(connect=connect)))


# --------------------------------------------------------------------------- #
# Flux
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_flux_liste_refusee_reconnexion_sans_la_liste():
    service, refus_notes = FauxFlux(), []
    armer_filet_lexique(service, ["Edilkamin", "MCZ"], refus_notes.append)
    assert await service._websocket_connect(URL) == "connexion"
    assert service.essais == [URL, _sans_la_liste(URL)]
    assert "keyterm" not in service.essais[1]
    assert "model=flux-general-multi" in service.essais[1] and "encoding=linear16" in service.essais[1]
    assert service._websocket_url == service.essais[1]
    assert service._settings.keyterm == []
    assert len(refus_notes) == 1 and "400" in refus_notes[0]


@pytest.mark.asyncio
async def test_flux_une_mauvaise_cle_reste_une_erreur_comme_avant():
    service = FauxFlux(statut_du_refus=401)
    armer_filet_lexique(service, ["Edilkamin"], lambda _m: pytest.fail("ce n'est pas un refus de la liste"))
    with pytest.raises(InvalidStatus):
        await service._websocket_connect(URL)
    assert service.essais == [URL]
    assert service._settings.keyterm == ["Edilkamin", "MCZ"]


@pytest.mark.asyncio
async def test_flux_liste_acceptee_rien_ne_change():
    service = FauxFlux(statut_du_refus=None)
    armer_filet_lexique(service, ["Edilkamin"], lambda _m: pytest.fail("aucun refus"))
    assert await service._websocket_connect(URL) == "connexion"
    assert service.essais == [URL]


@pytest.mark.asyncio
async def test_sans_liste_le_filet_nest_pas_arme():
    service = FauxFlux()
    original = service._websocket_connect
    assert armer_filet_lexique(service, [], None) is service
    assert armer_filet_lexique(service, None, None) is service
    assert service._websocket_connect == original


@pytest.mark.asyncio
async def test_le_refus_nest_signale_quune_fois():
    service, refus_notes = FauxFlux(), []
    armer_filet_lexique(service, ["Edilkamin"], refus_notes.append)
    await service._websocket_connect(URL)
    await service._websocket_connect(URL)  # a reconnection that still carries the old URL
    assert len(refus_notes) == 1


# --------------------------------------------------------------------------- #
# Classic models (nova-3)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_classique_liste_refusee_reconnexion_sans_la_liste():
    service, refus_notes = FauxClassique(), []
    armer_filet_lexique(service, ["Edilkamin"], refus_notes.append)
    async with service._client.listen.v1.connect(model="nova-3", keyterm=["Edilkamin"]) as connexion:
        assert connexion == "connexion"
    assert service.essais == [{"model": "nova-3", "keyterm": ["Edilkamin"]}, {"model": "nova-3"}]
    assert service.fermees == 1
    assert service._settings.keyterm == []
    assert len(refus_notes) == 1


@pytest.mark.asyncio
async def test_classique_une_mauvaise_cle_reste_une_erreur_comme_avant():
    service = FauxClassique(statut_du_refus=401)
    armer_filet_lexique(service, ["Edilkamin"], lambda _m: pytest.fail("ce n'est pas un refus de la liste"))
    with pytest.raises(ApiError):
        async with service._client.listen.v1.connect(model="nova-3", keyterm=["Edilkamin"]):
            pass
    assert len(service.essais) == 1


def test_un_service_inconnu_est_rendu_tel_quel():
    inconnu = object()
    assert armer_filet_lexique(inconnu, ["Edilkamin"], None) is inconnu


def test_le_filet_sarme_sur_les_vrais_services_deepgram():
    """The attributes the net wraps exist on the REAL Pipecat services (R1: a
    renamed attribute after a Pipecat upgrade would disarm the net in silence)."""
    from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService
    from pipecat.services.deepgram.stt import DeepgramSTTService

    flux = DeepgramFluxSTTService(
        api_key="cle-de-test",
        settings=DeepgramFluxSTTService.Settings(model="flux-general-multi", keyterm=["Edilkamin"]),
    )
    original = flux._websocket_connect
    armer_filet_lexique(flux, ["Edilkamin"], None)
    assert flux._websocket_connect != original
    assert hasattr(flux, "_websocket_url")
    assert flux._settings.keyterm == ["Edilkamin"]

    classique = DeepgramSTTService(
        api_key="cle-de-test",
        settings=DeepgramSTTService.Settings(model="nova-3", keyterm=["Edilkamin"]),
    )
    original = classique._client.listen.v1.connect
    armer_filet_lexique(classique, ["Edilkamin"], None)
    assert classique._client.listen.v1.connect != original
    assert classique._settings.keyterm == ["Edilkamin"]


# --------------------------------------------------------------------------- #
# The stamp
# --------------------------------------------------------------------------- #


def test_lestampille_dit_ce_que_la_transcription_a_recu_puis_le_refus():
    deepgram = plafond_du_lexique("deepgram", "flux-general-multi")
    envoyee = estampille_de_la_liste(ListeEcoutee(termes=["A"], non_envoyes=[], jetons=2, plafond=deepgram))
    assert envoyee == {
        "etat": ETAT_ENVOYE,
        "termes": 1,
        "jetons": 2,
        "plafond_jetons": deepgram.jetons,
        "fournisseur_du_plafond": "Deepgram",
        "non_envoyes": 0,
    }
    consignes = []
    noter_le_refus(envoyee, "InvalidStatus: HTTP 400", lambda entree, cle: consignes.append((cle, entree)), "lexique")
    assert envoyee["etat"] == ETAT_REFUSE and envoyee["refus"] == "InvalidStatus: HTTP 400"
    assert consignes == [("lexique", {"etat": ETAT_REFUSE, "refus": "InvalidStatus: HTTP 400"})]

    sans_plafond = estampille_de_la_liste(ListeEcoutee(termes=[], non_envoyes=["A"], jetons=0, plafond=None))
    assert sans_plafond["etat"] == ETAT_SANS_PLAFOND
    vide = estampille_de_la_liste(ListeEcoutee(termes=[], non_envoyes=[], jetons=0, plafond=deepgram))
    assert vide["etat"] == ETAT_AUCUN_TERME
