"""Le pipeline d'un appel simulé (.mark, chantier langwatch-et-fenetre-du-run, lot 3, L8, L19).

Le même cœur que tout appel téléphonique (``_run_pipeline_telephony_impl``) : lectures cloisonnées par
organisation, configuration effective de l'agent, bruit d'ambiance, filtre de bruit entrant, réglages
temps réel, audio à 8 kHz. Seul le sérialiseur diffère : protocole Twilio **sans** identifiants ni
raccrochage par l'API de Twilio, puisqu'aucun appel téléphonique n'existe.
"""

from __future__ import annotations

from fastapi import WebSocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from api.db import db_client
from api.enums import WorkflowRunMode
from api.services.appel_simule.direct import fermer_le_direct, ouvrir_le_direct
from api.services.configuration.ai_model_configuration import (
    get_effective_ai_model_configuration_for_workflow,
)
from api.services.pipecat import run_pipeline
from api.services.pipecat.audio_config import AudioConfig, create_audio_config
from api.services.pipecat.audio_mixer import build_audio_out_mixer
from api.services.pipecat.transport_params import (
    filtre_de_bruit_overrides,
    realtime_param_overrides,
)

# Le débit du protocole Twilio : 8 kHz, comme un vrai appel téléphonique.
FOURNISSEUR_AUDIO = WorkflowRunMode.TWILIO.value


def serialiseur_sans_telephonie(
    stream_sid: str, call_sid: str
) -> TwilioFrameSerializer:
    return TwilioFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        params=TwilioFrameSerializer.InputParams(auto_hang_up=False),
    )


async def creer_transport(
    websocket: WebSocket,
    audio_config: AudioConfig,
    *,
    stream_sid: str,
    call_sid: str,
    ambient_noise_config: dict | None,
    is_realtime: bool,
    run_configs: dict | None,
) -> FastAPIWebsocketTransport:
    mixer = await build_audio_out_mixer(
        audio_config.transport_out_sample_rate, ambient_noise_config
    )
    return FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=audio_config.transport_in_sample_rate,
            audio_out_sample_rate=audio_config.transport_out_sample_rate,
            audio_out_mixer=mixer,
            serializer=serialiseur_sans_telephonie(stream_sid, call_sid),
            **realtime_param_overrides(is_realtime),
            **filtre_de_bruit_overrides(run_configs),
        ),
    )


async def jouer_appel_simule(
    websocket: WebSocket,
    *,
    workflow_run_id: int,
    organization_id: int,
    stream_sid: str,
    call_sid: str,
) -> None:
    """Joue le run simulé sur le WebSocket déjà accepté, jusqu'à la fin de l'appel."""
    workflow_run = await db_client.get_workflow_run(
        workflow_run_id, organization_id=organization_id
    )
    if workflow_run is None:
        raise ValueError(f"Workflow run {workflow_run_id} not found")
    workflow = await db_client.get_workflow(
        workflow_run.workflow_id, organization_id=organization_id
    )
    if workflow is None:
        raise ValueError(f"Workflow {workflow_run.workflow_id} not found")

    run_configs = workflow_run.definition.workflow_configurations or {}
    user_config = await get_effective_ai_model_configuration_for_workflow(
        organization_id=organization_id,
        workflow_configurations=run_configs,
    )
    is_realtime = bool(user_config.is_realtime and user_config.realtime is not None)
    ambient_noise_config = (workflow.workflow_configurations or {}).get(
        "ambient_noise_configuration"
    )

    audio_config = create_audio_config(FOURNISSEUR_AUDIO)
    transport = await creer_transport(
        websocket,
        audio_config,
        stream_sid=stream_sid,
        call_sid=call_sid,
        ambient_noise_config=ambient_noise_config,
        is_realtime=is_realtime,
        run_configs=run_configs,
    )
    # Le direct de l'appel (direct-et-passe-muette, lot A) : le pipeline prend son canal dans le
    # registre au démarrage ; il est retiré à la fin, quoi qu'il arrive.
    await ouvrir_le_direct(workflow_run.id)
    try:
        await run_pipeline._run_pipeline_impl(
            transport,
            workflow.id,
            workflow_run.id,
            # Attribution seulement : le cloisonnement passe par organization_id.
            workflow.user_id,
            audio_config=audio_config,
            workflow_run=workflow_run,
            resolved_user_config=user_config,
            organization_id=organization_id,
            provider_call_id=call_sid,
        )
    finally:
        await fermer_le_direct(workflow_run.id)
