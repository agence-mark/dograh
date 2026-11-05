"""[.mark] S1 / D179 : la durée maximale d'une conversation du widget, en trois temps.

* à T - 60 s : une consigne au modèle (conclure) ;
* à T : après la phrase en cours (le bot a fini de parler), la phrase de fin du code, puis la fin de l'appel ;
* à T + 20 s : coupure dure si l'appel court encore (jamais au milieu d'une phrase avant T).

Le déroulé est ici, avec ses actions injectées (consigne, phrase de fin, coupure, état) : un test joue les trois temps
sans pipeline. ``lancer_pour_moteur`` branche le déroulé sur le moteur d'un appel de widget.
"""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable

from loguru import logger

MARGE_CONSIGNE_S = 60.0
GRACE_COUPURE_S = 20.0
PAS_S = 0.25

CONSIGNE_DE_FIN = (
    "La conversation doit se terminer dans moins d'une minute. Termine ta réponse en cours, conclus poliment "
    "et dis au revoir."
)
PHRASE_DE_FIN = "Je dois malheureusement conclure cette conversation. Merci de votre visite et à bientôt."


class MinuteurDuree:
    def __init__(
        self,
        duree_s: float,
        *,
        consigne: Callable[[], Awaitable[None]],
        phrase_de_fin: Callable[[], Awaitable[None]],
        couper: Callable[[], Awaitable[None]],
        bot_parle: Callable[[], bool],
        termine: Callable[[], bool],
        marge_consigne_s: float = MARGE_CONSIGNE_S,
        grace_coupure_s: float = GRACE_COUPURE_S,
        pas_s: float = PAS_S,
    ):
        self.duree_s = float(duree_s)
        self._consigne = consigne
        self._phrase_de_fin = phrase_de_fin
        self._couper = couper
        self._bot_parle = bot_parle
        self._termine = termine
        self._marge = marge_consigne_s
        self._grace = grace_coupure_s
        self._pas = pas_s
        self.evenements: list[str] = []

    async def _jusqua(self, instant: float) -> bool:
        """Attend l'instant (horloge monotone) ; ``False`` si l'appel s'est terminé entre-temps."""
        while time.monotonic() < instant:
            if self._termine():
                return False
            await asyncio.sleep(min(self._pas, max(instant - time.monotonic(), 0.0)))
        return not self._termine()

    async def derouler(self) -> None:
        t0 = time.monotonic()
        fin = t0 + self.duree_s
        limite = fin + self._grace
        if not await self._jusqua(fin - self._marge):
            return
        self.evenements.append("consigne")
        await self._consigne()
        if not await self._jusqua(fin):
            return
        # Jamais au milieu d'une phrase : on attend la fin de la phrase en cours, dans la limite de la coupure dure.
        while self._bot_parle() and time.monotonic() < limite and not self._termine():
            await asyncio.sleep(self._pas)
        if self._termine():
            return
        if time.monotonic() < limite:
            self.evenements.append("phrase_de_fin")
            tache = asyncio.create_task(self._phrase_de_fin())
            try:
                while not tache.done() and time.monotonic() < limite and not self._termine():
                    await asyncio.sleep(self._pas)
            finally:
                if not tache.done():
                    tache.cancel()
        while not self._termine() and time.monotonic() < limite:
            await asyncio.sleep(self._pas)
        if not self._termine():
            self.evenements.append("coupure")
            await self._couper()


async def dire_la_fin(engine) -> None:
    """La phrase de fin, par le catalogue des phrases (motif ``fin_duree_max`` : l'agent peut la réécrire). Sans règle,
    ou règle éteinte, ou diseur absent : la phrase d'avant, dite telle quelle ; la conversation ne finit jamais en
    silence. Rend la main quand la phrase est jouée. ⛔ Ne lève jamais plus que ``queue_speech`` d'avant."""
    from api.services.phrases.catalogue import FIN_DE_DUREE_MAX
    from api.services.phrases.diseur import DiseurDePhrases

    lecture = None
    diseur = getattr(engine, "phrases", None)
    if isinstance(diseur, DiseurDePhrases):
        lecture = await diseur.dire_la_parole(FIN_DE_DUREE_MAX)
    if lecture is None:
        lecture = await engine.queue_speech(PHRASE_DE_FIN, timeout=15)
    await lecture.wait()


def lancer_pour_moteur(
    engine, duree_s: float, a_la_fin: Callable[[int], Awaitable[None]] | None = None
) -> "asyncio.Task":
    """Branche le minuteur sur le moteur d'un appel de widget ; la tâche s'arrête avec l'appel."""
    from pipecat.frames.frames import LLMMessagesAppendFrame
    from pipecat.utils.enums import EndTaskReason

    from api.services.groupe.passations import ConsigneDuCode

    moniteur = engine.call_monitor
    raison = EndTaskReason.CALL_DURATION_EXCEEDED.value

    async def consigne():
        agregateur = moniteur.user_aggregator
        if agregateur is None:
            return
        await agregateur.push_frame(
            LLMMessagesAppendFrame([{"role": "user", "content": ConsigneDuCode(CONSIGNE_DE_FIN)}], run_llm=True)
        )

    async def phrase_de_fin():
        try:
            await dire_la_fin(engine)
        finally:
            await engine.end_call_with_reason(raison)

    async def couper():
        await engine.end_call_with_reason(raison, abort_immediately=True)

    minuteur = MinuteurDuree(
        duree_s,
        consigne=consigne,
        phrase_de_fin=phrase_de_fin,
        couper=couper,
        bot_parle=lambda: bool(getattr(moniteur, "bot_speaking", False)),
        termine=engine.is_call_disposed,
    )

    async def courir():
        debut = time.monotonic()
        try:
            await minuteur.derouler()
        except Exception:  # noqa: BLE001 -- la durée ne doit jamais faire tomber l'appel ; le plafond de l'amont reste
            logger.exception("[.mark] Public widget duration timer failed")
        finally:
            if a_la_fin is not None:
                try:
                    await a_la_fin(int(time.monotonic() - debut))
                except Exception:  # noqa: BLE001 -- le versement des minutes n'est jamais une raison de planter
                    logger.exception("[.mark] Public widget duration not recorded")

    return asyncio.create_task(courir(), name="widget-duree-max")
