"""One engine-owned handoff task; prepare privately, then commit synchronously."""

from __future__ import annotations

import asyncio
import time
import uuid
from builtins import BaseExceptionGroup
from contextlib import suppress
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger
from pipecat.frames.frames import LLMMessagesAppendFrame

from api.services.pipecat.agent_runtime_factory import AgentBuildError
from api.services.pipecat.audio_playback import play_hold_audio_loop
from api.services.phrases.catalogue import PASSATION_TARDE
from api.services.pipecat.main_passee import rendre_la_parole
from api.services.workflow.agent_handoff_context import (
    build_handoff_snapshot,
    conversation_messages,
)
from api.services.workflow.agent_runtime import new_visit_id
from api.services.groupe.passations import (
    NOTE_DE_PASSATION,
    finit_par_l_assistant,
    l_appelant_a_parle_en_dernier,
    tracer_passation,
)
from api.services.groupe.reglages_passation import (
    Attente,
    attente_de,
    chemin_du_son,
    dernieres_a_garder,
    passation_courte,
)

TRANSFER_PREPARE_TIMEOUT_SECONDS = 20.0
TRANSFER_ACTIVATION_TIMEOUT_SECONDS = 5.0
TRANSFER_MIN_HOLD_SECONDS = 1.2
# [.mark] Au plus ce que la passation attend la fin d'une phrase pont déjà commencée.
ATTENTE_FIN_PHRASE_PONT_S = 2.0


def _noeud_d_ouverture(destination) -> str:
    """[.mark] Lot 2 d'orchestrateur-trois-cerveaux : l'étape où l'agent appelé a été préparé
    (``prepare_agent`` : l'étape de départ, ou l'étape de retour de l'accueil). Sans étape lisible
    (maquette, agent non préparé) : l'étape de départ, comme avant."""
    courante = getattr(getattr(destination, "current_node", None), "id", None)
    return courante if isinstance(courante, str) and courante else destination.workflow.start_node_id


class TransferPhase(str, Enum):
    IDLE = "idle"
    ANNOUNCING = "announcing"
    PREPARING = "preparing"
    COMMITTING = "committing"
    OPENING = "opening"


@dataclass
class TransferRequest:
    destination_workflow_id: int
    destination_label: str
    origin_visit_id: str
    announcement: str | None = None
    play_greeting: bool = True
    request_id: str = field(default_factory=lambda: f"xfer-{uuid.uuid4().hex[:10]}")
    cancelled_reason: str | None = None
    # [.mark] Chantier agents-specialises (lot 2). Tous les défauts = comportement d'avant.
    # ``silencieuse`` : ni annonce, ni musique, ni durée minimale (retour au principal).
    silencieuse: bool = False
    # ``sans_resume`` : l'agent appelé reçoit l'historique filtré, sans appel au modèle.
    sans_resume: bool = False
    # ``ouverture`` : « toujours » (l'agent appelé ouvre, comme avant) ou
    # « si_l_appelant_attend » (il ne parle que si le dernier mot est à l'appelant).
    ouverture: str = "toujours"
    # La raison tracée dans ``passations`` (le nom de l'outil, ou « retour »).
    raison: str | None = None
    # Après le banc du 16/10 : l'agent appelé ne reçoit que la conversation à partir de cet
    # indice (le retour au principal : la dernière étape du spécialisé). ``None`` : toute.
    depuis: int | None = None
    # Lot 2 d'orchestrateur-trois-cerveaux (D1) : l'appel revient sur l'étape de retour de l'accueil
    # (si son graphe en a une), au lieu de l'étape de départ. ``False`` : comme avant.
    etape_de_retour: bool = False
    # Correctifs après le banc commun, lot 1 (K1) : la demande de l'appelant en une phrase, donnée à
    # l'outil de passation ; reprise dans la note remise au collègue. ``None`` : comme avant.
    demande: str | None = None
    # Lot 1 (K4) : le retour a été demandé pour finir l'appel (filet de fin, ou porte ``fin`` réécrite
    # en ``retour``) : l'accueil prend sa sortie ``fin`` sans tour de modèle. ``False`` : comme avant.
    fin_demandee: bool = False
    # fiabilite-de-la-conversation, lot A : le retour tombe sur CETTE étape de l'accueil (identifiant du nœud), choisie à
    # l'écran pour la deuxième impasse. ``None`` : l'étape de retour, ou celle de départ, comme avant.
    etape_cible: str | None = None

    @property
    def cancelled(self) -> bool:
        return self.cancelled_reason is not None


