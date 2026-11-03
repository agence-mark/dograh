"""[.mark] U11 : la fenêtre « Publier vX » et « Attaquer l'agent » (``/builder/publication``, ``/builder/attaques``).

- ``GET  /builder/publication/{agent}``                          les contrôles sur le brouillon (même fonction que l'action) ;
- ``PUT  /builder/publication/{agent}/reglages``                 les trois positions de chaque contrôle, le déploiement (brouillon) ;
- ``POST /builder/publication/{agent}/liste-vocale/corriger``    écrire les corrections ACCEPTÉES ;
- ``GET  /builder/publication/{agent}/deploiement``              la part en cours ;
- ``POST /builder/publication/{agent}/deploiement/passer-a-100`` · ``.../revenir``   gestes humains, jamais automatiques ;
- ``GET  /builder/attaques/catalogue`` · ``GET|POST /builder/attaques/{agent}[/lancer|/rejouer]``.

Tout est lu et écrit AVEC l'organisation de l'utilisateur ; un agent d'une autre organisation est un 404.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.db import db_client
from api.db.models import UserModel
from api.schemas.publication import Publication
from api.services.auth.depends import get_user_with_selected_organization
from api.services.builder import actions  # noqa: F401 -- remplit le registre
from api.services.builder.actions.registre import Contexte, executer

router = APIRouter(tags=["builder-publication"])


async def _agent_ou_404(user: UserModel, workflow_id: int):
    workflow = await db_client.get_workflow(workflow_id, organization_id=user.selected_organization_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


def _ou_http(resultat: dict[str, Any]) -> dict[str, Any]:
    if resultat.get("ok") is False and resultat.get("erreur"):
        code = {"introuvable": 404, "sans_brouillon": 409}.get(resultat.get("code") or "", 422)
        raise HTTPException(status_code=code, detail=resultat["erreur"])
    return resultat


async def _action(nom: str, user: UserModel, workflow_id: int, **arguments: Any) -> dict[str, Any]:
    await _agent_ou_404(user, workflow_id)
    contexte = Contexte(user=user, workflow_id=workflow_id)
    return _ou_http(await executer(nom, {"workflow_id": workflow_id, **arguments}, contexte))


class Corriger(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=1, max_length=20)


class Lancer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profondeur: str = Field(default="rapide", pattern="^(rapide|standard|poussee)$")
    confirme: bool = False
    modifie_l_environnement: bool = False
    corrige: bool = False


class Revenir(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1, description="The version number to go back to (an earlier published or archived version).")


# --- publication ----------------------------------------------------------------------------------------------------------


@router.get("/builder/publication/{workflow_id}")
async def controles_de_publication(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    return await _action("publication_controler", user, workflow_id)


@router.put("/builder/publication/{workflow_id}/reglages")
async def regler_la_publication(workflow_id: int, corps: Publication, user: UserModel = Depends(get_user_with_selected_organization)):
    from api.services.builder import reglages_agent

    await _agent_ou_404(user, workflow_id)
    try:
        await reglages_agent.regler(user.selected_organization_id, workflow_id, {"publication": corps.model_dump()})
    except reglages_agent.ErreurReglage as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from None
    return {"ok": True, "publication": corps.model_dump()}


@router.post("/builder/publication/{workflow_id}/liste-vocale/corriger")
async def corriger_la_liste_vocale(workflow_id: int, corps: Corriger, user: UserModel = Depends(get_user_with_selected_organization)):
    return await _action("publication_corriger_la_liste_vocale", user, workflow_id, ids=corps.ids)


@router.get("/builder/publication/{workflow_id}/deploiement")
async def deploiement_en_cours(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    from api.services.publication import deploiement

    await _agent_ou_404(user, workflow_id)
    ligne = await deploiement.lire(user.selected_organization_id, workflow_id)
    versions = await db_client.get_workflow_versions(workflow_id, limit=50)
    numeros = {v.id: v.version_number for v in versions}
    if ligne is None:
        return {"en_cours": False}
    return {
        "en_cours": True,
        "pourcentage": ligne.get("pourcentage"),
        "nouvelle": numeros.get(ligne.get("nouvelle")),
        "precedente": numeros.get(ligne.get("precedente")),
    }


@router.post("/builder/publication/{workflow_id}/deploiement/passer-a-100")
async def passer_a_100(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    from api.services.equipe_mark.acces import journaliser
    from api.services.publication import deploiement

    await _agent_ou_404(user, workflow_id)
    resultat = await deploiement.passer_a_100(user.selected_organization_id, workflow_id)
    await journaliser(user, "agents.deploiement_100", user.selected_organization_id, {"agent": workflow_id})
    return {"ok": True, **resultat}


@router.post("/builder/publication/{workflow_id}/deploiement/revenir")
async def revenir_a_une_version(workflow_id: int, corps: Revenir, user: UserModel = Depends(get_user_with_selected_organization)):
    from api.services.equipe_mark.acces import journaliser
    from api.services.publication import deploiement

    await _agent_ou_404(user, workflow_id)
    versions = await db_client.get_workflow_versions(workflow_id, limit=100)
    cible = next((v for v in versions if v.version_number == corps.version and v.status in ("published", "archived")), None)
    if cible is None:
        raise HTTPException(status_code=404, detail="Published or archived agent version not found")
    try:
        ligne = await deploiement.revenir(user.selected_organization_id, workflow_id, cible.id, corps.version, str(user.id))
    except deploiement.ErreurDeploiement as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from None
    await journaliser(user, "agents.deploiement_retour", user.selected_organization_id, {"agent": workflow_id, "version": corps.version})
    return {"ok": True, "pourcentage": ligne["pourcentage"]}


# --- attaques -------------------------------------------------------------------------------------------------------------


@router.get("/builder/attaques/catalogue")
async def catalogue_des_attaques(user: UserModel = Depends(get_user_with_selected_organization)):
    from api.services.attaques import catalogue

    try:
        jeu = await catalogue.lire_le_jeu()
        regles = await catalogue.lire_les_regles()
    except catalogue.JeuIllisible as erreur:
        raise HTTPException(status_code=503, detail=str(erreur)) from None
    return {
        "mention": jeu["mention"],
        "techniques": [{k: t[k] for k in ("id", "nom", "but", "gravite_par_defaut")} | {"sondes": len(t["sondes"])} for t in jeu["techniques"]],
        "ecartees": jeu["ecartees"],
        "regles": regles,
    }


@router.get("/builder/attaques/{workflow_id}")
async def dernier_rapport(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    return await _action("attaques_rapport", user, workflow_id)


@router.post("/builder/attaques/{workflow_id}/lancer")
async def lancer_les_attaques(workflow_id: int, corps: Lancer, user: UserModel = Depends(get_user_with_selected_organization)):
    return await _action("attaques_lancer", user, workflow_id, **corps.model_dump())


@router.post("/builder/attaques/{workflow_id}/rejouer")
async def rejouer_les_attaques(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    return await _action("attaques_rejouer", user, workflow_id)
