"""[.mark] Chantier fiabilite-orchestration, lot 4 ter (F22) : le son des phrases fabriqué au décroché.

Une phrase du code se dit justement quand quelque chose rame ; si c'est la voix qui rame, la phrase
d'attente arrive en retard elle aussi. Au décroché, pendant l'accueil, la **fabrique** fait dire une
fois chaque phrase allumée **sans variable** des agents de l'appel par une voix à part (le même
réglage que la voix de l'appel), dans un circuit isolé : jamais relié à l'appel, rien n'en sort. Le
son est gardé pour l'appel ; le diseur le joue ensuite tel quel, sans solliciter la voix
(``queue_speech(audio=…)``, transcription jointe : l'historique et le journal restent les mêmes).

Une phrase avec variable (``{{…}}``) se fabrique à la volée comme avant. Échec de fabrication (voix
absente, délai dépassé) : la phrase est dite par la voix de l'appel, comme avant. Aucun réglage
(décision F22 : automatique dès qu'une phrase est allumée). ⛔ Ne lève jamais.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from api.services.phrases.catalogue import MOTIFS
from api.services.phrases.regles import regles_de, resoudre

# Le temps laissé à la voix pour une phrase ; au-delà, la phrase reste à la voix de l'appel.
DELAI_PAR_PHRASE_S = 8.0
# Au plus ce nombre de phrases fabriquées par appel (le reste se dit à la voix).
MAX_PHRASES = 40
# Une phrase est finie à la fin de sa lecture, ou quand la voix n'envoie plus rien depuis ce temps
# (une voix peut tenir plusieurs phrases dans une même lecture sans fin explicite entre elles).
SILENCE_DE_FIN_S = 0.6


@dataclass(frozen=True)
class Son:
    audio: bytes
    taux: int


def textes_a_fabriquer(reglages_des_agents: Iterable[dict | None], reglages_principal: dict | None) -> list[str]:
    """Les phrases allumées, sans variable, que les agents de l'appel peuvent dire : la phrase en
    vigueur de chaque motif chez chaque agent, plus les variantes de ses règles d'étape allumées."""
    textes: list[str] = []

    def garder(variantes: Iterable[str]) -> None:
        for texte in variantes:
            if texte and "{{" not in texte and texte not in textes:
                textes.append(texte)

    for reglages in reglages_des_agents:
        for motif_id in MOTIFS:
            phrase = resoudre(
                motif_id, reglages_agent=reglages, reglages_principal=reglages_principal
            )
            if phrase is not None and phrase.dite:
                garder(phrase.variantes)
        # Toutes les règles allumées de l'agent (d'une étape, d'un outil, « dans l'ordre » : chaque
        # variante) et leurs phrases de sortie (« Ensuite »), toutes sans variable fabriquées au décroché.
        for regle in regles_de(reglages):
            if regle.active:
                garder(regle.variantes)
                garder(regle.ensuite.phrases)
        # Les règles « groupe » du principal valent pour les spécialisés : leurs phrases aussi.
        for regle in regles_de(reglages_principal):
            if regle.active and regle.portee == "groupe":
                garder(regle.variantes)
                garder(regle.ensuite.phrases)
    return textes[:MAX_PHRASES]


def nouveau_collecteur() -> Any:
    """Le bout du circuit isolé : garde l'audio de la phrase en cours, ne laisse rien passer
    (seuls les signaux de vie du circuit le traversent)."""
    from pipecat.frames.frames import (
        BotStartedSpeakingFrame,
        BotStoppedSpeakingFrame,
        CancelFrame,
        EndFrame,
        StartFrame,
        StopFrame,
        TTSAudioRawFrame,
        TTSStoppedFrame,
    )
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class Collecteur(FrameProcessor):
        def __init__(self) -> None:
            super().__init__(name="fabrique-des-sons")
            self.repartir()

        def repartir(self) -> None:
            self.morceaux: list[bytes] = []
            self.taux: int | None = None
            self.fini = asyncio.Event()
            self.dernier: float | None = None

        async def liberer(self) -> None:
            """Une voix se met en pause pendant sa lecture et attend la fin de la parole du robot
            (signal de la sortie audio, absente ici) : le collecteur la donne lui-même."""
            await self.push_frame(BotStartedSpeakingFrame(), FrameDirection.UPSTREAM)
            await self.push_frame(BotStoppedSpeakingFrame(), FrameDirection.UPSTREAM)

        async def process_frame(self, frame, direction):
            await super().process_frame(frame, direction)
            if isinstance(frame, TTSAudioRawFrame):
                self.morceaux.append(frame.audio)
                self.taux = frame.sample_rate
                self.dernier = asyncio.get_running_loop().time()
            elif isinstance(frame, TTSStoppedFrame):
                self.fini.set()
            elif isinstance(frame, (StartFrame, EndFrame, CancelFrame, StopFrame)):
                await self.push_frame(frame, direction)

    return Collecteur()


