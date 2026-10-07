"""[.mark] The delay of the model's answer (L7, PN2; plan delai-modele D1, D6, D7).

Measured on the fork: nothing bounds Mistral's request (600 s by default), and a model error is
not fatal, so the caller stays in silence. For an agent with the outage fallback on, the
conversation's Mistral service bounds its answer by ``delai_modele_s`` (4 s by default):

- no first piece within the delay, or the answer stalls that long between two pieces →
  ``DelaiModeleDepasse``; the service closes the stream, pushes NO error, and fires
  ``on_delai_modele_depasse``;
- every answer that starts fires ``on_reponse_modele_commencee`` (resets the count, D6).

``ReplisDelaiModele`` (engine side): first time, « Un instant, s'il vous plaît » and a new try;
second consecutive time, the outage fallback (``GardienPanne``). A caller who speaks again does
not reset the count (D6). The delay unset: the service behaves exactly as before.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

PHRASE_ATTENTE = "Un instant, s'il vous plaît."
TYPE_EVENEMENT = "mark-delai-modele-depasse"


class DelaiModeleDepasse(Exception):
    def __init__(self, moment: str, delai_s: float):
        super().__init__(f"model answer over {delai_s} s ({moment})")
        self.moment = moment
        self.delai_s = delai_s


class FluxAvecDelai:
    """The model's stream, each wait for the next piece bounded by the delay."""

    def __init__(
        self, flux: Any, delai_s: float, au_premier: Callable[[], Awaitable[None]]
    ):
        self._flux = flux
        self._delai = delai_s
        self._au_premier = au_premier

    def __aiter__(self):
        return self._parcourir()

    async def _parcourir(self):
        iterateur = self._flux.__aiter__()
        premier = True
        try:
            while True:
                try:
                    morceau = await asyncio.wait_for(iterateur.__anext__(), self._delai)
                except StopAsyncIteration:
                    return
                except TimeoutError:
                    raise DelaiModeleDepasse(
                        "premier_morceau" if premier else "en_cours", self._delai
                    ) from None
                if premier:
                    premier = False
                    try:
                        await self._au_premier()
                    except Exception as erreur:  # noqa: BLE001 -- a count never costs an answer
                        logger.warning(
                            f"[.mark] Model answer start not counted: {erreur!r}"
                        )
                yield morceau
        finally:
            fermer = getattr(iterateur, "aclose", None)
            if fermer is not None:
                await fermer()

    async def close(self):
        fermer = getattr(self._flux, "close", None) or getattr(
            self._flux, "aclose", None
        )
        if fermer is not None:
            await fermer()


class DelaiModeleMixin:
    """Mixed into ``DograhMistralLLMService``. ``mark_delai_modele_s`` None: unchanged."""

    mark_delai_modele_s: float | None = None

    def _mark_enregistrer_evenements(self) -> None:
        self._register_event_handler("on_delai_modele_depasse")
        self._register_event_handler("on_reponse_modele_commencee")

    async def get_chat_completions(self, context):  # type: ignore[override]
        delai = self.mark_delai_modele_s
        if not delai:
            return await super().get_chat_completions(context)  # type: ignore[misc]
        try:
            flux = await asyncio.wait_for(super().get_chat_completions(context), delai)  # type: ignore[misc]
        except TimeoutError:
            raise DelaiModeleDepasse("premier_morceau", delai) from None
        return FluxAvecDelai(
            flux, delai, lambda: self._call_event_handler("on_reponse_modele_commencee")
        )  # type: ignore[attr-defined]

    async def _process_context(self, context):  # type: ignore[override]
        try:
            await super()._process_context(context)  # type: ignore[misc]
        except DelaiModeleDepasse as depassement:
            await self._call_event_handler("on_delai_modele_depasse", depassement)  # type: ignore[attr-defined]


class ReplisDelaiModele:
    """The engine's answer to a model too slow, for ONE call."""

    def __init__(
        self,
        engine: Any,
        task: Any,
        gardien: Any,
        terminer: Callable[[], Awaitable[None]],
    ):
        self.engine = engine
        self.task = task
        self.gardien = gardien
        self.terminer = terminer
        self.compteur = 0
        self.total = 0

    def brancher(self, llm: Any) -> bool:
        if not hasattr(llm, "mark_delai_modele_s"):
            return False
        llm.event_handler("on_delai_modele_depasse")(self._depasse)
        llm.event_handler("on_reponse_modele_commencee")(self._commencee)
        return True

    async def _commencee(self, _service) -> None:
        self.compteur = 0

    async def _depasse(self, _service, depassement: DelaiModeleDepasse) -> None:
        from pipecat.frames.frames import LLMRunFrame, TTSSpeakFrame

        self.compteur += 1
        self.total += 1
        try:
            fiche = getattr(self.engine, "_gathered_context", None)
            if isinstance(fiche, dict):
                fiche["depassements_modele"] = self.total
            from api.services.analyse_run.incidents_appel import ATTRIBUT_JOURNAL

            journal = getattr(self.engine, ATTRIBUT_JOURNAL, None)
            if journal is not None:
                await journal.append(
                    {
                        "type": TYPE_EVENEMENT,
                        "payload": {
                            "attempt": self.compteur,
                            "moment": depassement.moment,
                            "delay_secs": depassement.delai_s,
                        },
                    }
                )
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[.mark] Model timeout not logged: {erreur!r}")
        if self.compteur == 1:
            await self.task.queue_frames(
                [
                    TTSSpeakFrame(
                        PHRASE_ATTENTE, append_to_context=False, persist_to_logs=True
                    ),
                    LLMRunFrame(),
                ]
            )
            return
        # ⛔ Whatever happens below, the call ends: the worst would be to stay in silence.
        try:
            await self.gardien.declencher(
                "modele_lent",
                "modele",
                f"{depassement.moment} > {depassement.delai_s} s",
            )
        finally:
            await self.terminer()
