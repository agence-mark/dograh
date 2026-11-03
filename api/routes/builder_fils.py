"""[.mark] Le builder, le chat : ses conversations en tables, en tâche de fond, rejouables (builder partie 2, U5).

- ``GET  /builder/demarrages``                        les 4 démarrages les plus utilisés (hors Rejeté) ;
- ``GET  /builder/fils``                              les conversations (``?workflow_id=``), les plus récentes d'abord ;
- ``POST /builder/fils``                              ouvre une conversation et lance le travail (``demarrage`` facultatif) ;
- ``GET  /builder/fils/{id}``                         une conversation (état, coût, jauge, changements à valider) ;
- ``GET  /builder/fils/{id}/evenements``              le flux SSE, rejoué depuis ``?depuis=`` ou ``Last-Event-ID`` ;
- ``POST /builder/fils/{id}/messages``                un message de plus ;
- ``POST /builder/fils/{id}/arreter`` · ``reprendre`` · ``modifier-dernier``.

Tout est lu et écrit AVEC l'organisation de l'utilisateur (R0) : la conversation d'une autre organisation est un 404, et l'agent
joint est contrôlé de la même façon. Le travail tourne en tâche de fond : fermer l'onglet ne l'arrête pas.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user_with_selected_organization
from api.services.builder import demarrages, fil as service_fil
from api.services.builder.constantes import organisation_bibliotheque
from api.services.mark_evenements import flux_sse, suivre

router = APIRouter(tags=["builder"])

DUREE_MAX_CLAUDE_CODE_S = 600.0


async def _cerveau_de(user: UserModel):
    # Même fabrique que la conversation historique (les tests la remplacent au même endroit).
    from api.routes import builder as routes_builder

    return await routes_builder._cerveau_de(user)


async def _fil_ou_404(user: UserModel, fil_id: int):
    fil = await db_client.lire_fil(user.selected_organization_id, fil_id)
    if fil is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return fil


async def _agent_ou_404(user: UserModel, workflow_id: int):
    workflow = await db_client.get_workflow(workflow_id, organization_id=user.selected_organization_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Agent not found")
    return workflow


class VueFil(BaseModel):
    id: int
    workflow_id: int | None
    titre: str
    etat: str
    jetons: int
    cout: float
    jauge: float
    changements: int
    demarrage: str | None
    cree_le: Any
    modifie_le: Any
    en_cours: bool
    genre: str = "principal"
    parent_id: int | None = None
    sous_agents_actifs: bool = True
    # U12 : une conversation recopiée depuis Claude Code (genre « claude_code ») : lecture seule, auteur affiché « Claude Code · <prénom> ».
    auteur: str | None = None


def _vue(fil) -> VueFil:
    return VueFil(
        id=fil.id,
        workflow_id=fil.workflow_id,
        titre=fil.titre,
        etat=fil.etat,
        jetons=fil.jetons or 0,
        cout=fil.cout or 0.0,
        jauge=fil.jauge or 0.0,
        changements=fil.changements or 0,
        demarrage=fil.demarrage,
        cree_le=fil.cree_le,
        modifie_le=fil.modifie_le,
        en_cours=service_fil.en_cours(fil.id),
        genre=fil.genre or "principal",
        parent_id=fil.parent_id,
        sous_agents_actifs=bool(fil.sous_agents_actifs),
        auteur=fil.auteur,
    )


def _pas_un_sous_agent(fil) -> None:
    """C2 (E96) : un sous-agent est lu, arrêté, jamais écrit à ni relancé par une personne."""
    if fil.genre == "sous_agent":
        raise HTTPException(status_code=409, detail="A sub-agent receives no message.")
    if fil.genre == "claude_code":  # U12 : on écrit dans Claude Code, on lit dans les deux
        raise HTTPException(status_code=409, detail="This conversation is led in Claude Code: it is read-only here.")


def _refus(erreur: service_fil.ErreurFil) -> HTTPException:
    return HTTPException(status_code=erreur.statut, detail=str(erreur))


def _dans_le_labo(user: UserModel) -> bool:
    """L'espace de la requête est-il le Labo ? Un client ne voit pas les cartes « proposées dans le Labo seulement » (E57)."""
    return user.selected_organization_id == organisation_bibliotheque()


class VueDemarrage(BaseModel):
    slug: str
    titre: str
    phrase: str
    demande: str
    besoin: str
    icone: str
    statut: str
    utilisations: int
    proposee_dans: str = "labo_et_clients"


@router.get("/demarrages", response_model=list[VueDemarrage])
async def lire_les_demarrages(user: UserModel = Depends(get_user_with_selected_organization)):
    return await demarrages.plus_utilises(dans_le_labo=_dans_le_labo(user))


@router.get("/fils", response_model=list[VueFil])
async def lister_les_fils(
    workflow_id: int | None = Query(default=None), user: UserModel = Depends(get_user_with_selected_organization)
):
    return [_vue(f) for f in await db_client.lister_fils(user.selected_organization_id, workflow_id)]


