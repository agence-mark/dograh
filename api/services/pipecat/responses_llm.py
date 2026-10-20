"""[.mark] Le cerveau compatible OpenAI par l'API Responses (chantier orchestrateur-trois-cerveaux, lot 1, D11 et D19).

Pourquoi : chez Scaleway, gpt-oss-120b ne porte des outils que par l'API Responses
(``POST <base_url>/responses``). Le fournisseur compatible OpenAI de la fabrique a donc un champ
« API » (``chat_completions`` par défaut, ``responses``) ; ce module est le service construit quand
l'écran dit ``responses``. Il vaut pour les trois cerveaux (conversation, greffier, travail de fond) :
tous passent par la même fabrique.

Base : ``OpenAIResponsesHttpLLMService`` de Pipecat (HTTP en flux, ``base_url`` honoré), jamais
``OpenAIResponsesLLMService`` : celui-ci ouvre un WebSocket vers ``wss://api.openai.com/v1/responses``,
inutilisable chez Scaleway (constat du lot 0). ⛔ Aucun fichier de ``pipecat/`` n'est touché (R2) :
tout ce que Pipecat ne fait pas pour la variante Responses est fait ici.

Ce que le service chat completions (``DograhOpenAILLMService``) porte, et son pendant ici
------------------------------------------------------------------------------------------
Les points d'accroche du fork portent des noms de chat completions (``get_chat_completions``,
``build_chat_completion_params``) : la fiche montrée à chaque requête, la trace, le garde du délai,
la réflexion de secours les enveloppent par ces noms. Le service Responses les **garde** :

- ``get_chat_completions(context)`` rend le flux de la réponse (des événements Responses) ;
- ``build_chat_completion_params(invocation)`` rend les paramètres de la requête (``input`` à la
  place de ``messages``) ;
- ``_build_response_params`` de Pipecat, appelé par ``_process_context`` AVANT la requête, ne
  construit rien pendant une réponse de conversation : il laisse la requête à
  ``get_chat_completions`` (``_Differe``), pour que la variable de contexte de la fiche soit posée
  avant la construction, exactement comme en chat completions.

Les trois couches .mark et leur pendant :

- main passée (``MainPasseeResponsesMixin``) : un agent qui a passé la main rend un flux vide ; une
  requête qui finit par une réplique de l'assistant reçoit la note de passation (dans ``input``) ;
- texte du cerveau (``TexteDuCerveauResponsesMixin``) : mêmes règles que ``texte_du_cerveau.py``
  (appel écrit en texte, crochets), appliquées au texte des événements ; le travail est celui de
  ``FluxNettoye``, les événements y passent sous la forme de morceaux minimaux ;
- reprise sans flux (``RepriseSansFluxResponsesMixin``) : un flux sans texte ni appel d'outil est
  relancé une fois sans flux (``responses.create`` sans ``stream``), sinon phrase de repli.

Et les détails que le service chat completions de Pipecat porte et que la variante Responses n'a pas :

- les appels de fonction d'une réponse passent par ``_run_or_defer_function_calls`` : un appel de
  passage de nœud attend la fin de la voix (``BotStoppedSpeakingFrame``) quand la réponse a dit du
  texte ; sans cela le graphe changerait d'étape en pleine phrase ;
- ``include: ["reasoning.encrypted_content"]``, que Pipecat ajoute dès qu'un raisonnement est réglé,
  est **refusé par Scaleway** (400, constaté le 17/10) : retiré hors d'OpenAI même.

Réglages d'échantillonnage : température, ``top_p`` et longueur maximale ont leur pendant Responses
(``max_output_tokens``). La graine et les pénalités n'existent pas dans l'API : elles partent dans
``extra_body`` quand l'écran les règle (le fournisseur les prend ou les ignore), jamais autrement.

⛔ Ne lève jamais à la place du service : chaque couche rend le flux d'origine en cas d'erreur.
Le format garanti du greffier (lot 5 bis) passera par ``text.format`` de la requête : rien ici ne le
ferme, ``build_chat_completion_params`` rend un dictionnaire que le greffier complète.
"""

from __future__ import annotations

import asyncio
import contextvars
import time
from typing import Any
from urllib.parse import urlparse

from loguru import logger
from openai.types.responses import (
    ResponseCompletedEvent,
    ResponseFunctionCallArgumentsDoneEvent,
    ResponseFunctionToolCall,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseTextDeltaEvent,
)

