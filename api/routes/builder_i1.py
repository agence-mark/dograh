"""[.mark] Le builder, U12 (lot I1, E104) : les sources des cerveaux, le miroir des conversations Claude Code, la mise à jour en direct.

- ``GET  /builder/sources``                   la source de chaque brique (builder, appelant, juge des tests, juge des vrais appels, analyse) ;
- ``PUT  /builder/sources/{brique}``          change la source d'UNE brique (``claude_code`` | ``cle_api``) ; équipe .mark seulement ;
- ``GET|PUT /builder/miroir/reglage``         l'interrupteur de la personne (éteint par défaut) ;
- ``POST /builder/miroir``                    les hooks de Claude Code y envoient messages, réponses et actions (clé MCP de la personne) ;
- ``GET  /builder/resume``                    ce qui a changé depuis la dernière session (la même fonction que l'outil MCP ``fork_resume``) ;
- ``GET  /builder/live``                      le flux SSE des modifications (``?objet=agent:12``, ``Last-Event-ID``) : l'écran se rafraîchit seul.

Tout est lu et écrit AVEC l'organisation de la clé ou de la session ; le corps d'une requête ne désigne jamais l'organisation.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.db import db_client
from api.db.models import UserModel
from api.services import miroir, modifications_live as live, sources_cerveaux
from api.services.auth.depends import get_user_with_selected_organization
from api.services.builder.cerveau import reglages as reglages_cerveau
from api.services.call_concurrency.rate_limiter import rate_limiter
from api.services.mark_evenements import flux_sse, suivre

router = APIRouter(tags=["builder"])

DUREE_MAX_FLUX_S = 600.0


class VueSources(BaseModel):
    sources: dict[str, Literal["claude_code", "cle_api"]]


@router.get("/sources", response_model=VueSources)
async def lire_les_sources(user: UserModel = Depends(get_user_with_selected_organization)):
    organisation_du_builder = await reglages_cerveau.organisation_des_reglages(user)
    return VueSources(sources=await sources_cerveaux.toutes(organisation_du_builder, user.selected_organization_id))


class ChangementDeSource(BaseModel):
    source: Literal["claude_code", "cle_api"]


@router.put("/sources/{brique}", response_model=VueSources)
async def regler_une_source(brique: str, demande: ChangementDeSource, user: UserModel = Depends(get_user_with_selected_organization)):
    if brique not in sources_cerveaux.BRIQUES:
        raise HTTPException(status_code=404, detail="Unknown brick")
    organisation_du_builder = await reglages_cerveau.organisation_des_reglages(user)
    organisation = organisation_du_builder if brique in sources_cerveaux.BRIQUES_DU_BUILDER else user.selected_organization_id
    await sources_cerveaux.regler(organisation, brique, demande.source)
    await live.noter(organisation, "sources", f"source_{brique}", source="ecran", auteur=live.auteur_de(user))
    return VueSources(sources=await sources_cerveaux.toutes(organisation_du_builder, user.selected_organization_id))


class ReglageDuMiroir(BaseModel):
    actif: bool


@router.get("/miroir/reglage", response_model=ReglageDuMiroir)
async def lire_le_miroir(user: UserModel = Depends(get_user_with_selected_organization)):
    return ReglageDuMiroir(actif=await miroir.actif(user.selected_organization_id, user.id))


@router.put("/miroir/reglage", response_model=ReglageDuMiroir)
async def regler_le_miroir(demande: ReglageDuMiroir, user: UserModel = Depends(get_user_with_selected_organization)):
    return ReglageDuMiroir(actif=await miroir.regler(user.selected_organization_id, user.id, demande.actif))


class RecuDuMiroir(BaseModel):
    actif: bool
    recus: int
    filtres: int = 0
    fil_id: int | None = None


@router.post("/miroir", response_model=RecuDuMiroir)
async def recevoir_le_miroir(charge: miroir.ChargeMiroir, user: UserModel = Depends(get_user_with_selected_organization)):
    """Une limite de débit par compte (120 envois par minute) ; l'interrupteur éteint : rien n'est rangé."""
    try:
        permis = await rate_limiter.acquire_token(user.id, miroir.PAR_MINUTE, scope_key=f"miroir:{user.id}", window_seconds=60.0)
    except Exception:  # noqa: BLE001 -- limiteur injoignable : on refuse (prudent), le hook réessaiera plus tard
        permis = False
    if not permis:
        raise HTTPException(status_code=429, detail="Too many mirror requests")
    return RecuDuMiroir(**await miroir.recevoir(user, charge))


@router.get("/resume")
async def lire_le_resume(
    depuis: str | None = Query(default=None, max_length=40), user: UserModel = Depends(get_user_with_selected_organization)
):
    """Pour le hook d'ouverture de session de Claude Code : le même résultat que l'outil MCP ``fork_resume``."""
    from api.services.builder.actions.registre import PORTE_MCP, Contexte, executer

    resultat = await executer("fork_resume", {"depuis": depuis} if depuis else {}, Contexte(user=user, porte=PORTE_MCP))
    if resultat.get("ok") is False:
        raise HTTPException(status_code=422, detail=str(resultat.get("erreur", "Invalid request")))
    return resultat


@router.get("/live")
async def suivre_les_modifications(
    objet: str | None = Query(default=None, max_length=80),
    depuis: int | None = Query(default=None, ge=0),
    last_event_id: str | None = Header(default=None),
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """Les modifications APRÈS ``depuis`` (ou ``Last-Event-ID``), puis les suivantes en direct. Sans point de départ : seulement les
    nouvelles (l'écran vient de lire l'état). Le flux se ferme au bout de dix minutes, l'écran se reconnecte avec le dernier identifiant."""
    if objet is not None and not live.OBJET_VALIDE.match(objet):
        raise HTTPException(status_code=422, detail="Invalid object")
    organisation = user.selected_organization_id
    if depuis is not None:
        reprise = depuis
    elif last_event_id and last_event_id.isdigit():
        reprise = int(last_event_id)
    else:
        reprise = await db_client.derniere_modification(organisation)
    import asyncio

    fin = asyncio.get_running_loop().time() + DUREE_MAX_FLUX_S

    async def est_fini() -> bool:
        return asyncio.get_running_loop().time() >= fin

    source = suivre(live.canal(organisation), lambda apres: live.lire_apres(organisation, apres, objet), est_fini, reprise)
    return StreamingResponse(
        flux_sse(source), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