class NouveauFil(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    workflow_id: int | None = None
    demarrage: str | None = Field(default=None, max_length=120)


@router.post("/fils", response_model=VueFil)
async def ouvrir_un_fil(demande: NouveauFil, user: UserModel = Depends(get_user_with_selected_organization)):
    workflow = await _agent_ou_404(user, demande.workflow_id) if demande.workflow_id is not None else None
    carte = None
    if demande.demarrage:
        carte = await demarrages.lire(demande.demarrage, dans_le_labo=_dans_le_labo(user))
        if carte is None:
            raise HTTPException(status_code=404, detail="Starter not found")
        if (manque := demarrages.manque(carte, demande.workflow_id)) is not None:
            raise HTTPException(status_code=422, detail=manque)
    cerveau, reglages = await _cerveau_de(user)
    message = demarrages.remplir(demande.message, getattr(workflow, "name", None))
    titre = carte["titre"] if carte else message.strip().splitlines()[0]
    fil = await service_fil.creer(user, demande.workflow_id, titre, demande.demarrage)
    if demande.demarrage:
        await demarrages.noter_l_utilisation(demande.demarrage, user.selected_organization_id, fil.id)
    try:
        await service_fil.lancer(user, fil, message, cerveau, reglages)
    except service_fil.ErreurFil as erreur:
        raise _refus(erreur) from None
    return _vue(await _fil_ou_404(user, fil.id))


@router.get("/fils/{fil_id}", response_model=VueFil)
async def lire_un_fil(fil_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    return _vue(await _fil_ou_404(user, fil_id))


@router.get("/fils/{fil_id}/evenements")
async def suivre_un_fil(
    fil_id: int,
    depuis: int | None = Query(default=None, ge=0),
    last_event_id: str | None = Header(default=None),
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """Le flux SSE : tout ce qui a été écrit après ``depuis`` (ou ``Last-Event-ID`` à la reconnexion), puis la suite en direct."""
    await _fil_ou_404(user, fil_id)
    org = user.selected_organization_id
    fin_du_flux = asyncio.get_running_loop().time() + DUREE_MAX_CLAUDE_CODE_S
    reprise = depuis if depuis is not None else (int(last_event_id) if last_event_id and last_event_id.isdigit() else 0)

    async def est_fini() -> bool:
        courant = await db_client.lire_fil(org, fil_id)
        if courant is not None and courant.genre == "claude_code":
            # Une session Claude Code reprend à chaque message : le flux reste ouvert, borné à DUREE_MAX_CLAUDE_CODE_S (l'écran se reconnecte).
            return asyncio.get_running_loop().time() >= fin_du_flux
        return courant is None or (courant.etat != "en_cours" and not service_fil.en_cours(fil_id))

    source = suivre(service_fil.canal(fil_id), lambda apres: service_fil.lire_apres(fil_id, apres), est_fini, reprise)
    return StreamingResponse(
        flux_sse(source),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class MessageDuFil(BaseModel):
    message: str = Field(min_length=1, max_length=20000)


@router.post("/fils/{fil_id}/messages", response_model=VueFil)
async def envoyer_un_message(fil_id: int, demande: MessageDuFil, user: UserModel = Depends(get_user_with_selected_organization)):
    fil = await _fil_ou_404(user, fil_id)
    _pas_un_sous_agent(fil)
    cerveau, reglages = await _cerveau_de(user)
    try:
        await service_fil.lancer(user, fil, demande.message, cerveau, reglages)
    except service_fil.ErreurFil as erreur:
        raise _refus(erreur) from None
    return _vue(await _fil_ou_404(user, fil_id))


@router.post("/fils/{fil_id}/arreter", response_model=VueFil)
async def arreter_un_fil(fil_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    fil = await _fil_ou_404(user, fil_id)
    if fil.genre == "claude_code":
        raise HTTPException(status_code=409, detail="This conversation is led in Claude Code: it is read-only here.")
    await service_fil.arreter(user.selected_organization_id, fil_id)
    return _vue(await _fil_ou_404(user, fil_id))


@router.post("/fils/{fil_id}/reprendre", response_model=VueFil)
async def reprendre_un_fil(fil_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    fil = await _fil_ou_404(user, fil_id)
    _pas_un_sous_agent(fil)
    cerveau, reglages = await _cerveau_de(user)
    try:
        await service_fil.reprendre(user, fil, cerveau, reglages)
    except service_fil.ErreurFil as erreur:
        raise _refus(erreur) from None
    return _vue(await _fil_ou_404(user, fil_id))


@router.post("/fils/{fil_id}/modifier-dernier", response_model=VueFil)
async def modifier_le_dernier_message(
    fil_id: int, demande: MessageDuFil, user: UserModel = Depends(get_user_with_selected_organization)
):
    fil = await _fil_ou_404(user, fil_id)
    _pas_un_sous_agent(fil)
    cerveau, reglages = await _cerveau_de(user)
    try:
        await service_fil.modifier_le_dernier_message(user, fil, demande.message, cerveau, reglages)
    except service_fil.ErreurFil as erreur:
        raise _refus(erreur) from None
    return _vue(await _fil_ou_404(user, fil_id))



