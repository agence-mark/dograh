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
  argument;
- Soniox (``SonioxSTTService``, chantier communes-cp-et-lexique-soniox, S3):
  ``_get_websocket``, read through a filter. Soniox refuses a context by a
  message inside the session (``error_code`` 400), not at the handshake; the
  message is held back, ``context`` (terms and domain description) is emptied,
  the reading of the session ends, and the engine's reconnection sends none.

The settings are emptied too (``keyterm = []``): a reconnection later in the
call rebuilds its request from them, and must not send the refused list again.
"""

from __future__ import annotations

import json
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


def _refus_du_contexte_soniox(message, avant_tout_mot: bool = True) -> str | None:
    """[.mark] The provider's text when a Soniox message refuses the context, else None.

    Soniox answers a request it will not take with ``error_code`` 400 inside
    the session (its documentation, ``invalid_request``); a missing credit is a
    402, a wrong key a 401: those are not the list's, and are left alone.
    A 400 is taken for the context's when its message names the context
    (probe of 2026-10-03: « Context is too long: 8021 tokens, the maximum is
    8000 tokens. »), or when it comes before any word: the context is read at
    the start of the session. A 400 in the middle of the call that does not
    name it is left to the engine (review of 2026-10-03).
    """
    try:
        contenu = json.loads(message)
    except (TypeError, ValueError):
        return None
    if not isinstance(contenu, dict):
        return None
    try:
        code = int(contenu.get("error_code"))
    except (TypeError, ValueError):
        return None
    if code != 400:
        return None
    texte = str(contenu.get("error_message") or "")
    if not avant_tout_mot and "context" not in texte.lower():
        return None
    return f"{code}: {texte}".strip()


def _porte_des_mots(message) -> bool:
    try:
        contenu = json.loads(message)
    except (TypeError, ValueError):
        return False
    return isinstance(contenu, dict) and bool(contenu.get("tokens"))


class _SocketFiltree:
    """[.mark] The Soniox socket of this call, read through the net.

    Every message passes untouched except a refusal of the context while one
    is sent: that one is held back, so the engine does not report it as an
    error of the call, and the reading ENDS there: the engine then reconnects
    through the emptied settings, whether or not Soniox closes the session
    (review of 2026-10-03).
    """

    def __init__(self, socket, retenir: Callable[[object, bool], bool]):
        self._socket = socket
        self._retenir = retenir

    def __aiter__(self):
        return self._lire()

    async def _lire(self):
        avant_tout_mot = True
        async for message in self._socket:
            if self._retenir(message, avant_tout_mot):
                return
            if avant_tout_mot and _porte_des_mots(message):
                avant_tout_mot = False
            yield message

    def __getattr__(self, nom):
        return getattr(self._socket, nom)


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
    if service is None:
        return service
    reglages = getattr(service, "_settings", None)
    # [.mark] Soniox carries the terms AND the domain description in one
    # context: a description alone arms the net too (communes-cp-et-lexique-soniox).
    contexte_soniox = reglages is not None and getattr(reglages, "context", None) is not None
    if not liste and not contexte_soniox:
        return service
    try:
        deja = {"refuse": False}

        def signaler(erreur: BaseException | str) -> None:
            message = (
                erreur if isinstance(erreur, str) else f"{type(erreur).__name__}: {erreur}"
            )[:LONGUEUR_MESSAGE]
            logger.warning(
                f"[.mark] The transcription refused the list of {len(liste or [])} terms "
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

        # Soniox (S3, question n° 273): the context travels in the first message
        # of the session, and a refusal comes back as a message, not as a
        # refused handshake. The context is emptied in the settings, which every
        # reconnection reads to build its first message again.
        lire_socket = getattr(service, "_get_websocket", None)
        if contexte_soniox and callable(lire_socket):

            def retenir(message, avant_tout_mot: bool) -> bool:
                if reglages.context is None:
                    return False
                refus = _refus_du_contexte_soniox(message, avant_tout_mot)
                if refus is None:
                    return False
                signaler(refus)
                reglages.context = None
                return True

            def _get_websocket():
                return _SocketFiltree(lire_socket(), retenir)

            service._get_websocket = _get_websocket
            return service

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
        envoye = liste.termes or getattr(liste, "description", None)
        etat = ETAT_ENVOYE if envoye else ETAT_AUCUN_TERME
    estampille = {
        "etat": etat,
        "termes": len(liste.termes),
        "jetons": liste.jetons,
        "plafond_jetons": liste.plafond.jetons if liste.plafond else None,
        "plafond_termes": liste.plafond.termes if liste.plafond else None,
        "fournisseur_du_plafond": liste.plafond.fournisseur if liste.plafond else None,
        "non_envoyes": len(liste.non_envoyes),
    }
    # [.mark] Soniox (Q5, 2026-10-02): the domain description sent, in characters.
    if getattr(liste, "description", None):
        estampille["description_caracteres"] = len(liste.description)
    return estampille


def noter_le_refus(estampille: dict, message: str, consigner: Callable[..., None] | None, cle: str) -> None:
    """The list was refused: the stamp says it, and the call's record keeps the message."""
    estampille["etat"] = ETAT_REFUSE
    estampille["refus"] = message
    if consigner is not None:
        consigner({"etat": ETAT_REFUSE, "refus": message}, cle)
