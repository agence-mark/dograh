"""[.mark] Lot GT (builder partie 3) : la voix Gradium, branchée sur le service de Pipecat sans le copier.

R9 (ce que la copie épinglée de Pipecat fournit déjà) : ``pipecat/src/pipecat/services/gradium/tts.py``
(``GradiumTTSService``, WebSocket, un message ``setup`` par contexte audio) fait la synthèse, le découpage par
``client_req_id`` et la reconnexion au changement de voix. Il ne fait PAS :

| Ce que veut le produit | Ce que fait Pipecat (``gradium/tts.py``) | Ce que fait ce fichier |
|---|---|---|
| format de sortie du téléphone (``ulaw_8000``, ``pcm_8000``) | ``output_format`` écrit en dur à ``pcm`` (48 kHz), fréquence figée à 48 000 | le format et la fréquence suivent le réglage ; le μ-law est décodé en PCM 8 kHz avant la lecture |
| ``temp``, ``padding_bonus``, ``rewrite_rules`` | ``json_config`` est une chaîne, jamais remplie par défaut | ``json_config`` envoyé en objet, comme le montre la documentation du message ``setup`` |
| dictionnaire de prononciation, nom du modèle | absents du message ``setup`` | ``pronunciation_id`` et ``model_name`` ajoutés |
| session de 300 s | aucune réouverture (la connexion n'est rouverte qu'au changement de voix, ligne 157) | la connexion est rouverte entre deux tours, avant la limite |

⛔ Le sous-module n'est jamais modifié : tout vit ici, dans une sous-classe. Quand Pipecat fournira ces
choses, la surcharge correspondante se retire avec sa ligne de ce tableau.

Documentation lue le 05/11/2026 : docs.gradium.ai/guides/websocket-lifecycle.md (message ``setup``),
docs.gradium.ai/guides/voice-settings (``json_config``), docs.gradium.ai/guides/recipes/telephony-audio.md.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator, Callable
from typing import Any

from loguru import logger
from websockets.protocol import State

from api.services.configuration.options.gradium import (
    GRADIUM_FREQUENCE_PAR_DEFAUT,
    GRADIUM_FREQUENCES_PCM,
    GRADIUM_MARGE_DE_REOUVERTURE_S,
    GRADIUM_PADDING_MAX,
    GRADIUM_PADDING_MIN,
    GRADIUM_SESSION_MAX_S,
    GRADIUM_TTS_VOIX_PAR_DEFAUT,
)
from pipecat.audio.utils import ulaw_to_pcm
from pipecat.frames.frames import Frame, TTSAudioRawFrame
from pipecat.services.gradium.tts import GradiumTTSService


def padding_bonus_de_la_vitesse(vitesse: float) -> float:
    """C5 : ``padding_bonus = -4 x (vitesse - 1)``, borné à ±4 (conversion de la démo Gradbot)."""
    brut = -4.0 * (float(vitesse) - 1.0)
    return round(max(GRADIUM_PADDING_MIN, min(GRADIUM_PADDING_MAX, brut)), 4)


def format_et_frequence(output_format: str | None, taux_transport: int | None) -> tuple[str, int]:
    """Le format envoyé à Gradium et la fréquence du son qui en revient.

    ``auto`` : PCM à la fréquence de la ligne si Gradium la sert (8, 16, 24 ou 48 kHz), sinon PCM 48 kHz
    (le comportement de Pipecat). Les deux formats du téléphone sont à 8 kHz."""
    choix = (output_format or "auto").strip() or "auto"
    if choix in ("pcm_8000", "ulaw_8000"):
        return choix, 8000
    if taux_transport in GRADIUM_FREQUENCES_PCM:
        return f"pcm_{taux_transport}", int(taux_transport)
    return "pcm", GRADIUM_FREQUENCE_PAR_DEFAUT


def reglages_gradium_voix(tts_config, taux_transport: int | None = None) -> dict:
    """Ce que la voix Gradium reçoit, lu UNE fois pour la fabrique et pour l'estampille (§5.4 de
    ``18-ajout-fournisseur.md`` : la requête et l'estampille passent par la même fonction).

    ⛔ Un champ vide retombe sur le défaut du fournisseur ou du produit, jamais sur celui du connecteur
    (voix ``_6Aslh2DxfmnRLmP``, anglaise). ``speed`` et ``pronunciation_id`` ne partent que renseignés."""
    from api.services.configuration.registry import GRADIUM_TTS_ADRESSE_EUROPE

    adresse = (getattr(tts_config, "base_url", None) or "").strip() or GRADIUM_TTS_ADRESSE_EUROPE
    format_, frequence = format_et_frequence(getattr(tts_config, "output_format", None), taux_transport)
    reglages: dict[str, Any] = {
        "base_url": adresse,
        "model": (getattr(tts_config, "model", None) or "").strip() or "default",
        "voice": (getattr(tts_config, "voice", None) or "").strip() or GRADIUM_TTS_VOIX_PAR_DEFAUT,
        "temp": getattr(tts_config, "temp", None) if getattr(tts_config, "temp", None) is not None else 0.7,
        "rewrite_rules": (getattr(tts_config, "rewrite_rules", None) or "fr"),
        "output_format": format_,
        "sample_rate": frequence,
    }
    vitesse = getattr(tts_config, "speed", None)
    if vitesse is not None:
        reglages["padding_bonus"] = padding_bonus_de_la_vitesse(vitesse)
    pronunciation = (getattr(tts_config, "pronunciation_id", None) or "").strip()
    if pronunciation:
        reglages["pronunciation_id"] = pronunciation
    return reglages


class MarkGradiumTTSService(GradiumTTSService):
    """``GradiumTTSService`` + format de sortie, ``json_config`` en objet, dictionnaire, sessions de 300 s."""

    # Le pas de la veille (secondes) ; un test le réduit.
    INTERVALLE_VEILLE_S = 1.0

    def __init__(
        self,
        *,
        reglages_json: dict | None = None,
        pronunciation_id: str | None = None,
        output_format: str = "pcm",
        sample_rate: int = GRADIUM_FREQUENCE_PAR_DEFAUT,
        session_max_s: float = GRADIUM_SESSION_MAX_S,
        marge_de_reouverture_s: float = GRADIUM_MARGE_DE_REOUVERTURE_S,
        horloge: Callable[[], float] = time.monotonic,
        **kwargs,
    ):
        super().__init__(**kwargs)
        # Pipecat fige la fréquence à 48 000 ; la sienne se lit à `setup` (`_init_sample_rate`).
        self._init_sample_rate = sample_rate
        self._format_de_sortie = output_format
        self._json_objet = dict(reglages_json or {})
        self._pronunciation_id = pronunciation_id
        self._session_max_s = float(session_max_s)
        self._reouvrir_apres_s = max(1.0, float(session_max_s) - float(marge_de_reouverture_s))
        self._horloge = horloge
        self._ouverte_a: float | None = None
        self._verrou_de_connexion = asyncio.Lock()
        self._tache_de_veille: asyncio.Task | None = None
        self._avertie_de_la_limite = False
        self.reouvertures = 0

    # --- le message de départ -------------------------------------------------------------------------

    def _build_setup_msg(self, context_id: str) -> dict:
        message = super()._build_setup_msg(context_id)
        message["output_format"] = self._format_de_sortie
        message["model_name"] = self._settings.model or "default"
        if self._pronunciation_id:
            message["pronunciation_id"] = self._pronunciation_id
        # Un objet, comme le montre la documentation (`"json_config": { "temp": 0.3 }`), pas une chaîne.
        if self._json_objet:
            message["json_config"] = dict(self._json_objet)
        return message

    # --- le son du téléphone --------------------------------------------------------------------------

    async def append_to_audio_context(self, context_id, frame):
        """μ-law 8 kHz -> PCM 16 bits 8 kHz avant la lecture (le pipeline ne lit que du PCM)."""
        if self._format_de_sortie == "ulaw_8000" and isinstance(frame, TTSAudioRawFrame):
            frame.audio = await ulaw_to_pcm(frame.audio, 8000, 8000, self._resampler)
        await super().append_to_audio_context(context_id, frame)

    # --- les sessions de 300 s ------------------------------------------------------------------------

    async def _connect_websocket(self):
        deja_ouverte = bool(self._websocket and self._websocket.state is State.OPEN)
        await super()._connect_websocket()
        if not deja_ouverte and self._websocket is not None:
            self._ouverte_a = self._horloge()
            self._avertie_de_la_limite = False

    async def _disconnect_websocket(self):
        await super()._disconnect_websocket()
        self._ouverte_a = None

    def age_de_la_session(self) -> float | None:
        return None if self._ouverte_a is None else self._horloge() - self._ouverte_a

    def _libre_entre_deux_tours(self, sauf_contexte: str | None = None) -> bool:
        """Rien n'est en train d'être dit ni attendu : aucun contexte audio (hors celui qui démarre), aucune
        requête ouverte chez Gradium. Rouvrir à ce moment ne coupe jamais une phrase."""
        autres = [c for c in self.get_audio_contexts() if c != sauf_contexte]
        encore_ouvertes = [c for c in self._setup_context_ids if c != sauf_contexte]
        return not autres and not encore_ouvertes

    async def rouvrir_si_necessaire(self, sauf_contexte: str | None = None) -> bool:
        """Rouvre la connexion quand la session approche de sa limite ET que rien n'est dit. Rend vrai si elle
        a été rouverte. Ne lève jamais : une réouverture ratée laisse `run_tts` se reconnecter comme avant."""
        age = self.age_de_la_session()
        if age is None or self._websocket is None:
            return False
        if age < self._reouvrir_apres_s:
            return False
        if not self._libre_entre_deux_tours(sauf_contexte):
            if age >= self._session_max_s and not self._avertie_de_la_limite:
                self._avertie_de_la_limite = True
                logger.warning(f"{self}: session Gradium au-delà de {self._session_max_s:.0f} s, une phrase est en cours")
            return False
        async with self._verrou_de_connexion:
            try:
                await self._disconnect()
                await self._connect()
            except Exception as erreur:  # noqa: BLE001 -- l'appel continue, `run_tts` se reconnecte
                logger.warning(f"{self}: réouverture de la session Gradium ratée : {erreur!r}")
                return False
        self.reouvertures += 1
        logger.info(f"{self}: session Gradium rouverte après {age:.0f} s ({self.reouvertures})")
        return True

    async def _veille_de_session(self):
        while True:
            await asyncio.sleep(self.INTERVALLE_VEILLE_S)
            try:
                await self.rouvrir_si_necessaire()
            except asyncio.CancelledError:
                raise
            except Exception as erreur:  # noqa: BLE001
                logger.warning(f"{self}: veille de session Gradium : {erreur!r}")

    async def _arreter_la_veille(self):
        if self._tache_de_veille is not None:
            await self.cancel_task(self._tache_de_veille)
            self._tache_de_veille = None

    async def setup(self, setup):
        await super().setup(setup)
        if self._tache_de_veille is None:
            self._tache_de_veille = self.create_task(self._veille_de_session())

    async def stop(self, frame):
        await self._arreter_la_veille()
        await super().stop(frame)

    async def cancel(self, frame):
        await self._arreter_la_veille()
        await super().cancel(frame)

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        # Filet : la veille a pu manquer le creux (tour précédent trop proche). La première phrase d'un tour
        # rouvre ici, avant d'envoyer quoi que ce soit sur l'ancienne connexion.
        if context_id not in self._setup_context_ids:
            await self.rouvrir_si_necessaire(sauf_contexte=context_id)
        async with self._verrou_de_connexion:
            pass
        async for frame in super().run_tts(text, context_id):
            yield frame
