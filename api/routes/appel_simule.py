"""[.mark] L'entrée audio des appels simulés (chantier langwatch-et-fenetre-du-run, lot 3, L8, L19).

``/appel-simule/ws/{workflow_run_id}/{jeton}`` : le simulateur (LangWatch Scenario) s'y branche au
protocole Twilio Media Streams (``connected``, ``start``, puis l'audio µ-law 8 kHz). Refus, avant
tout pipeline : jeton faux ou run inconnu (4401), run d'un autre mode ou déjà joué (4409). Le run
passe à « running » dès l'acceptation : le jeton ne sert qu'une fois.

La route ne garde que le protocole (jeton, concurrence, quota, début du flux) ; le pipeline est dans
``services/appel_simule/pipeline.py``. Calquée sur ``agent_stream.py``, dans un routeur à part pour ne
toucher aucun fichier de Dograh.

Et les routes de l'écran (L11, L18), toujours dans l'organisation de l'utilisateur : réglages de
l'appelant simulé, scénarios d'un agent, lancement, suivi, arrêt et rapport d'une série.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from loguru import logger
from pipecat.utils.run_context import set_current_org_id, set_current_run_id
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from api.db import db_client
from api.db.models import UserModel
from api.enums import WorkflowRunState
from api.schemas.appel_simule import ReglagesAppelantSimule, ScenarioSimule
from api.services.appel_simule import reglages as stockage
from api.services.appel_simule.entree import CLE_EXTRA, jeton_valide, run_branchable
from api.services.appel_simule.pipeline import jouer_appel_simule
from api.services.appel_simule.reglages import SerieSimulee
from api.services.appel_simule.serie import SerieRefusee, arreter_serie, lancer_serie
from api.services.auth.depends import get_user_with_selected_organization
from api.services.call_concurrency import CallConcurrencyLimitError, call_concurrency
from api.services.pipecat import run_pipeline
from api.services.quota_service import authorize_workflow_run_start
from api.services.workflow_run_failure import mark_workflow_run_failed

router = APIRouter(prefix="/appel-simule", tags=["appel-simule"])


async def lire_le_debut(websocket: WebSocket) -> tuple[str, str] | None:
    """``connected`` puis ``start`` : ``(streamSid, callSid)``, ou ``None`` si le protocole n'est pas suivi."""
    try:
        premier = json.loads(await websocket.receive_text())
        if not isinstance(premier, dict) or premier.get("event") != "connected":
            return None
        second = json.loads(await websocket.receive_text())
    except json.JSONDecodeError:
        return None
    if not isinstance(second, dict) or second.get("event") != "start":
        return None
    debut = second.get("start")
    if not isinstance(debut, dict):
        return None
    stream_sid = debut.get("streamSid")
    if not isinstance(stream_sid, str) or not stream_sid:
        return None
    call_sid = debut.get("callSid")
    return stream_sid, call_sid if isinstance(
        call_sid, str
    ) and call_sid else stream_sid


async def _fermer(websocket: WebSocket, code: int, raison: str) -> None:
    try:
        await websocket.close(code=code, reason=raison)
    except RuntimeError:
        pass


@router.websocket("/ws/{workflow_run_id}/{jeton}")
async def appel_simule_websocket(
    websocket: WebSocket, workflow_run_id: int, jeton: str
):
    await websocket.accept()
    # Lecture sans organisation : c'est le jeton du run qui prouve le droit, puis l'organisation est
    # tirée du run lui-même et sert à toutes les lectures suivantes.
    run = await db_client.get_workflow_run_by_id(workflow_run_id)
    if run is None or not jeton_valide(run, jeton):
        logger.warning(f"[appel simulé] jeton refusé pour le run {workflow_run_id}")
        await _fermer(websocket, 4401, "Unauthorized")
        return
    if not run_branchable(run):
        await _fermer(websocket, 4409, "Run not available for connection")
        return
    organisation = run.workflow.organization_id
    set_current_run_id(run.id)
    set_current_org_id(organisation)
    # Usage unique : le run quitte « initialized » avant toute autre attente.
    await db_client.update_workflow_run(
        run_id=run.id, state=WorkflowRunState.RUNNING.value
    )

    try:
        place = await call_concurrency.acquire_org_slot(
            organisation, source="appel_simule", timeout=0
        )
    except CallConcurrencyLimitError:
        await mark_workflow_run_failed(run.id, "Concurrent call limit reached")
        await _fermer(websocket, 1008, "Concurrent call limit reached")
        return
    try:
        await call_concurrency.bind_workflow_run(place, run.id)
    except Exception:
        await call_concurrency.release_slot(place)
        raise

    run_pipeline.register_worker_active_call(run.id)
    try:
        quota = await authorize_workflow_run_start(
            workflow_id=run.workflow_id,
            organization_id=organisation,
            workflow_run_id=run.id,
        )
        if not quota.has_quota:
            await mark_workflow_run_failed(
                run.id, quota.error_message or "Quota exceeded"
            )
            await _fermer(websocket, 1008, quota.error_message or "Quota exceeded")
            return
        identifiants = await lire_le_debut(websocket)
        if identifiants is None:
            await mark_workflow_run_failed(
                run.id, "Expected connected then start events"
            )
            await _fermer(websocket, 4400, "Expected connected then start events")
            return
        stream_sid, call_sid = identifiants
        await jouer_appel_simule(
            websocket,
            workflow_run_id=run.id,
            organization_id=organisation,
            stream_sid=stream_sid,
            call_sid=call_sid,
        )
        # Fin de l'appel : le simulateur l'apprend même si le transport n'a pas fermé.
        await _fermer(websocket, 1000, "Call ended")
    except WebSocketDisconnect as e:
        logger.info(f"[appel simulé] déconnecté : code={e.code} reason={e.reason}")
    except Exception as e:
        logger.error(f"[appel simulé] erreur sur le run {run.id} : {e}", exc_info=True)
        await _fermer(websocket, 1011, "Internal server error")
    finally:
        try:
            await call_concurrency.unregister_active_call(run.id)
        finally:
            run_pipeline.unregister_worker_active_call(run.id)


