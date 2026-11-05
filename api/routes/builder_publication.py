"""[.mark] U11 : la fenêtre « Publier vX » et « Attaquer l'agent » (``/builder/publication``, ``/builder/attaques``).

- ``GET  /builder/publication/{agent}``                          les contrôles sur le brouillon (même fonction que l'action) ;
- ``PUT  /builder/publication/{agent}/reglages``                 les trois positions de chaque contrôle, le déploiement (brouillon) ;
- ``POST /builder/publication/{agent}/liste-vocale/corriger``    écrire les corrections ACCEPTÉES ;
- ``POST /builder/publication/{agent}/corriger-un-reglage``      la correction en un clic d'un réglage sans effet (« Prêt à publier ») ;
- (la part des appels vit dans ``/builder/branches`` : un seul mécanisme de répartition du trafic) ;
- ``GET  /builder/attaques/catalogue`` · ``GET|POST /builder/attaques/{agent}[/lancer|/rejouer]`` ;
- ``GET|POST /builder/attaques/jeu-public[/importer]`` le jeu public fourni par une personne ;
- ``POST /builder/attaques/{agent}/creer-des-tests`` · ``/envoyer-a-ameliorer`` ce qu'on fait des attaques qui ont cédé.

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
        code = {"introuvable": 404, "sans_brouillon": 409, "rien_a_envoyer": 409}.get(resultat.get("code") or "", 422)
        raise HTTPException(status_code=code, detail=resultat["erreur"])
    return resultat


async def _action(nom: str, user: UserModel, workflow_id: int, **arguments: Any) -> dict[str, Any]:
    await _agent_ou_404(user, workflow_id)
    contexte = Contexte(user=user, workflow_id=workflow_id)
    return _ou_http(await executer(nom, {"workflow_id": workflow_id, **arguments}, contexte))


class Corriger(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=1, max_length=20)


class CorrigerUnReglage(BaseModel):
    """La correction en un clic d'un réglage « sans effet » : l'identifiant que la liste « Prêt à publier » a proposé, et l'étape ou
    la liaison qu'il vise. Le serveur ne joue que ce que le brouillon propose."""

    model_config = ConfigDict(extra="forbid")
    correction: str = Field(min_length=1, max_length=80)
    noeud_id: str | None = Field(default=None, max_length=100)
    liaison_id: str | None = Field(default=None, max_length=100)


class Lancer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profondeur: str = Field(default="rapide", pattern="^(rapide|standard|poussee)$")
    confirme: bool = False
    modifie_l_environnement: bool = False
    corrige: bool = False
    essais: int | None = Field(default=None, ge=1, le=5)
    temoin: bool = True
    jeu: str = Field(default="catalogue", pattern="^(catalogue|public)$")


class ChoixDAttaques(BaseModel):
    """Les attaques du dernier rapport à traiter ; vide = celles qui ont cédé de façon confirmée."""

    model_config = ConfigDict(extra="forbid")
    ids: list[str] | None = Field(default=None, max_length=50)


class JeuPublic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contenu: str = Field(min_length=1, max_length=12_000_000)


# --- publication ----------------------------------------------------------------------------------------------------------