class AgentTransferCoordinator:
    """Sequence handoffs beneath the call engine, one request at a time."""

    def __init__(self, engine):
        self._engine = engine
        self._phase = TransferPhase.IDLE
        self._request: TransferRequest | None = None
        self._task: asyncio.Task | None = None
        self._hold_stop: asyncio.Event | None = None
        self._hold_task: asyncio.Task | None = None
        # [.mark] La phrase pont : tâche différée, annulée si la passation finit avant le délai.
        self._phrase_task: asyncio.Task | None = None
        self._phrase_en_cours = False

    @property
    def phase(self):
        return self._phase

    @property
    def in_progress(self):
        return self._request is not None

    @property
    def completed(self):
        return list(self._engine._transfer_outcomes)

    def accept(self, request):
        if (
            self.in_progress
            or self._engine.is_call_disposed()
            or request.origin_visit_id != self._engine.active_agent.visit_id
        ):
            return False
        self._request = request
        self._phase = TransferPhase.ANNOUNCING
        self._engine.call_monitor.suspend()
        # [.mark] Lot 3 (D7, D18) : passation demandee, debut de la mesure du premier octet de voix.
        mesure = getattr(self._engine, "mesure_passation", None)
        if mesure is not None:
            mesure.demandee(request.request_id)
        return True

    def start(self, request, *, context_ready=None) -> bool:
        """[.mark] Rend ``True`` si la passation est partie (D1 : l'agent d'origine se tait)."""
        if self._request is not request or request.cancelled:
            return False
        self._task = asyncio.create_task(
            self._run(request, context_ready=context_ready),
            name=f"transfer:{request.request_id}",
        )
        self._task.add_done_callback(self._report_error)
        return True

    @staticmethod
    def _report_error(task):
        if not task.cancelled() and task.exception() is not None:
            logger.opt(exception=task.exception()).error(
                "Agent handoff failed during cleanup"
            )

    async def invalidate(self, reason):
        if self._request is not None:
            self._request.cancelled_reason = reason
        task = self._task
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await self._annuler_phrase_pont(attendre_la_fin=False)
        await self._stop_hold_audio()
        self._request = None
        self._phase = TransferPhase.IDLE

    def _check_current(self, request):
        if request.cancelled or self._engine.is_call_disposed():
            raise asyncio.CancelledError
        if self._request is not request:
            raise AgentBuildError("stale_request", "The handoff is no longer current")

    async def _run(self, request, *, context_ready=None):
        engine = self._engine
        source = engine.active_agent
        destination = None
        committed = False
        outcome = "completed"
        try:
            if source.visit_id != request.origin_visit_id:
                raise AgentBuildError("stale_origin", "The requesting visit has ended")
            if context_ready is not None:
                await asyncio.wait_for(context_ready.wait(), timeout=5)
            await self._announce(request, source)
            self._check_current(request)
            # [.mark] Au clavier (aucune sortie audio) ou pour un retour au principal :
            # l'agent est mis en attente, sans musique ni durée minimale. Lot 6 (A6) : vers
            # un agent DÉJÀ CONSTRUIT (le principal resté chaud), aucune musique et aucune
            # durée minimale, quel que soit le réglage (il ne vaut que pour un agent à
            # construire) ; sinon le réglage ``attente`` du principal (son, durée, où).
            reglage = attente_de(getattr(engine, "reglages_appel", None))
            deja_construit = (
                engine.principal_chaud_pour(request.destination_workflow_id) is not None
            )
            attente = not (
                request.silencieuse
                or self._sans_sortie_audio()
                or deja_construit
                or not reglage.passation
                or reglage.sans_son
            )
            duree_min = (
                TRANSFER_MIN_HOLD_SECONDS
                if reglage.duree_min_s is None
                else reglage.duree_min_s
            )
            if attente:
                await self._begin_hold(request, source, reglage)
            else:
                await engine.deactivate_agent(source)
            hold_started = time.monotonic()
            # [.mark] La phrase pont : un filet si la passation dure. Jamais pour un retour
            # silencieux, jamais au clavier (pas de voix), jamais vers un agent déjà construit
            # (le principal chaud revient à l'instant) ; vide = désactivée.
            # Fiabilite-orchestration, lot 4 bis (F17) : la phrase est la règle « la passation
            # tarde » de l'agent qui passe la main (étape, agent, principal ; l'ancien réglage
            # ``attente.phrase_pont`` du principal est repris tel quel).
            pont = self._phrase_pont_en_vigueur(source)
            if (
                pont is not None
                and not (
                    request.silencieuse or self._sans_sortie_audio() or deja_construit
                )
            ):
                self._phrase_task = asyncio.create_task(
                    self._phrase_pont(request, source, reglage, pont, avec_son=attente),
                    name=f"phrase-pont:{request.request_id}",
                )

            async def prepare():
                nonlocal destination
                destination = await engine.build_agent(
                    workflow_id=request.destination_workflow_id, visit_id=new_visit_id()
                )
                if not await destination.wait_until_started():
                    raise AgentBuildError(
                        "destination_not_ready", "Destination did not start"
                    )
                await engine.prepare_agent(destination)
                # Ready and activated while the call boundary still blocks all
                # candidate input/output. No shared prompt or tools change yet.
                if not await engine.activate_agent(
                    destination, timeout=TRANSFER_ACTIVATION_TIMEOUT_SECONDS
                ):
                    raise AgentBuildError(
                        "activation_failed", "Destination did not activate"
                    )
                if destination.error:
                    raise AgentBuildError("destination_unusable", destination.error)

            async with asyncio.timeout(TRANSFER_PREPARE_TIMEOUT_SECONDS):
                self._phase = TransferPhase.PREPARING
                await engine.pause_background_context_writers()
                # [.mark] Lot 6 (P5) : une conversation courte passe sans appel au modèle de
                # résumé (réglage ``passation_sans_resume_jusqua``, 40 par défaut dans un groupe).
                resumer = not request.sans_resume
                try:
                    if resumer and engine.context is not None:
                        nombre = len(conversation_messages(engine.context.get_messages()))
                        if passation_courte(nombre, getattr(engine, "reglages_appel", None)):
                            resumer = False
                            logger.info(
                                f"[transfer] {request.request_id}: {nombre} messages, "
                                "historique rendu sans résumé"
                            )
                except Exception as e:  # noqa: BLE001 -- jamais une raison de rater la passation
                    logger.warning(f"[transfer] décompte des messages illisible : {e!r}")
                async with asyncio.TaskGroup() as group:
                    group.create_task(prepare())
                    compact = group.create_task(
                        build_handoff_snapshot(
                            engine.context,
                            source.inference_llm,
                            request_id=request.request_id,
                            # Resolved here, in the parent task: the compaction
                            # task has no ambient span of its own to inherit.
                            parent_context=engine._get_otel_context(),
                            resumer=resumer,
                            depuis=request.depuis,
                            dernieres=dernieres_a_garder(
                                getattr(engine, "reglages_appel", None)
                            ),
                        )
                    )
                snapshot = compact.result()

            # [.mark] Arrivée sur un transfert d'appel, entreprise ouverte : le code dit lui-même
            # la mise en relation (réglage ``transfert_humain.phrase_mise_en_relation``). Décidé
            # ICI, avant de couper le son d'attente (trois lectures en base : l'appelant ne doit pas
            # les attendre en silence) et avant le commit ; appliqué après l'ouverture. Jamais au
            # clavier, jamais pour un retour silencieux au principal.
            fige = None
            figer = getattr(engine, "transfert_fige_a_l_ouverture", None)
            if (
                figer is not None
                and not self._sans_sortie_audio()
                and not request.silencieuse
            ):
                fige = await figer(destination, _noeud_d_ouverture(destination))
            # La passation est prête : une phrase pont pas encore dite ne le sera plus ; une
            # phrase en cours se termine (jamais coupée en plein mot).
            await self._annuler_phrase_pont()
            if attente:
                await asyncio.sleep(
                    max(0, duree_min - (time.monotonic() - hold_started))
                )
            await self._stop_hold_audio()
            if not self._sans_sortie_audio():
                await engine.drain_call_pipeline()
            self._check_current(request)
            if destination.error:
                raise AgentBuildError("destination_unusable", destination.error)
            self._phase = TransferPhase.COMMITTING
            engine.commit_agent(destination, snapshot)
            committed = True
            self._phase = TransferPhase.OPENING
            engine.call_monitor.resume()
            await engine.notify_agent_entered(destination)
            # [.mark] Lot 2 d'orchestrateur-trois-cerveaux : l'étape où l'agent appelé a été préparé
            # (l'étape de départ, ou l'étape de retour de l'accueil), jamais refaite ici.
            start_node_id = _noeud_d_ouverture(destination)
            # [.mark] Lot 1 (K4) : un retour demandé pour finir l'appel : l'accueil prend sa sortie
            # ``fin`` sans tour de modèle. Au clavier (pas de voix à dire), le tour se joue comme avant.
            if (
                request.fin_demandee
                and not self._sans_sortie_audio()
                and await engine.fin_directe_de_l_accueil(destination, start_node_id)
            ):
                outcome = "completed"
                return
            # [.mark] « si_l_appelant_attend » : l'agent appelé ne parle que si le
            # dernier mot de la conversation est à l'appelant (sinon il attend sa réponse).
            parler = request.ouverture != "si_l_appelant_attend" or (
                l_appelant_a_parle_en_dernier(engine.context.get_messages())
            )
            fige = fige if parler else None
            if parler and finit_par_l_assistant(engine.context.get_messages()):
                # [.mark] D1 : l'ouverture ne part jamais sur un message de l'assistant.
                engine.context.add_message({"role": "user", "content": NOTE_DE_PASSATION})
            ouverture = {
                "node_id": start_node_id,
                "previous_node_id": None if request.play_greeting else start_node_id,
                # La phrase figée remplace le tour du modèle (il ne parle que si le transfert échoue).
                "generate_if_no_greeting": parler and fige is None,
            }
            if self._sans_sortie_audio():
                # [.mark] Au clavier, le modèle de l'agent appelé n'est pas dans le
                # circuit du tour : son ouverture est jouée au passage suivant.
                engine.ouverture_differee = ouverture
            else:
                resultat = await engine.queue_node_opening(
                    **ouverture, origin_visit_id=destination.visit_id
                )
                # [.mark] Lot 3 (A7) : un agent appelé dont la première étape porte un
                # outil de transfert commence par le transfert (entreprise ouverte).
                if fige is not None and getattr(resultat, "action", None) != "greeting":
                    # ``""`` : l'outil dit son message en partant ; le transfert attend alors
                    # ce que l'ouverture joue déjà (``resultat.playback``).
                    await engine.dire_puis_transferer_a_l_ouverture(
                        destination, start_node_id, fige, apres=getattr(resultat, "playback", None)
                    )
                else:
                    # Aucune phrase figée, ou l'étape d'arrivée a son message d'accueil : il est dit
                    # et le transfert part ensuite (le comportement d'avant), jamais les deux phrases.
                    garantir = getattr(engine, "garantir_a_l_ouverture", None)
                    if garantir is not None:
                        garantir(destination, start_node_id, getattr(resultat, "playback", None))
        except asyncio.CancelledError:
            outcome = request.cancelled_reason or "cancelled"
            raise
        except Exception as error:
            while isinstance(error, BaseExceptionGroup):
                error = error.exceptions[0]
            outcome = (
                error.reason
                if isinstance(error, AgentBuildError)
                else (
                    "prepare_timeout"
                    if isinstance(error, TimeoutError)
                    else "opening_failed"
                    if committed
                    else "internal_error"
                )
            )
            logger.opt(exception=error).warning(
                f"[transfer] {request.request_id}: {outcome}"
            )
        finally:
            try:
                await self._annuler_phrase_pont(attendre_la_fin=False)
                await self._stop_hold_audio()
                if committed:
                    # [.mark] Lot 6 (A5) : le principal d'un groupe reste chaud (désactivé,
                    # jamais libéré) ; un agent seul est libéré exactement comme avant.
                    if not engine.garder_chaud(source):
                        await source.retire("transferred")
                elif destination is not None:
                    if destination is engine.__dict__.get("_principal_chaud"):
                        # Un principal chaud n'est JAMAIS avorté : il reste ouvert pour le
                        # retour suivant ; on le remet hors de la conversation s'il y était entré.
                        try:
                            if destination.worker is not None and destination.worker.active:
                                await engine.deactivate_agent(destination)
                        except Exception as e:  # noqa: BLE001
                            logger.warning(f"[transfer] principal chaud non remis en attente : {e!r}")
                        finally:
                            engine.discard_pending_agent(destination)
                    else:
                        try:
                            await destination.abort("transfer abandoned")
                        finally:
                            engine.discard_pending_agent(destination)
                # The source and its shared conversation were never replaced.
                if not committed and not engine.is_call_disposed():
                    if await engine.activate_agent(
                        source, timeout=TRANSFER_ACTIVATION_TIMEOUT_SECONDS
                    ):
                        engine._agent_on_hold = False
            finally:
                self._finish(
                    request, outcome, source, destination if committed else None
                )

        if not committed and engine.agent_can_act(source):
            engine.expect_response()
            await source.queue_frame(
                LLMMessagesAppendFrame(
                    [
                        {
                            "role": "user",
                            "content": (
                                f"System note: the transfer to {request.destination_label} could not be completed. "
                                "You are still speaking with the caller. Apologize briefly for the wait "
                                "and continue helping them yourself."
                            ),
                        }
                    ],
                    run_llm=True,
                )
            )

    def _sans_sortie_audio(self) -> bool:
        """[.mark] Le clavier n'a ni voix ni musique (``PipecatEngine.sans_sortie_audio``)."""
        return bool(getattr(self._engine, "sans_sortie_audio", False))

    async def _announce(self, request, source):
        engine = self._engine
        if request.announcement and not (
            request.silencieuse or self._sans_sortie_audio()
        ):
            # The assistant turn logs context speech; logging it here duplicates it.
            speech = await engine.queue_speech(
                request.announcement,
                append_to_context=True,
                persist_to_logs=False,
                mute_user=True,
            )
            await speech.wait()
        # Also drain when the tool has no announcement.
        await source.cancel_tools()
        if not self._sans_sortie_audio():
            await engine.drain_call_pipeline()

    async def _begin_hold(self, request, source, reglage: Attente | None = None):
        await self._engine.deactivate_agent(source)
        self._start_hold_audio(request, reglage)

    def _start_hold_audio(self, request, reglage: Attente | None = None):
        self._hold_stop = asyncio.Event()
        stop = self._hold_stop
        reglage = reglage or Attente()

        async def jouer():
            # [.mark] Lot 6 (A6) : le son déposé du réglage ``attente`` (mis en cache local,
            # comme le bruit d'ambiance) ; sans lui, ou s'il ne se charge pas, la sonnerie d'avant.
            options = {}
            if reglage.fichier is not None:
                chemin = await chemin_du_son(reglage, self._engine.hold_audio_sample_rate)
                if chemin:
                    options["audio_file"] = chemin
            await play_hold_audio_loop(
                stop_event=stop,
                sample_rate=self._engine.hold_audio_sample_rate,
                queue_frame=self._engine.transport_output_queue_frame,
                **options,
            )

        self._hold_task = asyncio.create_task(jouer(), name=f"hold:{request.request_id}")

    def _phrase_pont_en_vigueur(self, source):
        """La règle « la passation tarde » en vigueur pour ``source``, si elle se dit."""
        diseur = getattr(self._engine, "phrases", None)
        if diseur is None:
            return None
        try:
            pont = diseur.phrase(PASSATION_TARDE, source)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[transfer] phrase pont illisible : {e!r}")
            return None
        return pont if pont is not None and pont.dite else None

    async def _phrase_pont(
        self, request, source, reglage: Attente, pont, *, avec_son: bool
    ):
        """[.mark] La phrase pont, dite par la voix de l'APPEL si la passation n'est pas commise
        après le délai de la règle. Une seule fois. Le son d'attente se tait le temps de la
        phrase, puis reprend. ⛔ Ne lève jamais.

        Lot 3 d'orchestrateur-trois-cerveaux (D7) : la voix est celle de l'appel, plus celle de
        l'agent qui passe la main. Pendant la passation cet agent est « en attente » (désactivé,
        ``selected_visit_id`` vaut ``None``) : la phrase prend donc la route locale du pont
        (``PipecatEngine.queue_speech``), directement à la voix. L'agent source ne reçoit rien et
        ne dit rien, de bout en bout.

        Fiabilite-orchestration, lot 4 bis (F24, F25) : la phrase passe par le diseur (verrous,
        trace, variantes) ; son délai ne court que pendant l'attente du système, jamais pendant
        que l'appelant parle, et repart à la fin de sa réplique ; l'appelant peut la couper."""
        engine = self._engine
        diseur = engine.phrases
        son_coupe = False

        async def avant() -> None:
            nonlocal son_coupe
            self._phrase_en_cours = True
            if avec_son:
                son_coupe = True
                await self._stop_hold_audio()

        async def apres(_parole) -> None:
            # Comme ``_announce`` : tout ce qui est en vol arrive à l'appelant avant que l'attente
            # se referme ; puis, entre deux redites, le son d'attente reprend.
            nonlocal son_coupe
            await engine.drain_call_pipeline()
            self._phrase_en_cours = False
            if son_coupe and self._passation_en_cours(request) and self._hold_stop is None:
                self._start_hold_audio(request, reglage)
                son_coupe = False

        try:
            # correctifs-apres-banc-v4 (lot 4) : la veille générique du diseur (délai, redites toutes les
            # ``redite_s``, plafonds, sortie). Pas dans le contexte (``historique=False``) : le résumé de
            # passation se bâtit en même temps, rien ne doit bouger derrière lui ; la phrase reste dans
            # le journal de l'appel.
            await diseur.veiller(
                PASSATION_TARDE,
                lambda: self._passation_en_cours(request),
                agent=source,
                phrase=pont,
                historique=False,
                avant_chaque=avant,
                apres_chaque=apres,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 -- un filet ne fait jamais rater la passation
            logger.warning(f"[transfer] {request.request_id}: phrase pont non dite : {e!r}")
        finally:
            # Quoi qu'il arrive (échec, annulation, voix absente), le son d'attente reprend si la
            # passation dure encore : l'appelant n'attend jamais en silence à cause d'un filet.
            self._phrase_en_cours = False
            if son_coupe and self._passation_en_cours(request) and self._hold_stop is None:
                self._start_hold_audio(request, reglage)

    def _passation_en_cours(self, request) -> bool:
        """La passation n'est ni annulée, ni commise, ni finie (le délai de la phrase pont court)."""
        return (
            self._request is request
            and not request.cancelled
            and self._phase in (TransferPhase.ANNOUNCING, TransferPhase.PREPARING)
            and not self._engine.is_call_disposed()
        )

    async def _annuler_phrase_pont(self, *, attendre_la_fin: bool = True):
        """Annule la phrase pont pas encore dite. Une phrase déjà en cours de lecture se termine
        (``attendre_la_fin``, au plus ``ATTENTE_FIN_PHRASE_PONT_S``) : la couper laisserait un mot en
        plein milieu, mais l'appelant attend et le commit ne doit pas attendre une phrase longue."""
        task = self._phrase_task
        self._phrase_task = None
        if task is None or task is asyncio.current_task():
            return
        if attendre_la_fin and self._phrase_en_cours and not task.done():
            with suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=ATTENTE_FIN_PHRASE_PONT_S)
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _stop_hold_audio(self):
        if self._hold_stop is not None:
            self._hold_stop.set()
        task = self._hold_task
        self._hold_task = None
        self._hold_stop = None
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=2)
            except TimeoutError:
                logger.warning("Hold audio producer timed out while stopping")

    def _finish(self, request, outcome, source, destination):
        if destination is None:
            # [.mark] D1 : rien n'a été basculé, l'agent d'origine garde l'appel et reparle.
            rendre_la_parole(getattr(source, "llm", None))
        self._phase = TransferPhase.IDLE
        self._request = None
        self._engine.call_monitor.resume()
        self._engine.record_transfer_outcome(
            {
                "request_id": request.request_id,
                "outcome": outcome,
                "destination_workflow_id": request.destination_workflow_id,
                "destination_label": request.destination_label,
                "from_visit_id": source.visit_id,
                "to_visit_id": destination.visit_id if destination else None,
            }
        )
        # [.mark] Chantier agents-specialises (A18) : la trace ``passations`` de la fiche.
        tracer_passation(
            self._engine._gathered_context,
            de=getattr(source, "workflow_id", None) or None,
            vers=request.destination_workflow_id,
            raison=request.raison or request.destination_label,
            refusee=False,
            issue=outcome,
            demande=request.demande,
        )
        logger.info(f"[transfer] {request.request_id} {outcome}")
