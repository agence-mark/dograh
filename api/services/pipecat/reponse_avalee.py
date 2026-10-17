"""[.mark] La réponse avalée par le fournisseur : relancée une fois, sans flux.

Chantier agents-specialises, banc d'architecture du 16/10 (runs 1315 à 1346). Le cerveau
compatible OpenAI (Mistral Small chez Scaleway) rend parfois un flux **vide** : ni texte, ni
appel d'outil, ``finish_reason = stop``, alors que le fournisseur compte des jetons générés
(10, la taille d'un appel d'outil). Le modèle a répondu ; c'est la conversion de sa réponse
en flux qui l'a perdue. Résultat : un agent muet, 23 fois sur un banc, jamais sur un autre
cerveau du même fournisseur.

Ce que fait ce module, et rien d'autre :

- le flux passe tel quel dès qu'un morceau porte du texte ou un appel d'outil ;
- un flux fini sans rien de tout cela, avec des jetons générés comptés par le fournisseur,
  est **relancé une fois sans flux** (même requête, ``stream`` à faux) ; la réponse est
  rendue en morceaux comme si elle avait coulé, pour que la suite (Pipecat, la trace, le
  lecteur de portes) ne voie aucune différence ;
- C2, filet du silence (Evan, 16/10) : un flux sans texte ni appel d'outil n'est jamais une
  réponse ; il est relancé même sans jeton compté ; si la relance est vide aussi (ou en
  erreur) et que l'appelant attend une réponse (le dernier message est le sien), le code dit
  ``PHRASE_DE_REPLI`` plutôt qu'un silence ; sinon le flux d'origine est rendu, comme avant.

⛔ Ne lève jamais à la place du service : toute erreur de la relance rend le comportement
d'avant. Un flux qui a déjà porté du texte n'est jamais relancé (rien n'est dit deux fois).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

# C2 : la phrase dite par le code quand le cerveau n'a rien rendu, deux fois. Neutre, sans mot de
# métier : elle redonne la parole à l'appelant, qui répète, et le tour repart normalement.
PHRASE_DE_REPLI = "Pardon, je n'ai pas bien saisi. Vous pouvez répéter ?"


def _delta(morceau: Any) -> Any:
    choix = getattr(morceau, "choices", None) or []
    return getattr(choix[0], "delta", None) if choix else None


def porte_quelque_chose(morceau: Any) -> bool:
    """Le morceau porte-t-il du texte ou un appel d'outil ?"""
    delta = _delta(morceau)
    if delta is None:
        return False
    return bool(getattr(delta, "content", None) or getattr(delta, "tool_calls", None))


def jetons_generes(morceau: Any) -> int:
    usage = getattr(morceau, "usage", None)
    try:
        return int(getattr(usage, "completion_tokens", 0) or 0)
    except (TypeError, ValueError):
        return 0


def additionner(usage_a: Any, usage_b: Any) -> Any:
    """Les deux comptes de jetons additionnés (le flux vide a coûté aussi)."""
    if usage_a is None:
        return usage_b
    if usage_b is None:
        return usage_a
    from openai.types.completion_usage import CompletionUsage

    def n(u, cle):
        return int(getattr(u, cle, 0) or 0)

    return CompletionUsage(
        prompt_tokens=n(usage_a, "prompt_tokens") + n(usage_b, "prompt_tokens"),
        completion_tokens=n(usage_a, "completion_tokens") + n(usage_b, "completion_tokens"),
        total_tokens=n(usage_a, "total_tokens") + n(usage_b, "total_tokens"),
    )


def en_morceaux(reponse: Any, usage_d_avant: Any = None) -> list[Any]:
    """Une réponse sans flux, rendue comme les morceaux d'un flux (texte, appels d'outil,
    fin, compte de jetons)."""
    from openai.types.chat.chat_completion_chunk import (
        ChatCompletionChunk,
        Choice,
        ChoiceDelta,
        ChoiceDeltaToolCall,
        ChoiceDeltaToolCallFunction,
    )

    choix = (getattr(reponse, "choices", None) or [None])[0]
    message = getattr(choix, "message", None)
    contenu = getattr(message, "content", None) or None
    appels = [
        ChoiceDeltaToolCall(
            index=i,
            id=getattr(appel, "id", None),
            type="function",
            function=ChoiceDeltaToolCallFunction(
                name=getattr(appel.function, "name", None),
                arguments=getattr(appel.function, "arguments", None) or "{}",
            ),
        )
        for i, appel in enumerate(getattr(message, "tool_calls", None) or [])
    ]
    commun = {
        "id": getattr(reponse, "id", None) or "reprise",
        "created": int(getattr(reponse, "created", None) or time.time()),
        "model": getattr(reponse, "model", None) or "",
        "object": "chat.completion.chunk",
    }
    # Revue du 16/10 : Pipecat lit dans un morceau « appel d'outil, sinon texte », et seulement
    # le premier appel : un morceau pour le texte, puis un morceau par appel d'outil.
    morceaux = []
    if contenu:
        morceaux.append(
            ChatCompletionChunk(
                **commun,
                choices=[
                    Choice(
                        index=0,
                        delta=ChoiceDelta(role="assistant", content=contenu),
                        finish_reason=None,
                    )
                ],
            )
        )
    for appel in appels:
        morceaux.append(
            ChatCompletionChunk(
                **commun,
                choices=[
                    Choice(index=0, delta=ChoiceDelta(tool_calls=[appel]), finish_reason=None)
                ],
            )
        )
    morceaux.append(
        ChatCompletionChunk(
            **commun,
            choices=[
                Choice(
                    index=0,
                    delta=ChoiceDelta(),
                    finish_reason=getattr(choix, "finish_reason", None) or "stop",
                )
            ],
        )
    )
    usage = additionner(usage_d_avant, getattr(reponse, "usage", None))
    if usage is not None:
        morceaux.append(ChatCompletionChunk(**commun, choices=[], usage=usage))
    return morceaux


