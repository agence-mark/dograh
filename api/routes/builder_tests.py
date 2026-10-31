"""[.mark] Builder, lot 6 : la page « Tests et corrections » et la boucle d'amélioration (``/builder/tests``).

- ``GET    /builder/tests/{agent}``                          les tests, leur dernière exécution, l'état de la publication ;
- ``POST   /builder/tests/{agent}``                          créer un test (depuis un appel, à la main) : MÊME fonction que l'action ``tests_creer`` ;
- ``GET    /builder/tests/{agent}/{test}``                   le détail : le test et ses 3 dernières exécutions (conversation, raisons) ;
- ``PATCH  /builder/tests/{agent}/{test}``                   obligatoire, dossier ;
- ``DELETE /builder/tests/{agent}/{test}``                   supprimer ;
- ``POST   /builder/tests/{agent}/rejouer``                  rejouer la suite : MÊME fonction que l'action ``tests_rejouer`` ;
- ``GET    /builder/tests/{agent}/publication``              ce qui bloque la publication (contrôle du prompt, tests obligatoires) ;
- ``GET    /builder/tests/{agent}/export``                   un fichier téléchargeable pour le labo ;
- ``GET    /builder/tests/{agent}/corrections`` · ``POST .../{id}/retour``   l'historique des corrections et le retour arrière ;
- ``POST   /builder/tests/{agent}/juge/notes``               noter un avis du juge (calibration) ;
- ``GET    /builder/tests/recette/{famille}/{slug}/agents``  les agents qui utilisent une recette (B30) · ``POST .../preparer`` les brouillons.

Tout est lu et écrit AVEC l'organisation de l'utilisateur ; un agent d'une autre organisation est un 404.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user_with_selected_organization
from api.services.builder import actions  # noqa: F401 -- remplit le registre
from api.services.builder.actions import controle_et_tests
from api.services.builder.actions.registre import Contexte, executer
from api.services.builder.bibliotheque.service import ErreurBibliotheque
from api.services.builder.controle.service import controler_l_agent
from api.services.builder.tests_agent import boucle, creation, export, juge, mise_a_jour, publication, stockage

router = APIRouter(prefix="/builder/tests", tags=["builder-tests"])


async def _agent_ou_404(user: UserModel, workflow_id: int):
    workflow = await db_client.get_workflow(workflow_id, organization_id=user.selected_organization_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


def _ou_http(resultat: dict[str, Any]) -> dict[str, Any]:
    if resultat.get("ok") is False and resultat.get("erreur") and "disponible" not in resultat:
        raise HTTPException(status_code=422 if not resultat.get("code") == "introuvable" else 404, detail=resultat["erreur"])
    return resultat


class CreerUnTest(controle_et_tests._TestACreer):
    pass


class RejouerLaSuite(BaseModel):
    tests: list[str] | None = None
    repetitions: int = Field(default=3, ge=1, le=10)


class ChangerUnTest(BaseModel):
    obligatoire: bool | None = None
    dossier: str | None = Field(default=None, max_length=80)


class NoteDuJuge(BaseModel):
    identifiant: str = Field(min_length=1, max_length=200)
    ok: bool


class Preparer(BaseModel):
    rejouer_la_suite: bool = True


@router.get("/recette/{famille}/{slug}/agents")
async def agents_d_une_recette(famille: str, slug: str, user: UserModel = Depends(get_user_with_selected_organization)):
    try:
        return await mise_a_jour.agents_qui_utilisent(famille, slug)
    except ErreurBibliotheque as erreur:
        raise HTTPException(status_code=404, detail=str(erreur)) from None


@router.post("/recette/{famille}/{slug}/preparer")
async def preparer_les_mises_a_jour(
    famille: str, slug: str, corps: Preparer, user: UserModel = Depends(get_user_with_selected_organization)
):
    try:
        return await mise_a_jour.preparer(Contexte(user=user), famille, slug, rejouer_la_suite=corps.rejouer_la_suite)
    except ErreurBibliotheque as erreur:
        raise HTTPException(status_code=404, detail=str(erreur)) from None


@router.get("/{workflow_id}")
async def lire_les_tests(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    workflow = await _agent_ou_404(user, workflow_id)
    org = user.selected_organization_id
    lignes = []
    for test in await stockage.lister(org, workflow.id):
        derniere = await stockage.derniere_execution(org, workflow.id, test["slug"])
        lignes.append(
            {
                **creation.en_resume(test),
                "derniere": None
                if derniere is None
                else {k: derniere.get(k) for k in ("le", "version", "statut", "reussis", "total")},
            }
        )
    return {"tests": lignes, "personnages_disponibles": True}


@router.post("/{workflow_id}")
async def creer_un_test(workflow_id: int, corps: CreerUnTest, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    arguments = corps.model_dump(exclude={"workflow_id"})
    return _ou_http(await executer("tests_creer", {**arguments, "workflow_id": workflow_id}, Contexte(user=user, workflow_id=workflow_id)))


@router.post("/{workflow_id}/rejouer")
async def rejouer_la_suite(workflow_id: int, corps: RejouerLaSuite, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    arguments = {"workflow_id": workflow_id, **corps.model_dump()}
    return _ou_http(await executer("tests_rejouer", arguments, Contexte(user=user, workflow_id=workflow_id)))


@router.get("/{workflow_id}/publication")
async def etat_de_la_publication(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    """Ce qui bloquerait la publication du brouillon maintenant (le contrôle et les tests obligatoires)."""
    workflow = await _agent_ou_404(user, workflow_id)
    org = user.selected_organization_id
    draft = await db_client.get_draft_version(workflow.id)
    if draft is None:
        return {"brouillon": False, "bloque": False, "controle": None, "tests_obligatoires": []}
    controle = await controler_l_agent(workflow, org, graphe=draft.workflow_json)
    tests = await publication.problemes_des_tests_obligatoires(
        org, workflow.id, draft.version_number, publication.empreinte_du_brouillon_publie(draft)
    )
    suivi = await publication.agent_suivi(org, workflow.id)
    return {
        "brouillon": True,
        "version": draft.version_number,
        "suivi": suivi,
        "bloque": suivi and (not controle["ok"] or bool(tests)),
        "controle": controle,
        "tests_obligatoires": tests,
    }


@router.get("/{workflow_id}/export")
async def exporter_les_tests(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    workflow = await _agent_ou_404(user, workflow_id)
    lot = await export.exporter(user.selected_organization_id, workflow.id, workflow.name)
    return Response(
        content=export.en_octets(lot),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="tests-agent-{workflow.id}.json"'},
    )


@router.get("/{workflow_id}/corrections")
async def historique_des_corrections(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    return {"corrections": await boucle.historique(user.selected_organization_id, workflow_id)}


@router.post("/{workflow_id}/corrections/{correction_id}/retour")
async def retour_arriere(workflow_id: int, correction_id: str, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    try:
        return await boucle.retour_arriere(user.selected_organization_id, workflow_id, correction_id)
    except boucle.RetourImpossible as erreur:
        raise HTTPException(status_code=409, detail=str(erreur)) from None


@router.post("/{workflow_id}/juge/notes")
async def noter_le_juge(workflow_id: int, corps: NoteDuJuge, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    await juge.noter(user.selected_organization_id, workflow_id, corps.identifiant, corps.ok)
    return {"ok": True, "notes": len(await juge.notes(user.selected_organization_id, workflow_id))}


@router.get("/{workflow_id}/{slug}")
async def lire_un_test(workflow_id: int, slug: str, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    org = user.selected_organization_id
    try:
        test = await stockage.lire(org, workflow_id, slug)
    except stockage.ErreurTest as erreur:
        raise HTTPException(status_code=404, detail=str(erreur)) from None
    return {"test": test, "resultats": await stockage.resultats(org, workflow_id, slug)}


@router.patch("/{workflow_id}/{slug}")
async def changer_un_test(workflow_id: int, slug: str, corps: ChangerUnTest, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    try:
        test = await stockage.changer(user.selected_organization_id, workflow_id, slug, obligatoire=corps.obligatoire, dossier=corps.dossier)
    except stockage.ErreurTest as erreur:
        raise HTTPException(status_code=404, detail=str(erreur)) from None
    return creation.en_resume(test)


@router.delete("/{workflow_id}/{slug}")
async def supprimer_un_test(workflow_id: int, slug: str, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    if not await stockage.supprimer(user.selected_organization_id, workflow_id, slug):
        raise HTTPException(status_code=404, detail="Unknown test")
    return {"ok": True}