@router.get("/builder/publication/{workflow_id}")
async def controles_de_publication(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    return await _action("publication_controler", user, workflow_id)


@router.get("/builder/publication/{workflow_id}/changements")
async def changements_du_brouillon(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    """« Ce qui change » de la fenêtre Publier : le brouillon comparé à la version publiée, avant et après (lecture seule)."""
    from api.services.publication import changements

    workflow = await _agent_ou_404(user, workflow_id)
    brouillon = await db_client.get_draft_version(workflow_id)
    if brouillon is None:
        raise HTTPException(status_code=409, detail="There is no draft: nothing to compare with the published version.")
    publiee = getattr(workflow, "released_definition", None)
    calcul = changements.calculer(
        brouillon.workflow_json,
        getattr(publiee, "workflow_json", None),
        brouillon.workflow_configurations,
        getattr(publiee, "workflow_configurations", None),
    )
    return {
        "version_brouillon": brouillon.version_number,
        "version_publiee": getattr(publiee, "version_number", None),
        "publiee_le": getattr(publiee, "published_at", None),
        **calcul,
    }


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


@router.post("/builder/publication/{workflow_id}/corriger-un-reglage")
async def corriger_un_reglage(workflow_id: int, corps: CorrigerUnReglage, user: UserModel = Depends(get_user_with_selected_organization)):
    """« Prêt à publier » : la correction en un clic d'un réglage sans effet, écrite dans le BROUILLON ; rend la liste recalculée."""
    from api.services.equipe_mark.acces import journaliser
    from api.services.publication import corriger_reglage, sans_effet

    workflow = await _agent_ou_404(user, workflow_id)
    try:
        vue = await corriger_reglage.corriger(
            workflow, user.selected_organization_id, corps.correction, noeud_id=corps.noeud_id, liaison_id=corps.liaison_id
        )
    except corriger_reglage.CorrectionIntrouvable as erreur:
        raise HTTPException(status_code=409, detail=str(erreur)) from None
    except sans_effet.CorrectionRefusee as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from None
    await journaliser(user, "agents.corriger_un_reglage", user.selected_organization_id, {"agent": workflow_id, "correction": corps.correction})
    return {"ok": True, **vue}


# --- les défauts de l'organisation (thème « Publication » des Réglages) --------------------------------------------------


@router.get("/builder/publication-organisation", response_model=Publication)
async def defauts_de_l_organisation(user: UserModel = Depends(get_user_with_selected_organization)):
    from api.services.publication import defauts_org

    return await defauts_org.lire(user.selected_organization_id) or Publication()


@router.put("/builder/publication-organisation", response_model=Publication)
async def regler_les_defauts_de_l_organisation(corps: Publication, user: UserModel = Depends(get_user_with_selected_organization)):
    """Les positions par défaut et l'interrupteur du déploiement progressif de l'organisation. Journalisé ; jamais par une clé d'API."""
    from api.services.equipe_mark.acces import est_par_cle_api, journaliser
    from api.services.publication import defauts_org

    if est_par_cle_api(user):
        raise HTTPException(status_code=403, detail="The organization's publication settings are not open to an API key")
    await defauts_org.ecrire(user.selected_organization_id, corps)
    await journaliser(
        user,
        "publication.defauts",
        user.selected_organization_id,
        {"deploiement": corps.deploiement.actif, "controles": corps.controles.model_dump()},
    )
    return corps


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


@router.get("/builder/attaques/jeu-public")
async def jeu_public(user: UserModel = Depends(get_user_with_selected_organization)):
    return _ou_http(await executer("attaques_jeu_public", {}, Contexte(user=user, workflow_id=None)))


@router.post("/builder/attaques/jeu-public/importer")
async def importer_le_jeu_public(corps: JeuPublic, user: UserModel = Depends(get_user_with_selected_organization)):
    return _ou_http(await executer("attaques_importer_le_jeu_public", corps.model_dump(), Contexte(user=user, workflow_id=None)))


@router.get("/builder/attaques/{workflow_id}")
async def dernier_rapport(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    return await _action("attaques_rapport", user, workflow_id)


@router.post("/builder/attaques/{workflow_id}/lancer")
async def lancer_les_attaques(workflow_id: int, corps: Lancer, user: UserModel = Depends(get_user_with_selected_organization)):
    return await _action("attaques_lancer", user, workflow_id, **corps.model_dump())


@router.post("/builder/attaques/{workflow_id}/rejouer")
async def rejouer_les_attaques(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    return await _action("attaques_rejouer", user, workflow_id)


@router.post("/builder/attaques/{workflow_id}/creer-des-tests")
async def creer_des_tests_depuis_les_attaques(workflow_id: int, corps: ChoixDAttaques, user: UserModel = Depends(get_user_with_selected_organization)):
    return await _action("attaques_creer_des_tests", user, workflow_id, **corps.model_dump())


@router.post("/builder/attaques/{workflow_id}/envoyer-a-ameliorer")
async def envoyer_les_attaques_dans_a_ameliorer(workflow_id: int, corps: ChoixDAttaques, user: UserModel = Depends(get_user_with_selected_organization)):
    return await _action("attaques_envoyer_a_ameliorer", user, workflow_id, **corps.model_dump())
