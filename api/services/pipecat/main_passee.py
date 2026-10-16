"""[.mark] Le cerveau d'un agent autour d'une passation (chantier agents-specialises, D1).

Rejeu du 16/10, run 1404 : dans la même réponse, l'accueil a passé la main ET écrit une
porte vers une de ses étapes. La porte, lue une fraction de seconde avant l'outil, a relancé
l'accueil : il a parlé pendant la passation, et le spécialiste a ouvert sur cette réplique de
l'assistant, que le fournisseur refuse en dernier (400). Tour perdu.

Deux garde-fous, posés au plus près de la requête, quel que soit le chemin qui la déclenche :

- ``muter`` / ``rendre_la_parole`` : un agent qui a passé la main ne parle plus. Son cerveau
  rend un flux vide sans rien envoyer, jusqu'à ce qu'il reprenne la main (principal chaud
  au retour) ou que la passation échoue (il garde l'appel) ;
- une requête de conversation qui finit par une réplique de l'assistant reçoit, dans la
  requête seulement, la note de passation (jamais dite, jamais gardée dans le contexte).

⛔ Ne lève jamais à la place du service.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.services.groupe.passations import NOTE_DE_PASSATION

ATTRIBUT = "_mark_main_passee"


def muter(llm: Any) -> None:
    """L'agent vient de passer la main : son cerveau ne parle plus."""
    try:
        if llm is not None:
            setattr(llm, ATTRIBUT, True)
    except Exception:  # noqa: BLE001
        pass


def rendre_la_parole(llm: Any) -> None:
    """L'agent (re)prend la main, ou la passation a échoué : il reparle."""
    try:
        if llm is not None and getattr(llm, ATTRIBUT, False):
            setattr(llm, ATTRIBUT, False)
    except Exception:  # noqa: BLE001
        pass


def avec_la_note(messages: list) -> list:
    """Les messages de la requête, la note ajoutée si le dernier (hors consignes) est une
    réplique de l'assistant sans appel d'outil."""
    try:
        for message in reversed(messages):
            if not isinstance(message, dict) or message.get("role") == "system":
                continue
            if message.get("role") == "assistant" and not message.get("tool_calls"):
                return [*messages, {"role": "user", "content": NOTE_DE_PASSATION}]
            return messages
        return messages
    except Exception:  # noqa: BLE001
        return messages


class _FluxVide:
    def __aiter__(self):
        return self._rien()

    async def _rien(self):
        return
        yield  # noqa: B901 -- générateur vide

    async def close(self):
        return None


class MainPasseeMixin:
    """Mêlé au cerveau compatible OpenAI, sous la trace et au-dessus de la relance : un
    agent muet ne déclenche ni relance ni phrase de repli."""

    async def get_chat_completions(self, context):  # type: ignore[override]
        if getattr(self, ATTRIBUT, False):
            logger.info("[passation] l'agent a passé la main : sa réponse n'est pas demandée")
            return _FluxVide()
        return await super().get_chat_completions(context)  # type: ignore[misc]

    def build_chat_completion_params(self, params_from_context):  # type: ignore[override]
        params = super().build_chat_completion_params(params_from_context)  # type: ignore[misc]
        messages = params.get("messages")
        if isinstance(messages, list):
            complete = avec_la_note(messages)
            if complete is not messages:
                logger.info("[passation] requête finie par l'assistant : note ajoutée")
                params["messages"] = complete
        return params
