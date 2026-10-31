"""[.mark] Le builder d'agent vocal : la porte de l'écran (``/builder``). Chantier builder-agent-vocal, lot 1.

- ``POST /builder/conversation``                              un message ; réponse en flux (SSE) de ``moteur.conversation`` ;
- ``GET  /builder/conversation/{agent}``                      l'historique de l'agent (texte, actions, résumé, dépense) ;
- ``POST /builder/conversation/{agent}/corriger``             correction en plusieurs tours (B37), en flux ;
- ``GET  /builder/conception/{agent}`` · ``POST .../decision``  le document de conception et le geste humain (B36) ;
- ``GET  /builder/fiche/{agent}`` · ``POST .../valider``       la fiche client et sa validation par une personne ;
- ``GET  /builder/actions``                                    les actions des deux portes ;
- ``GET/PUT /builder/cerveau``                                 fournisseur, modèle, clé, plafonds (la clé n'est jamais relue) ;
- ``GET/PUT /builder/preferences``                             les préférences de la personne (couche 3).

La bibliothèque a ses routes à part (``builder_bibliotheque.py``, préfixe ``/builder/bibliotheque``).

Règles : tout est lu et écrit AVEC l'organisation de l'utilisateur (un agent d'une autre organisation est un 404) ;
la clé du cerveau n'est ni renvoyée, ni journalisée ; le builder ne publie jamais (il n'en a pas l'action).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.enums import WebhookCredentialType
from api.routes.builder_bibliotheque import router as routeur_bibliotheque
from api.routes.builder_contexte import router as routeur_contexte
from api.services.auth.depends import get_user_with_selected_organization
from api.services.builder import actions, conception, contexte, correction, fiche as service_fiche, moteur
from api.services.builder.actions.registre import Contexte
from api.services.builder.bibliotheque import droits
from api.services.builder.bibliotheque.service import ErreurBibliotheque
from api.services.builder.cerveau import reglages as reglages_cerveau
from api.services.builder.cerveau.appel import Cerveau, ErreurCerveau, fabriquer
from api.services.builder.cerveau.reglages import FormatDuFil, ReglagesCerveau, VueReglagesCerveau

router = APIRouter(prefix="/builder", tags=["builder"])
router.include_router(routeur_bibliotheque)
router.include_router(routeur_contexte)

MARQUE_CLE_DU_CERVEAU = "mark_builder_cerveau"
NOM_CLE_DU_CERVEAU = "builder-cerveau"
CLE_LONGUEUR = (8, 500)


def _transport_des_tests() -> httpx.AsyncBaseTransport | None:
    """Les tests remplacent cette fonction pour ne jamais atteindre un vrai fournisseur."""
    return None


def fabriquer_le_cerveau(reglages: ReglagesCerveau, cle: str) -> Cerveau:
    return fabriquer(reglages, cle, _transport_des_tests())


async def _agent_ou_404(user: UserModel, workflow_id: int):
    workflow = await db_client.get_workflow(workflow_id, organization_id=user.selected_organization_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Agent not found")
    return workflow


def _refus_bibliotheque(erreur: ErreurBibliotheque) -> HTTPException:
    return HTTPException(status_code=erreur.statut, detail=str(erreur))


# --- la conversation ---------------------------------------------------------------------------------------------


class MessageDuBuilder(BaseModel):
    workflow_id: int
    message: str = Field(min_length=1, max_length=20000)


def _flux(evenements: AsyncIterator[dict[str, Any]]) -> StreamingResponse:
    async def diffuser():
        async for evenement in evenements:
            yield f"data: {json.dumps(evenement, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(
        diffuser(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _cerveau_de(user: UserModel) -> tuple[Cerveau, ReglagesCerveau]:
    organisation = await reglages_cerveau.organisation_des_reglages(user)
    reglages = await reglages_cerveau.lire(organisation)
    cle = await reglages_cerveau.lire_la_cle(organisation, reglages)
    if not reglages.modele or not cle:
        raise HTTPException(status_code=409, detail="Set the builder's brain first: model and key (builder settings).")
    try:
        return fabriquer_le_cerveau(reglages, cle), reglages
    except ErreurCerveau as erreur:
        raise HTTPException(status_code=409, detail=erreur.message) from None


@router.post("/conversation")
async def parler_au_builder(demande: MessageDuBuilder, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, demande.workflow_id)
    cerveau, reglages = await _cerveau_de(user)
    contexte_d_action = Contexte(user=user, workflow_id=demande.workflow_id)
    return _flux(moteur.conversation(contexte_d_action, demande.message, cerveau, reglages))


@router.post("/conversation/{workflow_id}/corriger")
async def corriger_le_brouillon(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    cerveau, reglages = await _cerveau_de(user)
    return _flux(correction.corriger(Contexte(user=user, workflow_id=workflow_id), cerveau, reglages))


class VueConversation(BaseModel):
    resume: str
    messages: list[dict[str, Any]]
    depense: dict[str, Any]
    en_cours: bool


@router.get("/conversation/{workflow_id}", response_model=VueConversation)
async def lire_la_conversation(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    conv = await contexte.charger(user.selected_organization_id, workflow_id)
    return VueConversation(
        resume=conv["resume"],
        messages=[
            {k: v for k, v in m.items() if k in ("role", "content", "nom", "appels")} for m in conv["messages"] if m["role"] != "outil"
        ],
        depense=conv["depense"],
        en_cours=bool(conv.get("en_cours_depuis")),
    )


# --- conception et fiche : les gestes humains --------------------------------------------------------------------


@router.get("/conception/{workflow_id}")
async def lire_la_conception(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    return {"conception": conception.resume(await conception.lire(user.selected_organization_id, workflow_id))}


class DecisionDeConception(BaseModel):
    approuve: bool
    note: str | None = Field(default=None, max_length=2000)


@router.post("/conception/{workflow_id}/decision")
async def decider_de_la_conception(
    workflow_id: int, decision: DecisionDeConception, user: UserModel = Depends(get_user_with_selected_organization)
):
    """Approuver, ou renvoyer avec une note. C'est le seul chemin qui approuve : le builder n'a pas cette action."""
    await _agent_ou_404(user, workflow_id)
    try:
        etat = await conception.decider(
            user.selected_organization_id, workflow_id, decision.approuve, droits.nom_de_l_auteur(user), decision.note
        )
    except conception.ErreurConception as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from None
    return {"conception": conception.resume(etat)}


@router.get("/fiche/{workflow_id}")
async def lire_la_fiche(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    return {"fiche": (await service_fiche.lire(user.selected_organization_id, workflow_id)).model_dump(mode="json")}


@router.post("/fiche/{workflow_id}/valider")
async def valider_la_fiche(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    try:
        fiche = await service_fiche.valider(user.selected_organization_id, workflow_id, droits.nom_de_l_auteur(user))
    except service_fiche.ErreurFiche as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from None
    return {"fiche": fiche.model_dump(mode="json")}


# --- les actions -------------------------------------------------------------------------------------------------


class VueAction(BaseModel):
    nom: str
    description: str
    groupe: str
    ecriture: bool
    disponible: bool
    mcp: bool
    parametres: dict[str, Any]


@router.get("/actions", response_model=list[VueAction])
async def lister_les_actions(user: UserModel = Depends(get_user_with_selected_organization)):
    return [
        VueAction(
            nom=a.nom,
            description=a.description,
            groupe=a.groupe,
            ecriture=a.ecriture,
            disponible=a.disponible,
            mcp=a.mcp,
            parametres=a.schema(),
        )
        for a in actions.REGISTRE.values()
    ]


# --- le cerveau --------------------------------------------------------------------------------------------------


@router.get("/cerveau", response_model=VueReglagesCerveau)
async def lire_le_cerveau(user: UserModel = Depends(get_user_with_selected_organization)):
    """Les réglages, jamais la clé : seulement « posée » ou non."""
    return await reglages_cerveau.vue(await reglages_cerveau.organisation_des_reglages(user))


class ModificationDuCerveau(BaseModel):
    format: FormatDuFil
    modele: str = Field(min_length=1, max_length=200)
    adresse: str = Field(default="", max_length=500)
    plafond_depense: float = Field(default=2.0, ge=0)
    plafond_jetons: int = Field(default=1_500_000, ge=1000)
    prix_entree_par_million: float = Field(default=0.0, ge=0)
    prix_sortie_par_million: float = Field(default=0.0, ge=0)
    fenetre: int = Field(default=200_000, ge=4000)
    sortie_max: int = Field(default=8192, ge=256)
    tours_outils_max: int = Field(default=12, ge=1, le=40)
    tours_correction_max: int = Field(default=3, ge=1, le=10)
    # Bornes vérifiées dans la route : une erreur de validation de FastAPI renverrait la valeur saisie.
    cle: str | None = None


@router.put("/cerveau", response_model=VueReglagesCerveau)
async def regler_le_cerveau(
    demande: ModificationDuCerveau, user: UserModel = Depends(get_user_with_selected_organization)
):
    """Réservé à l'équipe .mark (le coût du builder est celui de .mark). La clé va au coffre chiffré, jamais dans la ligne."""
    try:
        await droits.exiger_l_equipe(user)
    except ErreurBibliotheque as erreur:
        raise _refus_bibliotheque(erreur) from None
    if demande.adresse and not demande.adresse.startswith("https://"):
        raise HTTPException(status_code=422, detail="The brain's address must be an https address.")
    organisation = await reglages_cerveau.organisation_des_reglages(user)
    actuels = await reglages_cerveau.lire(organisation)
    cle_ref = actuels.cle_ref
    cle = (demande.cle or "").strip()
    if cle:
        if not CLE_LONGUEUR[0] <= len(cle) <= CLE_LONGUEUR[1]:
            raise HTTPException(status_code=422, detail=f"A key holds {CLE_LONGUEUR[0]} to {CLE_LONGUEUR[1]} characters")
        donnees = {"token": cle, MARQUE_CLE_DU_CERVEAU: True, "format": demande.format}
        existante = await db_client.get_credential_by_uuid(cle_ref, organisation) if cle_ref else None
        if existante is not None:
            await db_client.update_credential(cle_ref, organisation, credential_data=donnees)
        else:
            try:
                creee = await db_client.create_credential(
                    organization_id=organisation,
                    user_id=user.id,
                    name=NOM_CLE_DU_CERVEAU,
                    credential_type=WebhookCredentialType.BEARER_TOKEN.value,
                    credential_data=donnees,
                )
            except Exception:  # noqa: BLE001 -- jamais le détail : il pourrait contenir la valeur
                raise HTTPException(status_code=500, detail="Key not saved") from None
            cle_ref = creee.credential_uuid
    reglages = ReglagesCerveau(**demande.model_dump(exclude={"cle"}), cle_ref=cle_ref)
    await reglages_cerveau.ecrire(organisation, reglages)
    return await reglages_cerveau.vue(organisation)


class Preferences(BaseModel):
    texte: str = Field(default="", max_length=5000)


@router.get("/preferences", response_model=Preferences)
async def lire_les_preferences(user: UserModel = Depends(get_user_with_selected_organization)):
    return Preferences(texte=await contexte.preferences(user.id))


@router.put("/preferences", response_model=Preferences)
async def ecrire_les_preferences(demande: Preferences, user: UserModel = Depends(get_user_with_selected_organization)):
    await contexte.ecrire_preferences(user.id, demande.texte)
    return demande

