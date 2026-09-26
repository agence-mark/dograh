"""[.mark] The safety net of the list of terms: a refused list never costs the call.

Why this module exists
----------------------
On 2026-09-18 Deepgram refused the connection (HTTP 400) because the list of
terms to listen for was too long, and EVERY agent of the organization fell
silent: the transcription never opened, the calls never started (question 181
of the labo). The ceiling declared with the provider
(``api/services/configuration/plafond_lexique.py``) makes this unlikely; this
net makes it harmless (plan « le lexique », L2, 2026-09-26):

- the connection is refused (HTTP 400) while a list is sent → the service
  connects again, at once, WITHOUT the list;
- it is logged ``[.mark]`` and stamped on the run: « lexique non envoyé :
  refusé », with the provider's message;
- any other refusal (a wrong key is a 401), or a refusal without a list, is left
  exactly as the engine handles it today: the net changes nothing else.

⛔ No function of the engine or of Pipecat is changed. The net wraps, on THE
service instance of this call only, the one call that opens the connection:

- Flux (``DeepgramFluxSTTService``): ``_websocket_connect``, which raises
  ``websockets.InvalidStatus`` on a refused handshake; the list lives in the
  URL the service built, so the URL is built again from the emptied settings;
- the classic models (``DeepgramSTTService``, nova-3): ``client.listen.v1.connect``,
  whose handshake raises ``ApiError`` (status 400); the list is its ``keyterm``
  argument.

The settings are emptied too (``keyterm = []``): a reconnection later in the
call rebuilds its request from them, and must not send the refused list again.
"""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from typing import Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from loguru import logger

ETAT_ENVOYE = "envoyé"
ETAT_AUCUN_TERME = "aucun terme"
ETAT_SANS_PLAFOND = "non envoyé : aucun plafond déclaré pour ce fournisseur"
ETAT_REFUSE = "non envoyé : refusé"

# How long the provider's message is kept on the stamp.
LONGUEUR_MESSAGE = 300


def _statut_du_refus(erreur: BaseException) -> int | None:
    """The HTTP status of a refused handshake, whatever the library raised it."""
    reponse = getattr(erreur, "response", None)  # websockets.InvalidStatus
    statut = getattr(reponse, "status_code", None)
    if statut is None:
        statut = getattr(erreur, "status_code", None)  # deepgram ApiError
    try:
        return int(statut) if statut is not None else None
    except (TypeError, ValueError):
        return None


def _est_un_refus_de_la_liste(erreur: BaseException) -> bool:
    """400 is what Deepgram answers a list it will not take (181); a wrong key is a 401."""
    return _statut_du_refus(erreur) == 400


def _sans_la_liste(url: str) -> str:
    """The same URL, every ``keyterm`` parameter removed, the others kept in order."""
    morceaux = urlsplit(url)
    parametres = [(cle, valeur) for cle, valeur in parse_qsl(morceaux.query, keep_blank_values=True)
                  if cle != "keyterm"]
    return urlunsplit(morceaux._replace(query=urlencode(parametres)))


def _vider_la_liste(service) -> None:
    reglages = getattr(service, "_settings", None)
    if reglages is not None and hasattr(reglages, "keyterm"):
        reglages.keyterm = []


def armer_filet_lexique(service, liste: list[str] | None, sur_refus: Callable[[str], None] | None = None):
    """Arm the net on this call's transcription service, and return the service.

    ``sur_refus(message)`` is called once, when the list is refused and dropped
    (the stamp and the call's record). ⛔ Never raises: a service it does not
    know, or no list, is returned untouched.
    """
    if not liste or service is None:
        return service
    try:
        deja = {"refuse": False}

        def signaler(erreur: BaseException) -> None:
            message = f"{type(erreur).__name__}: {erreur}"[:LONGUEUR_MESSAGE]
            logger.warning(
                f"[.mark] The transcription refused the list of {len(liste)} terms "
                f"({message}). Connecting again WITHOUT the list: the call goes on, "
                f"the vocabulary keeps correction and pronunciation."
            )
            if not deja["refuse"]:
                deja["refuse"] = True
                if sur_refus is not None:
                    try:
                        sur_refus(message)
                    except Exception as echec:  # noqa: BLE001 -- a record never costs a call
                        logger.warning(f"[.mark] Refused list not recorded: {echec!r}")

        # Flux: the list travels in the URL.
        connecter = getattr(service, "_websocket_connect", None)
        if callable(connecter) and hasattr(service, "_websocket_url"):

            async def _websocket_connect(uri: str, **kwargs):
                try:
                    return await connecter(uri, **kwargs)
                except Exception as erreur:
                    if "keyterm=" not in uri or not _est_un_refus_de_la_liste(erreur):
                        raise
                    signaler(erreur)
                    _vider_la_liste(service)
                    uri = _sans_la_liste(uri)
                    service._websocket_url = uri
                    return await connecter(uri, **kwargs)

            service._websocket_connect = _websocket_connect
            return service

        # Classic models: the list is the ``keyterm`` argument of the SDK's connect.
        ecoute = getattr(getattr(getattr(service, "_client", None), "listen", None), "v1", None)
        connect = getattr(ecoute, "connect", None)
        if callable(connect):

            @asynccontextmanager
            async def _connect(**kwargs):
                async with AsyncExitStack() as pile:
                    try:
                        connexion = await pile.enter_async_context(connect(**kwargs))
                    except Exception as erreur:
                        if not kwargs.get("keyterm") or not _est_un_refus_de_la_liste(erreur):
                            raise
                        signaler(erreur)
                        _vider_la_liste(service)
                        kwargs = {cle: valeur for cle, valeur in kwargs.items() if cle != "keyterm"}
                        connexion = await pile.enter_async_context(connect(**kwargs))
                    yield connexion

            ecoute.connect = _connect
            return service

        logger.info(
            f"[.mark] No safety net for the list of terms on {type(service).__name__}: "
            f"a refusal is handled by the engine as before."
        )
        return service
    except Exception as erreur:  # noqa: BLE001 -- the net never costs the call
        logger.warning(f"[.mark] Safety net of the list of terms not armed: {erreur!r}")
        return service


def estampille_de_la_liste(liste) -> dict:
    """What the run is stamped with about its list (``runtime_configuration``).

    🔑 The SAME dict is kept by the net and updated on a refusal: the stamp the
    call's visit history records at the end says what really happened.
    """
    if liste.plafond is None:
        etat = ETAT_SANS_PLAFOND if liste.non_envoyes else ETAT_AUCUN_TERME
    else:
        etat = ETAT_ENVOYE if liste.termes else ETAT_AUCUN_TERME
    return {
        "etat": etat,
        "termes": len(liste.termes),
        "jetons": liste.jetons,
        "plafond_jetons": liste.plafond.jetons if liste.plafond else None,
        "plafond_termes": liste.plafond.termes if liste.plafond else None,
        "fournisseur_du_plafond": liste.plafond.fournisseur if liste.plafond else None,
        "non_envoyes": len(liste.non_envoyes),
    }


def noter_le_refus(estampille: dict, message: str, consigner: Callable[..., None] | None, cle: str) -> None:
    """The list was refused: the stamp says it, and the call's record keeps the message."""
    estampille["etat"] = ETAT_REFUSE
    estampille["refus"] = message
    if consigner is not None:
        consigner({"etat": ETAT_REFUSE, "refus": message}, cle)
