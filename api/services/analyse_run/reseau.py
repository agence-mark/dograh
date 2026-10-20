"""La qualité de la liaison audio d'un appel WebRTC (.mark, fiabilite-orchestration, lot 9, F11).

Au banc du 19/10, la voix saccadée du 1463 était le wifi du poste (fluide en 5G) : rien dans le run
ne le disait. Pendant un appel navigateur, la liaison est relevée toutes les quelques secondes
(``RTCPeerConnection.getStats()`` d'aiortc, déjà dans le transport) et le bilan est rangé dans
``gathered_context.mark_reseau`` :

- ``inbound`` : la voix de l'appelant reçue par le serveur (paquets reçus et perdus, gigue) ;
- ``outbound`` : ce que le navigateur dit avoir reçu de la voix de l'agent (paquets perdus, gigue,
  temps d'aller-retour : le compte rendu RTCP du navigateur, ``remote-inbound-rtp``).

La gigue d'aiortc est en unités d'horloge RTP (48 000 Hz pour l'audio Opus) : elle est convertie en
millisecondes (``gigue_ms``). Pire valeur vue et dernière valeur sont gardées : la dernière dit
l'état de fin d'appel, la pire dit ce que l'appelant a pu entendre en route.

⛔ Ne fait jamais tomber un appel : toute erreur est journalisée, le bilan dit « unavailable ».
Pas de téléphone (Twilio) : aucun relevé, la fenêtre dit « non capté ».
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

CLE_RESEAU = "mark_reseau"
PERIODE_S = 5.0
HORLOGE_AUDIO_HZ = 48000


def _gigue_ms(gigue: Any) -> float | None:
    if isinstance(gigue, bool) or not isinstance(gigue, (int, float)):
        return None
    return round(gigue * 1000 / HORLOGE_AUDIO_HZ, 2)


def _entier(valeur: Any) -> int | None:
    return valeur if isinstance(valeur, int) and not isinstance(valeur, bool) else None


def lire_les_stats(rapport: Any) -> dict:
    """Un relevé à partir d'un rapport de statistiques d'aiortc (objets à attributs, ou dictionnaires
    de même forme). Seules les pistes audio comptent."""
    valeurs = rapport.values() if hasattr(rapport, "values") else list(rapport or [])
    releve: dict = {"inbound": None, "outbound": None}
    for stat in valeurs:
        def lire(cle: str, _stat: Any = stat) -> Any:
            return _stat.get(cle) if isinstance(_stat, dict) else getattr(_stat, cle, None)

        if lire("kind") not in (None, "audio"):
            continue
        genre = lire("type")
        if genre == "inbound-rtp":
            recus, perdus = _entier(lire("packetsReceived")), _entier(lire("packetsLost"))
            releve["inbound"] = {
                "packets_received": recus,
                "packets_lost": perdus,
                "jitter_ms": _gigue_ms(lire("jitter")),
            }
        elif genre == "remote-inbound-rtp":
            rtt = lire("roundTripTime")
            releve["outbound"] = {
                "packets_lost": _entier(lire("packetsLost")),
                "jitter_ms": _gigue_ms(lire("jitter")),
                "round_trip_ms": round(rtt * 1000, 1)
                if isinstance(rtt, (int, float)) and not isinstance(rtt, bool)
                else None,
            }
    return releve


def _pire(avant: float | None, apres: float | None) -> float | None:
    valeurs = [v for v in (avant, apres) if v is not None]
    return max(valeurs) if valeurs else None


class BilanDeLaLiaison:
    """Le bilan d'un appel : dernier relevé et pires valeurs vues."""

    def __init__(self) -> None:
        self.releves = 0
        self.dernier: dict = {"inbound": None, "outbound": None}
        self.pire = {"jitter_ms_in": None, "jitter_ms_out": None, "round_trip_ms": None}

    def ajouter(self, releve: dict) -> None:
        self.releves += 1
        entree, sortie = releve.get("inbound"), releve.get("outbound")
        if entree:
            self.dernier["inbound"] = entree
            self.pire["jitter_ms_in"] = _pire(self.pire["jitter_ms_in"], entree.get("jitter_ms"))
        if sortie:
            self.dernier["outbound"] = sortie
            self.pire["jitter_ms_out"] = _pire(self.pire["jitter_ms_out"], sortie.get("jitter_ms"))
            self.pire["round_trip_ms"] = _pire(self.pire["round_trip_ms"], sortie.get("round_trip_ms"))

    def en_dict(self) -> dict:
        if not self.releves:
            return {"status": "unavailable", "reason": "no_sample"}
        return {
            "status": "ok",
            "samples": self.releves,
            "last": self.dernier,
            "worst": self.pire,
        }


async def surveiller_la_liaison(
    obtenir_les_stats: Callable[[], Awaitable[Any]],
    ecrire: Callable[[dict], Awaitable[None]],
    *,
    periode_s: float = PERIODE_S,
) -> None:
    """Relève la liaison toutes les ``periode_s`` secondes jusqu'à l'annulation, puis écrit le bilan
    (une dernière fois, à l'annulation). Une erreur de relevé n'arrête pas la surveillance."""
    bilan = BilanDeLaLiaison()
    try:
        while True:
            try:
                bilan.ajouter(lire_les_stats(await obtenir_les_stats()))
            except asyncio.CancelledError:
                raise
            except Exception as erreur:  # noqa: BLE001 -- une mesure n'emporte pas l'appel
                logger.debug(f"[reseau] relevé de la liaison impossible : {erreur!r}")
            await asyncio.sleep(periode_s)
    finally:
        with contextlib.suppress(Exception):
            await asyncio.shield(ecrire(bilan.en_dict()))


def lancer_la_surveillance(
    connexion: Any, workflow_run_id: int, db: Any, *, periode_s: float = PERIODE_S
) -> asyncio.Task | None:
    """Pour un appel navigateur : lance la surveillance de ``connexion`` (``SmallWebRTCConnection``).
    ``None`` si la connexion ne sait pas donner ses statistiques. À annuler à la fin de l'appel."""
    try:
        obtenir = getattr(connexion.pc, "getStats", None)
    except Exception:  # noqa: BLE001 -- pas encore de connexion pair à pair
        obtenir = None
    if obtenir is None:
        return None

    async def ecrire(bilan: dict) -> None:
        try:
            await db.update_workflow_run(
                run_id=workflow_run_id, gathered_context={CLE_RESEAU: bilan}
            )
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[reseau] liaison du run {workflow_run_id} non écrite : {erreur!r}")

    return asyncio.create_task(
        surveiller_la_liaison(obtenir, ecrire, periode_s=periode_s),
        name=f"surveillance-liaison-{workflow_run_id}",
    )
