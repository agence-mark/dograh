"""[.mark] The delay of the model's answer (L7, PN2; plan delai-modele D1, D6, D7).

Measured on the fork: nothing bounds Mistral's request (600 s by default), and a model error is
not fatal, so the caller stays in silence. For an agent with the outage fallback on, the
conversation's Mistral service bounds its answer by ``delai_modele_s`` (4 s by default):

- no first piece within the delay, or the answer stalls that long between two pieces →
  ``DelaiModeleDepasse``; the service closes the stream, pushes NO error, and fires
  ``on_delai_modele_depasse``;
- every answer that starts fires ``on_reponse_modele_commencee`` (resets the count, D6).

The engine's answer lives in ``garde_modele.GardeDuModele`` since fiabilite-orchestration (lot 4,
F20): armed for every agent, outage mode on or not; « Un instant » is the code sentence of the
cause « the model is slow » (theme Phrases), no longer a constant here. The delay unset: the
service behaves exactly as before.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

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
    """Mixed into ``DograhMistralLLMService``. ``mark_delai_modele_s`` None: unchanged.

    fiabilite-orchestration, lot 4 (C5) : ``mark_repli`` (connexion et modèle d'un cerveau de
    repli) et ``_mark_tentative_au_repli`` : la PROCHAINE requête part chez le repli (même service,
    mêmes outils, même fiche ; autre connexion, autre modèle), puis tout revient comme avant."""

    mark_delai_modele_s: float | None = None
    mark_repli: Any = None
    _mark_tentative_au_repli: bool = False

    def _mark_enregistrer_evenements(self) -> None:
        self._register_event_handler("on_delai_modele_depasse")
        self._register_event_handler("on_reponse_modele_commencee")

    async def _mark_demander(self, context):
        """La requête au modèle, chez le repli si la tentative le demande (une seule fois)."""
        repli = self.mark_repli if self._mark_tentative_au_repli else None
        self._mark_tentative_au_repli = False
        if repli is None:
            return await super().get_chat_completions(context)  # type: ignore[misc]
        reglages = getattr(self, "_settings", None)
        client, modele = self._client, getattr(reglages, "model", None)  # type: ignore[has-type]
        self._client = repli.client
        if reglages is not None:
            reglages.model = repli.modele
        try:
            return await super().get_chat_completions(context)  # type: ignore[misc]
        finally:
            self._client = client
            if reglages is not None:
                reglages.model = modele

    async def get_chat_completions(self, context):  # type: ignore[override]
        delai = self.mark_delai_modele_s
        if not delai:
            return await self._mark_demander(context)
        try:
            flux = await asyncio.wait_for(self._mark_demander(context), delai)
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