from api.services.groupe.passations import NOTE_DE_PASSATION
from api.services.panne.delai_modele import DelaiModeleMixin
from api.services.pipecat.main_passee import ATTRIBUT as ATTRIBUT_MAIN_PASSEE
from api.services.pipecat.main_passee import _FluxVide
from api.services.pipecat.reponse_avalee import phrase_de_repli
from api.services.pipecat.replique_inachevee import ReflexionDeRelanceMixin
from api.services.pipecat.texte_du_cerveau import FluxNettoye, _noms_des_outils
from api.services.pipecat.trace_modele import TraceModeleMixin
from api.services.workflow.porte_parlee import FLECHE
from pipecat.frames.frames import BotStoppedSpeakingFrame, FunctionCallsFromLLMInfoFrame
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import FunctionCallFromLLM
from pipecat.services.openai.responses.llm import OpenAIResponsesHttpLLMService
from pipecat.utils.text.alnum_utils import has_alnum
from pipecat.utils.types import assert_given

TYPE_TEXTE = "response.output_text.delta"
TYPE_FIN = "response.completed"
TYPE_ITEM_AJOUTE = "response.output_item.added"

# La réponse de conversation en cours dans cette tâche (voir ``_Differe``).
_CONTEXTE_DE_CONVERSATION: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "mark_responses_contexte", default=None
)


# --- Les événements Responses que le code fabrique -------------------------------------------


def evenement_de_texte(texte: str) -> ResponseTextDeltaEvent:
    return ResponseTextDeltaEvent.model_construct(
        type=TYPE_TEXTE,
        delta=texte,
        content_index=0,
        item_id="mark",
        output_index=0,
        sequence_number=0,
        logprobs=[],
    )


def evenements_d_appel(call_id: str, nom: str, arguments: str, index: int = 0) -> list[Any]:
    """Un appel d'outil comme le flux Responses le raconte : l'item ajouté, ses arguments
    finis, l'item fini (c'est ce que ``_process_context`` de Pipecat lit)."""
    arguments = arguments or "{}"
    item_id = f"fc_{call_id}"
    complet = ResponseFunctionToolCall(
        arguments=arguments,
        call_id=call_id,
        name=nom,
        type="function_call",
        id=item_id,
        status="completed",
    )
    commence = complet.model_copy(update={"arguments": ""})
    return [
        ResponseOutputItemAddedEvent.model_construct(
            type=TYPE_ITEM_AJOUTE, item=commence, output_index=index, sequence_number=0
        ),
        ResponseFunctionCallArgumentsDoneEvent.model_construct(
            type="response.function_call_arguments.done",
            item_id=item_id,
            arguments=arguments,
            name=nom,
            output_index=index,
            sequence_number=0,
        ),
        ResponseOutputItemDoneEvent.model_construct(
            type="response.output_item.done", item=complet, output_index=index, sequence_number=0
        ),
    ]


def evenements_de_reponse(reponse: Any) -> list[Any]:
    """Une réponse sans flux, rendue comme les événements d'un flux (texte, appels d'outil,
    fin avec le compte de jetons)."""
    evenements: list[Any] = []
    texte = getattr(reponse, "output_text", None)
    if texte:
        evenements.append(evenement_de_texte(texte))
    for i, item in enumerate(getattr(reponse, "output", None) or []):
        if getattr(item, "type", None) == "function_call":
            evenements += evenements_d_appel(
                getattr(item, "call_id", None) or f"appel-{int(time.time() * 1000)}-{i}",
                getattr(item, "name", "") or "",
                getattr(item, "arguments", None) or "{}",
                i,
            )
    evenements.append(
        ResponseCompletedEvent.model_construct(
            type=TYPE_FIN, response=reponse, sequence_number=0
        )
    )
    return evenements


def porte_quelque_chose(evenement: Any) -> bool:
    """L'événement porte-t-il du texte ou un appel d'outil ?"""
    type_ = getattr(evenement, "type", None)
    if type_ == TYPE_TEXTE:
        return bool(getattr(evenement, "delta", None))
    if type_ == TYPE_ITEM_AJOUTE:
        return getattr(getattr(evenement, "item", None), "type", None) == "function_call"
    return False