class FabriqueDesSons:
    """Les sons de l'appel. ``creer_la_voix`` : une voix neuve au réglage de la voix de l'appel."""

    def __init__(
        self,
        *,
        creer_la_voix: Callable[[], Any],
        ajouter_le_circuit: Callable[[Any], Any],
        taux_attendu: int,
        audio_config: Any = None,
        en_vie: Callable[[], bool] = lambda: True,
        voix_de_l_appel: Any = None,
    ) -> None:
        self._creer_la_voix = creer_la_voix
        self._ajouter = ajouter_le_circuit
        self._taux = taux_attendu
        self._audio_config = audio_config
        # Revue du 19/10 : l'appel fini, la fabrique s'arrête (au plus la phrase en cours).
        self._en_vie = en_vie
        # La voix qui parle à l'appelant : la fabrique n'y touche JAMAIS (un processeur Pipecat ne
        # tient que dans un circuit ; la brancher ici la retirerait de l'appel).
        self._voix_de_l_appel = voix_de_l_appel
        self.sons: dict[str, Son] = {}
        self.echecs: list[str] = []
        self._tache: asyncio.Task | None = None

    def son(self, texte: str) -> Son | None:
        return self.sons.get(texte)

    def lancer(self, textes: list[str]) -> None:
        if self._tache is not None or not textes:
            return
        self._tache = asyncio.get_running_loop().create_task(
            self.fabriquer(textes), name="fabrique-des-sons"
        )

    async def attendre(self) -> None:
        if self._tache is not None:
            await asyncio.gather(self._tache, return_exceptions=True)

    async def fabriquer(self, textes: list[str]) -> None:
        worker = None
        try:
            from pipecat.frames.frames import TTSSpeakFrame
            from pipecat.pipeline.pipeline import Pipeline
            from pipecat.pipeline.worker import PipelineParams, PipelineWorker

            voix = self._creer_la_voix()
            if voix is None or voix is self._voix_de_l_appel or _deja_dans_un_circuit(voix):
                logger.warning("[phrases] pas de voix à part pour la fabrique : sons non fabriqués")
                return
            collecteur = nouveau_collecteur()
            params = PipelineParams(enable_metrics=False, enable_heartbeats=False)
            params.audio_out_sample_rate = self._taux
            worker = PipelineWorker(
                Pipeline([voix, collecteur]),
                name="fabrique-des-sons",
                params=params,
                idle_timeout_secs=None,
                enable_turn_tracking=False,
                enable_rtvi=False,
            )
            await self._ajouter(worker)
            debut = asyncio.get_running_loop().time()
            while worker.started_at is None:
                if worker.has_finished() or asyncio.get_running_loop().time() - debut > 10:
                    raise RuntimeError("circuit de la fabrique non démarré")
                await asyncio.sleep(0.02)
            for texte in textes:
                if not self._en_vie() or worker.has_finished():
                    logger.info("[phrases] appel fini : fabrique des sons arrêtée")
                    break
                collecteur.repartir()
                await worker.queue_frame(TTSSpeakFrame(texte, append_to_context=False))
                await _attendre_la_phrase(collecteur, self._en_vie)
                await collecteur.liberer()
                audio = b"".join(collecteur.morceaux)
                if audio and collecteur.taux == self._taux:
                    self.sons[texte] = Son(audio=audio, taux=self._taux)
                else:
                    self.echecs.append(texte)
            logger.info(
                f"[phrases] sons fabriqués au décroché : {len(self.sons)}/{len(textes)}"
            )
        except asyncio.CancelledError:
            raise
        except Exception as erreur:  # noqa: BLE001 -- la voix de l'appel dira les phrases
            logger.warning(f"[phrases] fabrique des sons en échec : {erreur!r}")
        finally:
            if worker is not None:
                try:
                    await worker.cancel(reason="fabrique des sons terminée")
                except Exception:  # noqa: BLE001
                    pass


def _deja_dans_un_circuit(processeur: Any) -> bool:
    """Le processeur est-il déjà relié à un circuit (un voisin, ou démarré) ?"""
    return any(
        getattr(processeur, attribut, None) is not None for attribut in ("_prev", "_next")
    )


async def _attendre_la_phrase(collecteur: Any, en_vie: Callable[[], bool] = lambda: True) -> None:
    boucle = asyncio.get_running_loop()
    limite = boucle.time() + DELAI_PAR_PHRASE_S
    while boucle.time() < limite and not collecteur.fini.is_set() and en_vie():
        if collecteur.dernier is not None and boucle.time() - collecteur.dernier >= SILENCE_DE_FIN_S:
            return
        await asyncio.sleep(0.05)


def fabrique_de(moteur: Any) -> FabriqueDesSons | None:
    fabrique = (getattr(moteur, "__dict__", None) or {}).get("fabrique_des_sons")
    return fabrique if isinstance(fabrique, FabriqueDesSons) else None


def lancer_la_fabrique(moteur: Any) -> None:
    """Au décroché : fabrique les sons des phrases des agents connus de l'appel (le premier et les
    collègues en réserve, sinon le premier seul). ⛔ Ne lève jamais."""
    try:
        fabrique = fabrique_de(moteur)
        if fabrique is None or getattr(moteur, "sans_sortie_audio", False) is True:
            return
        principal = getattr(moteur, "reglages_appel", None)
        agents = [getattr(getattr(moteur, "active_agent", None), "reglages", None) or principal]
        from api.services.groupe.prechauffage import precharge_de

        precharge = precharge_de(moteur)
        for runtime in (getattr(precharge, "prets", None) or {}).values():
            agents.append(getattr(runtime, "reglages", None))
        fabrique.lancer(textes_a_fabriquer(agents, principal))
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[phrases] fabrique non lancée : {erreur!r}")