def morceaux_de_texte(texte: str) -> list[Any]:
    """Un texte dit comme une réponse du cerveau (un morceau de texte, puis la fin)."""
    from openai.types.chat.chat_completion_chunk import ChatCompletionChunk, Choice, ChoiceDelta

    commun = {"id": "repli", "created": int(time.time()), "model": "", "object": "chat.completion.chunk"}
    return [
        ChatCompletionChunk(
            **commun,
            choices=[Choice(index=0, delta=ChoiceDelta(role="assistant", content=texte), finish_reason=None)],
        ),
        ChatCompletionChunk(
            **commun, choices=[Choice(index=0, delta=ChoiceDelta(), finish_reason="stop")]
        ),
    ]


class FluxRepris:
    """Le flux du cerveau, relancé une fois sans flux s'il finit vide alors que des jetons
    ont été générés."""

    def __init__(self, flux: Any, relancer, l_appelant_attend=None):
        self._flux = flux
        self._relancer = relancer
        self._l_appelant_attend = l_appelant_attend

    def __aiter__(self):
        return self._parcourir()

    async def _parcourir(self):
        tenus: list[Any] = []
        quelque_chose = False
        jetons = 0
        usage_d_avant = None
        async for morceau in self._flux:
            if quelque_chose:
                yield morceau
                continue
            jetons = max(jetons, jetons_generes(morceau))
            if getattr(morceau, "usage", None) is not None:
                usage_d_avant = morceau.usage
            if porte_quelque_chose(morceau):
                quelque_chose = True
                for tenu in tenus:
                    yield tenu
                tenus = []
                yield morceau
            else:
                tenus.append(morceau)
        if quelque_chose:
            return
        if jetons <= 0 and not self._attend():
            for tenu in tenus:
                yield tenu
            return
        reprise = None
        try:
            reprise = await self._relancer()
        except Exception as erreur:  # noqa: BLE001 -- jamais à la place du service
            logger.warning(f"[cerveau] relance sans flux en échec : {erreur!r}")
        if reprise is not None:
            morceaux = en_morceaux(reprise, usage_d_avant)
            if any(porte_quelque_chose(m) for m in morceaux):
                logger.warning(
                    f"[cerveau] flux vide ({jetons} jetons comptés) : réponse rendue par la "
                    "relance sans flux"
                )
                for morceau in morceaux:
                    yield morceau
                return
        if self._attend():
            logger.warning(
                f"[cerveau] flux vide ({jetons} jetons comptés), relance vide : phrase de repli"
            )
            for morceau in morceaux_de_texte(PHRASE_DE_REPLI):
                yield morceau
            return
        logger.warning(f"[cerveau] flux vide ({jetons} jetons comptés), relance vide")
        for tenu in tenus:
            yield tenu

    def _attend(self) -> bool:
        try:
            return bool(self._l_appelant_attend is not None and self._l_appelant_attend())
        except Exception:  # noqa: BLE001
            return False

    async def close(self):
        fermer = getattr(self._flux, "close", None) or getattr(self._flux, "aclose", None)
        if fermer is not None:
            await fermer()


class RepriseSansFluxMixin:
    """Mêlé au cerveau compatible OpenAI (``DograhOpenAILLMService``), sous la trace : la
    trace voit le flux tel que l'agent le reçoit, relance comprise."""

    async def get_chat_completions(self, context):  # type: ignore[override]
        # Revue du 16/10 : la relance part avec la réflexion de secours si cette réponse-ci
        # l'avait (l'armement est consommé par la requête d'origine), et se dit dans la trace.
        secours = bool(getattr(self, "_mark_relance_armee", False))
        entree = getattr(self, "_mark_entree_en_cours", None)
        flux = await super().get_chat_completions(context)  # type: ignore[misc]

        async def relancer():
            if isinstance(entree, dict):
                entree["relance_sans_flux"] = True
            delai = getattr(self, "mark_delai_modele_s", None)
            if delai:
                # Revue du 16/10 : la relance a le même délai de garde que la requête d'origine ;
                # dépassé, l'erreur est rattrapée et la phrase de repli est dite.
                return await asyncio.wait_for(requeter(), delai)
            return await requeter()

        async def requeter():
            from pipecat.utils.types import assert_given

            adapter = self.get_llm_adapter()  # type: ignore[attr-defined]
            params = adapter.get_llm_invocation_params(
                context,
                system_instruction=assert_given(self._settings.system_instruction),  # type: ignore[attr-defined]
                convert_developer_to_user=not self.supports_developer_role,  # type: ignore[attr-defined]
            )
            # Par l'attribut de l'instance : les enveloppes posées par le moteur (l'état de
            # la fiche) s'appliquent à la relance comme à la requête d'origine.
            avant = getattr(self, "_mark_secours_en_cours", False)
            self._mark_secours_en_cours = secours
            try:
                requete = dict(self.build_chat_completion_params(params))  # type: ignore[attr-defined]
            finally:
                self._mark_secours_en_cours = avant
            requete["stream"] = False
            requete.pop("stream_options", None)
            return await self._client.chat.completions.create(**requete)  # type: ignore[attr-defined]

        def l_appelant_attend() -> bool:
            messages = [
                m for m in (getattr(context, "messages", None) or []) if isinstance(m, dict)
            ]
            return bool(messages) and messages[-1].get("role") == "user"

        return FluxRepris(flux, relancer, l_appelant_attend)