def jetons_generes(evenement: Any) -> int:
    if getattr(evenement, "type", None) != TYPE_FIN:
        return 0
    usage = getattr(getattr(evenement, "response", None), "usage", None)
    try:
        return int(getattr(usage, "output_tokens", 0) or 0)
    except (TypeError, ValueError):
        return 0


# --- Main passée ------------------------------------------------------------------------------


def avec_la_note(entrees: list) -> list:
    """Les éléments d'entrée de la requête, la note ajoutée si le dernier (hors consignes) est
    une réplique de l'assistant. Un appel d'outil ou son résultat n'ont pas de rôle : rien."""
    try:
        for entree in reversed(entrees):
            if not isinstance(entree, dict) or entree.get("role") in ("system", "developer"):
                continue
            if entree.get("role") == "assistant":
                return [*entrees, {"role": "user", "content": NOTE_DE_PASSATION}]
            return entrees
        return entrees
    except Exception:  # noqa: BLE001
        return entrees


class MainPasseeResponsesMixin:
    """Pendant Responses de ``MainPasseeMixin`` : un agent muet ne déclenche ni relance ni
    phrase de repli."""

    async def get_chat_completions(self, context):  # type: ignore[override]
        if getattr(self, ATTRIBUT_MAIN_PASSEE, False):
            logger.info("[passation] l'agent a passé la main : sa réponse n'est pas demandée")
            return _FluxVide()
        return await super().get_chat_completions(context)  # type: ignore[misc]

    def build_chat_completion_params(self, invocation_params):  # type: ignore[override]
        params = super().build_chat_completion_params(invocation_params)  # type: ignore[misc]
        entrees = params.get("input")
        if isinstance(entrees, list):
            complete = avec_la_note(entrees)
            if complete is not entrees:
                logger.info("[passation] requête finie par l'assistant : note ajoutée")
                params["input"] = complete
        return params


# --- Texte du cerveau -------------------------------------------------------------------------


class _Delta:
    def __init__(self, content: str):
        self.content = content

    def model_copy(self, update: dict | None = None) -> "_Delta":
        return _Delta((update or {}).get("content", self.content))


class _Choix:
    def __init__(self, delta: _Delta, finish_reason: Any = None):
        self.delta = delta
        self.finish_reason = finish_reason

    def model_copy(self, update: dict | None = None) -> "_Choix":
        update = update or {}
        return _Choix(
            update.get("delta", self.delta), update.get("finish_reason", self.finish_reason)
        )


class _Morceau:
    """Un événement Responses, vu par ``FluxNettoye`` comme un morceau de chat completions :
    le texte d'un delta, rien pour les autres. ``origine`` est l'événement d'où il vient."""

    def __init__(self, origine: Any, choices: list[_Choix]):
        self.origine = origine
        self.choices = choices

    def model_copy(self, update: dict | None = None) -> "_Morceau":
        return _Morceau(self.origine, (update or {}).get("choices", self.choices))


class _VersMorceaux:
    def __init__(self, flux: Any):
        self._flux = flux

    def __aiter__(self):
        return self._parcourir()

    async def _parcourir(self):
        async for evenement in self._flux:
            if getattr(evenement, "type", None) == TYPE_TEXTE:
                yield _Morceau(evenement, [_Choix(_Delta(evenement.delta))])
            else:
                yield _Morceau(evenement, [])

    async def close(self):
        fermer = getattr(self._flux, "close", None) or getattr(self._flux, "aclose", None)
        if fermer is not None:
            await fermer()


def _en_evenements(morceau: Any) -> list[Any]:
    """Ce que ``FluxNettoye`` rend, de nouveau en événements Responses."""
    if isinstance(morceau, _Morceau):
        if not morceau.choices:
            return [morceau.origine]
        texte = morceau.choices[0].delta.content
        if texte == getattr(morceau.origine, "delta", None):
            return [morceau.origine]
        return [morceau.origine.model_copy(update={"delta": texte})]
    # Un appel d'outil écrit en texte, rendu par ``FluxNettoye`` en morceau de chat completions.
    evenements: list[Any] = []
    for choix in getattr(morceau, "choices", None) or []:
        for appel in getattr(getattr(choix, "delta", None), "tool_calls", None) or []:
            fonction = getattr(appel, "function", None)
            evenements += evenements_d_appel(
                getattr(appel, "id", None) or f"ecrit-{int(time.time() * 1000)}",
                getattr(fonction, "name", "") or "",
                getattr(fonction, "arguments", None) or "{}",
                getattr(appel, "index", 0) or 0,
            )
    return evenements