# --- L'écran ---------------------------------------------------------------------------------------


def _illisible(quoi: str, erreur: Exception) -> HTTPException:
    logger.warning(f"[.mark] {quoi} unreadable for the screen: {erreur!r}")
    return HTTPException(
        status_code=500,
        detail=f"The {quoi} saved for this organization cannot be read. Nothing was changed; saving now would replace it.",
    )


async def _agent(workflow_id: int, user: UserModel):
    workflow = await db_client.get_workflow(
        workflow_id, organization_id=user.selected_organization_id
    )
    if workflow is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return workflow


@router.get("/reglages", response_model=ReglagesAppelantSimule)
async def get_reglages_appelant_simule(
    user: UserModel = Depends(get_user_with_selected_organization),
):
    try:
        return await stockage.lire_reglages(user.selected_organization_id)
    except Exception as erreur:  # noqa: BLE001
        raise _illisible("simulated caller settings", erreur) from None


@router.put("/reglages", response_model=ReglagesAppelantSimule)
async def save_reglages_appelant_simule(
    request: ReglagesAppelantSimule,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    org = user.selected_organization_id
    for uuid_ in {
        request.appelant.identifiant,
        request.juge.identifiant,
        request.voix.identifiant,
    }:
        if uuid_ and await db_client.get_credential_by_uuid(uuid_, org) is None:
            raise HTTPException(status_code=404, detail="Credential not found")
    return await stockage.enregistrer_reglages(org, request)


@router.get("/agents/{workflow_id}/scenarios", response_model=list[ScenarioSimule])
async def get_scenarios_simules(
    workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)
):
    await _agent(workflow_id, user)
    try:
        return await stockage.lire_scenarios(user.selected_organization_id, workflow_id)
    except Exception as erreur:  # noqa: BLE001
        raise _illisible("scenario library", erreur) from None


@router.put("/agents/{workflow_id}/scenarios", response_model=list[ScenarioSimule])
async def save_scenarios_simules(
    workflow_id: int,
    request: list[ScenarioSimule],
    user: UserModel = Depends(get_user_with_selected_organization),
):
    await _agent(workflow_id, user)
    try:
        return await stockage.remplacer_scenarios(
            user.selected_organization_id, workflow_id, request
        )
    except ValueError as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from None


class LancementSerie(BaseModel):
    scenario_ids: list[str] = Field(min_length=1, max_length=50)


@router.post("/agents/{workflow_id}/series", response_model=SerieSimulee)
async def lancer_serie_simulee(
    workflow_id: int,
    request: LancementSerie,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    await _agent(workflow_id, user)
    try:
        return await lancer_serie(
            user.selected_organization_id, user.id, workflow_id, request.scenario_ids
        )
    except SerieRefusee as erreur:
        raise HTTPException(status_code=409, detail=str(erreur)) from None


@router.get("/series", response_model=list[SerieSimulee])
async def get_series_simulees(
    workflow_id: int | None = None,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    series = await stockage.lire_series(user.selected_organization_id)
    return [s for s in series if workflow_id is None or s.workflow_id == workflow_id]


class AppelDuRapport(BaseModel):
    scenario_id: str
    scenario_nom: str
    run_id: int | None
    etat: str
    reussi: bool | None
    cout: float | None
    erreur: str | None
    resultat: dict | None = None


class RapportSerie(BaseModel):
    serie: SerieSimulee
    appels: list[AppelDuRapport]


@router.get("/series/{serie_id}", response_model=RapportSerie)
async def get_rapport_serie(
    serie_id: str, user: UserModel = Depends(get_user_with_selected_organization)
):
    org = user.selected_organization_id
    serie = await stockage.lire_serie(org, serie_id)
    if serie is None:
        raise HTTPException(status_code=404, detail="Series not found")
    appels = []
    for appel in serie.appels:
        resultat = None
        if appel.run_id is not None:
            run = await db_client.get_workflow_run(appel.run_id, organization_id=org)
            if run is not None and run.workflow_id == serie.workflow_id:
                resultat = ((run.extra or {}).get(CLE_EXTRA) or {}).get("resultat")
        appels.append(AppelDuRapport(**appel.model_dump(), resultat=resultat))
    return RapportSerie(serie=serie, appels=appels)


@router.post("/series/{serie_id}/arreter")
async def arreter_serie_simulee(
    serie_id: str, user: UserModel = Depends(get_user_with_selected_organization)
) -> dict:
    if not await arreter_serie(user.selected_organization_id, serie_id):
        raise HTTPException(status_code=409, detail="This series is not playing.")
    return {"stopping": True}
