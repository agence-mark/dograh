"""[.mark] Chantier Partie 1, lot 17 : le côté serveur de l'écran des gabarits (aucun écran ici : Partie 2).

- ``GET  /gabarits/{nom}``                                   le gabarit en lecture seule : version, empreinte, trous, missions, styles proposés ;
- ``POST /gabarits/{nom}/formulaire/controle``               le contrôle d'un formulaire (A, B, signalements), rien n'est écrit ;
- ``POST /gabarits/{nom}/agents``                             crée l'agent d'un restaurant depuis le gabarit (seul A bloque), par le moteur
                                                              « Nouveau client » (étape « L'agent ») ;
- ``GET  /gabarits/agents/{workflow_id}``                    l'état d'un agent installé : version du gabarit et du fork, trous, données B qui
                                                              manquent, retouches, porte, rodage (lu par le portail) ;
- ``POST /gabarits/agents/{workflow_id}/porte``              rejoue les tests générés sans modèle (la porte d'acceptation) ;
- ``POST /gabarits/agents/{workflow_id}/tests/regenerer``    réécrit les tests générés (carte ou gabarit changé) ;
- ``POST /gabarits/agents/{workflow_id}/appels/{run_id}/relu`` marque un vrai appel relu (rodage, D28) ;
- ``POST /gabarits/{nom}/diffusions``                        diffuse une version (« organisation » ou « toutes », D59) ;
- ``GET  /gabarits/{nom}/diffusions``                        le journal des diffusions.

L'organisation est celle de la SESSION (``get_user`` l'a contrôlée) ; un agent d'une autre organisation est un 404. Chaque route a sa décision
au registre (``registre_routes``). Un refus rend une phrase courte, jamais un texte interne.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user_with_selected_organization
from api.services.gabarits import diffusion as D
from api.services.gabarits import formulaire as F
from api.services.gabarits import gabarit as G
from api.services.gabarits import styles as ST

router = APIRouter(prefix="/gabarits", tags=["gabarits"])


def _gabarit(nom: str) -> G.Gabarit:
    if nom != G.RESTAURATION:
        raise HTTPException(status_code=404, detail="Template not found.")
    return G.charger(nom)


async def _application(user: UserModel, workflow_id: int) -> dict[str, Any]:
    a = await db_client.application_de(user.selected_organization_id, workflow_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return a


class DemandeDeFormulaire(BaseModel):
    formulaire: dict[str, Any] = Field(default_factory=dict)


class DemandeDeDiffusion(BaseModel):
    version: int = Field(ge=1)
    portee: Literal["organisation", "toutes"]


@router.get("/{nom}")
async def lire_le_gabarit(nom: str, user: UserModel = Depends(get_user_with_selected_organization)):
    g = _gabarit(nom)
    return {
        "nom": g.nom,
        "version": g.version,
        "empreinte": g.empreinte,
        "verrouille": True,
        "trous": sorted(g.trous),
        "variables_d_appel": g.variables_d_appel,
        "missions": {k: v["libelle"] for k, v in g.definition["missions"].items()},
        "etapes": list(g.definition["etapes"]),
        "styles": [{"nom": n, "libelle": ST.STYLES[n].libelle, "texte": ST.STYLES[n].texte} for n in ST.proposes()],
        "niveaux": {cle: {"niveau": d.niveau, "libelle": d.libelle} for cle, d in F.DONNEES.items()},
        "outils_sans_action": G.outils_sans_action(g),
    }


@router.post("/{nom}/formulaire/controle")
async def controler_un_formulaire(nom: str, demande: DemandeDeFormulaire, user: UserModel = Depends(get_user_with_selected_organization)):
    _gabarit(nom)
    c = F.controler(demande.formulaire)
    return {"creation_permise": c.creation_permise, "a_manquer": c.a_manquer, "b_manquer": c.b_manquer, "signalements": c.signalements}


@router.post("/{nom}/agents")
async def creer_depuis_le_gabarit(nom: str, demande: DemandeDeFormulaire, user: UserModel = Depends(get_user_with_selected_organization)):
    from api.services.base_client import rattachement
    from api.services.gabarits.installation import installer_un_restaurant

    _gabarit(nom)
    c = F.controler(demande.formulaire)
    if not c.creation_permise:
        raise HTTPException(status_code=422, detail={"code": "gabarit_formulaire_incomplet", "a_manquer": c.a_manquer})
    nom_base = await rattachement.nom_de_la_base(user.selected_organization_id)
    if not nom_base:
        raise HTTPException(status_code=409, detail={"code": "base_requise"})
    r = await installer_un_restaurant(user, user.selected_organization_id, demande.formulaire, nom_base=nom_base)
    if r["echec"] is not None:
        raise HTTPException(status_code=422, detail={k: r["echec"][k] for k in ("etape", "code", "fr", "en", "precisions") if k in r["echec"]})
    return {"application": _vue(r["application"]), "b_manquer": r["etape_6"].get("b_manquer", []), "signalements": r["etape_6"].get("signalements", [])}


def _vue(a: dict[str, Any] | None) -> dict[str, Any] | None:
    if a is None:
        return None
    return {
        "workflow_id": a["workflow_id"],
        "agents": {k: v for k, v in a["agents"].items() if not k.startswith("_")},
        "gabarit": {"nom": a["gabarit_nom"], "version": a["gabarit_version"]},
        "commit_fork": a["commit_fork"],
        "trous": a["trous"],
        "installee_le": a["installee_le"],
    }


@router.get("/agents/{workflow_id}")
async def etat_d_un_agent(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    from api.db.bases_clients.restauration_formulaire import faits_de_l_etablissement
    from api.services.gabarits.installation import _base_du_client

    a = await _application(user, workflow_id)
    connexion = await _base_du_client(user.selected_organization_id)
    try:
        faits = await faits_de_l_etablissement(connexion, a["formulaire"]["etablissement_id"])
    finally:
        await connexion.close()
    verte, problemes = await D.porte_verte(user.selected_organization_id, a)
    return {
        **_vue(a),
        "b_manquer": F.controler(a["formulaire"], faits).b_manquer,
        "retouches": {e: await D.retouches_de_l_agent(user.selected_organization_id, a, e) for e in a["agents"] if not e.startswith("_")},
        "porte": {"verte": verte, "problemes": [{k: p.get(k) for k in ("etape", "slug", "nom", "code")} for p in problemes][:200]},
        "rodage": await D.etat_du_rodage(user.selected_organization_id, workflow_id),
    }


@router.post("/agents/{workflow_id}/porte")
async def rejouer_la_porte(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    from api.services.gabarits.tests_generes import jouer_les_tests_du_code

    a = await _application(user, workflow_id)
    return await jouer_les_tests_du_code(user.selected_organization_id, a)


@router.post("/agents/{workflow_id}/tests/regenerer")
async def regenerer_les_tests(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    """La carte ou le gabarit a changé : réécrit les tests obligatoires générés de l'agent (un test écrit à la main n'est jamais touché)."""
    from api.services.gabarits.tests_generes import regenerer

    await _application(user, workflow_id)
    return {"tests": await regenerer(user.selected_organization_id, workflow_id)}


@router.post("/agents/{workflow_id}/appels/{run_id}/relu")
async def marquer_un_appel_relu(workflow_id: int, run_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    await _application(user, workflow_id)
    etat = await D.noter_un_appel_relu(user.selected_organization_id, workflow_id, run_id)
    if etat is None:
        raise HTTPException(status_code=404, detail="Call not found among this agent's real calls.")
    return etat


@router.post("/{nom}/diffusions")
async def diffuser_une_version(nom: str, demande: DemandeDeDiffusion, user: UserModel = Depends(get_user_with_selected_organization)):
    _gabarit(nom)
    try:
        ligne = await D.diffuser(user, nom=nom, version=demande.version, portee=demande.portee, organization_id=user.selected_organization_id)
    except D.RefusDiffusion as refus:
        raise HTTPException(status_code=refus.statut, detail={"code": refus.code, "message": refus.message}) from None
    return {k: ligne[k] for k in ("id", "gabarit_nom", "gabarit_version", "portee", "statut", "resultat", "le")}


@router.get("/{nom}/diffusions")
async def journal_des_diffusions(nom: str, user: UserModel = Depends(get_user_with_selected_organization)):
    """Celles qui visaient l'organisation de la session ; toutes pour un rôle qui peut diffuser partout."""
    _gabarit(nom)
    partout = await D._peut_diffuser_partout(user)
    lignes = await db_client.diffusions_de(nom, organization_id=None if partout else user.selected_organization_id)
    return [{k: l[k] for k in ("id", "gabarit_version", "portee", "organization_id", "par_user_id", "statut", "le")} for l in lignes]