class FluxNettoyeResponses:
    """Le flux du cerveau, sans appel écrit en texte ni passage entre crochets."""

    def __init__(self, flux: Any, outils: list[str], portes_dans_la_reponse: bool):
        self._flux = flux
        self._nettoye = FluxNettoye(_VersMorceaux(flux), outils, portes_dans_la_reponse)

    def __aiter__(self):
        return self._parcourir()

    async def _parcourir(self):
        async for morceau in self._nettoye:
            for evenement in _en_evenements(morceau):
                yield evenement

    async def close(self):
        fermer = getattr(self._flux, "close", None) or getattr(self._flux, "aclose", None)
        if fermer is not None:
            await fermer()


class TexteDuCerveauResponsesMixin:
    """Pendant Responses de ``TexteDuCerveauMixin`` (même consigne, mêmes outils déclarés)."""

    async def get_chat_completions(self, context):  # type: ignore[override]
        flux = await super().get_chat_completions(context)  # type: ignore[misc]
        try:
            consigne = str(getattr(getattr(self, "_settings", None), "system_instruction", "") or "")
            portes = FLECHE in consigne or any(
                isinstance(m, dict)
                and m.get("role") == "system"
                and FLECHE in str(m.get("content") or "")
                for m in (getattr(context, "messages", None) or [])
            )
            return FluxNettoyeResponses(flux, _noms_des_outils(context), portes)
        except Exception as erreur:  # noqa: BLE001 -- jamais à la place du service
            logger.warning(f"[cerveau] nettoyage du texte non posé : {erreur!r}")
            return flux


# --- Reprise sans flux ------------------------------------------------------------------------


class FluxReprisResponses:
    """Le flux du cerveau, relancé une fois sans flux s'il finit vide (ni texte ni appel d'outil)."""

    def __init__(self, flux: Any, relancer, l_appelant_attend=None, repli=None):
        self._flux = flux
        self._relancer = relancer
        self._l_appelant_attend = l_appelant_attend
        self._repli = repli

    def __aiter__(self):
        return self._parcourir()

    async def _parcourir(self):
        tenus: list[Any] = []
        quelque_chose = False
        jetons = 0
        async for evenement in self._flux:
            if quelque_chose:
                yield evenement
                continue
            jetons = max(jetons, jetons_generes(evenement))
            if porte_quelque_chose(evenement):
                quelque_chose = True
                for tenu in tenus:
                    yield tenu
                tenus = []
                yield evenement
            else:
                tenus.append(evenement)
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
            evenements = evenements_de_reponse(reprise)
            if any(porte_quelque_chose(e) for e in evenements):
                logger.warning(
                    f"[cerveau] flux vide ({jetons} jetons comptés) : réponse rendue par la "
                    "relance sans flux"
                )
                # Le flux vide a coûté aussi : sa fin (compte de jetons) part avant la relance.
                for tenu in tenus:
                    if getattr(tenu, "type", None) == TYPE_FIN:
                        yield tenu
                for evenement in evenements:
                    yield evenement
                return
        texte = self._repli() if self._attend() and self._repli is not None else None
        if texte:
            logger.warning(
                f"[cerveau] flux vide ({jetons} jetons comptés), relance vide : phrase de repli"
            )
            yield evenement_de_texte(texte)
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


class RepriseSansFluxResponsesMixin:
    """Pendant Responses de ``RepriseSansFluxMixin``, sous la trace : la trace voit le flux tel
    que l'agent le reçoit, relance comprise."""

    async def get_chat_completions(self, context):  # type: ignore[override]
        secours = bool(getattr(self, "_mark_relance_armee", False))
        entree = getattr(self, "_mark_entree_en_cours", None)
        flux = await super().get_chat_completions(context)  # type: ignore[misc]

        async def relancer():
            if isinstance(entree, dict):
                entree["relance_sans_flux"] = True
            delai = getattr(self, "mark_delai_modele_s", None)
            if delai:
                return await asyncio.wait_for(requeter(), delai)
            return await requeter()

        async def requeter():
            adapter = self.get_llm_adapter()  # type: ignore[attr-defined]
            invocation = adapter.get_llm_invocation_params(
                context,
                system_instruction=assert_given(self._settings.system_instruction),  # type: ignore[attr-defined]
            )
            avant = getattr(self, "_mark_secours_en_cours", False)
            self._mark_secours_en_cours = secours
            try:
                requete = dict(self.build_chat_completion_params(invocation))  # type: ignore[attr-defined]
            finally:
                self._mark_secours_en_cours = avant
            requete["stream"] = False
            return await self._client.responses.create(**requete)  # type: ignore[attr-defined]

        def l_appelant_attend() -> bool:
            messages = [
                m for m in (getattr(context, "messages", None) or []) if isinstance(m, dict)
            ]
            return bool(messages) and messages[-1].get("role") == "user"

        return FluxReprisResponses(
            flux, relancer, l_appelant_attend, lambda: phrase_de_repli(self)
        )


# --- Le service -------------------------------------------------------------------------------


class _Differe(dict):
    """Ce que ``_build_response_params`` rend pendant une réponse de conversation : les
    paramètres d'invocation, la requête elle-même étant construite par ``get_chat_completions``."""


class _AEmettre(list):
    """Liste vide qui porte les appels de fonction que la réponse vient d'achever
    (``appels``) : Pipecat les passe à ``run_function_calls``, qui les confie à
    ``_run_or_defer_function_calls`` comme le fait le service chat completions."""

    appels: list


class _MarkResponsesBase(OpenAIResponsesHttpLLMService):
    """Le service Responses HTTP, avec les noms de points d'accroche du fork (voir le module)."""

    mark_api = "responses"

    def __init__(
        self,
        *,
        prompt_cache_key: str | None = None,
        extra_body: dict | None = None,
        base_url: str | None = None,
        **kwargs,
    ):
        # Vide : aucune clé du tout, jamais une clé vide dans la requête.
        self._prompt_cache_key = prompt_cache_key or None
        self._mark_extra_body = dict(extra_body or {})
        # ``include`` est une demande propre à OpenAI (raisonnement chiffré à renvoyer) que
        # d'autres fournisseurs refusent en 400 : gardée chez OpenAI seulement.
        hote = urlparse(base_url or "https://api.openai.com/v1").hostname or ""
        self._mark_garde_include = hote == "openai.com" or hote.endswith(".openai.com")
        super().__init__(base_url=base_url, **kwargs)
        self._pending_node_transition_function_calls: list[FunctionCallFromLLM] = []
        self._mark_texte_genere = ""
        if hasattr(self, "_mark_enregistrer_evenements"):
            self._mark_enregistrer_evenements()  # type: ignore[attr-defined]

    # --- La requête ---

    def build_chat_completion_params(self, invocation_params) -> dict:  # noqa: D401
        """Les paramètres de la requête de conversation (le nom est celui de chat completions,
        que la fiche, la trace et le greffier enveloppent ou lisent)."""
        params = super()._build_response_params(invocation_params)
        if not self._mark_garde_include and "include" not in self._settings.extra:
            params.pop("include", None)
        if self._prompt_cache_key:
            params["prompt_cache_key"] = self._prompt_cache_key
        if self._mark_extra_body:
            params["extra_body"] = {**(params.get("extra_body") or {}), **self._mark_extra_body}
        return params

    def _build_response_params(self, invocation_params):  # type: ignore[override]
        if _CONTEXTE_DE_CONVERSATION.get() is not None:
            return _Differe(invocation_params)
        return self.build_chat_completion_params(invocation_params)

    async def get_chat_completions(self, context):
        """Le flux de la réponse (événements Responses) : construit la requête, puis l'envoie."""
        invocation = self.get_llm_adapter().get_llm_invocation_params(
            context, system_instruction=assert_given(self._settings.system_instruction)
        )
        params = self.build_chat_completion_params(invocation)
        return await super()._create_stream(params)

    async def _create_stream(self, params):  # type: ignore[override]
        if isinstance(params, _Differe):
            return await self.get_chat_completions(_CONTEXTE_DE_CONVERSATION.get())
        return await super()._create_stream(params)

    async def _process_context(self, context):  # type: ignore[override]
        if self._pending_node_transition_function_calls:
            logger.warning(
                f"{self}: discarding {len(self._pending_node_transition_function_calls)} deferred "
                "node-transition calls never released by TTS"
            )
        self._pending_node_transition_function_calls = []
        self._mark_texte_genere = ""
        jeton = _CONTEXTE_DE_CONVERSATION.set(context)
        try:
            await super()._process_context(context)
        finally:
            _CONTEXTE_DE_CONVERSATION.reset(jeton)

    # --- Les appels de fonction : ce que le service chat completions de Pipecat fait en plus ---

    async def _push_llm_text(self, text: str):  # type: ignore[override]
        self._mark_texte_genere += text
        await super()._push_llm_text(text)

    def _process_function_calls(self, context, function_calls):  # type: ignore[override]
        appels = super()._process_function_calls(context, function_calls)
        vide = _AEmettre()
        vide.appels = appels
        return vide

    async def run_function_calls(self, function_calls):  # type: ignore[override]
        if isinstance(function_calls, _AEmettre):
            appels = function_calls.appels
            if not appels:
                return
            await self.push_frame(
                FunctionCallsFromLLMInfoFrame(function_calls=appels),
                direction=FrameDirection.DOWNSTREAM,
            )
            await self._run_or_defer_function_calls(
                appels, text_generated=has_alnum(self._mark_texte_genere)
            )
            return
        await super().run_function_calls(function_calls)

    async def _run_or_defer_function_calls(
        self, function_calls: list[FunctionCallFromLLM], *, text_generated: bool
    ) -> None:
        """Un appel de passage de nœud attend la fin de la voix quand la réponse a dit du texte
        (copie du service chat completions de Pipecat, absente de la variante Responses)."""
        if self._speculation_gate.is_speculating:
            await self.run_function_calls(function_calls)
            return
        contient_un_passage = any(
            self._function_is_node_transition(fc.function_name) for fc in function_calls
        )
        if text_generated and contient_un_passage:
            self._pending_node_transition_function_calls = function_calls
            logger.debug(
                f"{self}: Deferring {len(function_calls)} node-transition function calls until after TTS"
            )
            return
        logger.debug(f"{self}: Executing {len(function_calls)} function calls")
        await self.run_function_calls(function_calls)

    async def _run_pending_node_transition_function_calls(self) -> None:
        if not self._pending_node_transition_function_calls:
            return
        function_calls = self._pending_node_transition_function_calls
        self._pending_node_transition_function_calls = []
        logger.debug(
            f"{self}: Executing {len(function_calls)} deferred node-transition function calls after TTS"
        )
        await self.run_function_calls(function_calls)

    async def process_frame(self, frame, direction):  # type: ignore[override]
        if isinstance(frame, BotStoppedSpeakingFrame):
            # Comme le service chat completions : le traitement du service, les appels différés,
            # puis le cadre suit son chemin.
            await super(OpenAIResponsesHttpLLMService, self).process_frame(frame, direction)
            await self._run_pending_node_transition_function_calls()
            await self.push_frame(frame, direction)
            return
        await super().process_frame(frame, direction)


class MarkOpenAIResponsesLLMService(
    TraceModeleMixin,
    MainPasseeResponsesMixin,
    TexteDuCerveauResponsesMixin,
    RepriseSansFluxResponsesMixin,
    ReflexionDeRelanceMixin,
    DelaiModeleMixin,
    _MarkResponsesBase,
):
    """[.mark] Le cerveau compatible OpenAI par l'API Responses : les mêmes couches .mark que
    ``DograhOpenAILLMService``, dans le même ordre (trace, main passée, texte du cerveau, reprise
    sans flux, réflexion de secours, garde du délai)."""

    def _mark_appliquer_le_secours(self, params: dict) -> dict:
        """Pendant Responses de la réflexion de secours : la clé est ``reasoning.effort``."""
        if self._mark_secours_en_cours and self.mark_reflexion_de_relance:
            params["reasoning"] = {
                **(params.get("reasoning") or {}),
                "effort": self.mark_reflexion_de_relance,
            }
        return params

    def build_chat_completion_params(self, invocation_params) -> dict:  # noqa: D401
        params = super().build_chat_completion_params(invocation_params)
        # D10 de repliques-coupees : la relance d'une réplique inachevée, seule, part avec la
        # réflexion de secours de l'agent.
        return self._mark_appliquer_le_secours(params)
