"""[.mark] builder partie 2, U8 : « À améliorer » (la boucle) et la page Qualité.

- ``GET  /ameliorations``                  les problèmes de l'organisation par état, le plus grave d'abord, avec les compteurs des quatre boîtes ;
- ``GET  /ameliorations/a-juger``          la file « À juger » (vrais appels rangés pour Claude Code) ;
- ``GET  /ameliorations/{id}``             le détail : cas regroupés, réplique fautive, cause, correction proposée, avancement ;
- ``PUT  /ameliorations/{id}``             l'état à la main (en cours, ignorer, rouvrir), la personne chargée, l'origine ;
- ``POST /ameliorations/{id}/test``        crée un test depuis la réplique fautive (même fonction que l'action ``tests_creer``) ;
- ``POST /ameliorations/{id}/rejouer``     rejoue toute la suite de l'agent (même fonction que l'action ``tests_rejouer``) ;
- ``GET  /qualite``                        les indicateurs, les motifs, les agents et la comparaison des versions (sur 7 ou 30 jours).

⛔ Tout passe par l'organisation de l'utilisateur : un problème d'une autre organisation est un 404. Aucune route n'écrit un état
« Testée » ou « Publiée » à la main : seuls le rejeu complet vert et la publication les posent.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user_with_selected_organization
from api.services.boucle import qualite, vues
from api.services.builder import actions  # noqa: F401 -- remplit le registre
from api.services.builder.actions.registre import Contexte, executer
from api.services.juge import file as file_du_juge

router = APIRouter(tags=["ameliorations"])

EtatAMain = Literal["a_trier", "en_cours", "ignoree"]
Origine = Literal["client", "recette", "code"]


class VueDeLigne(BaseModel):
    id: int
    workflow_id: int
    workflow_nom: str
    titre: str
    critere: str | None = None
    etape: str | None = None
    gravite: int
    frequence: dict[str, Any]
    releve_par: str
    cause: str | None = None
    etat: str
    origine: str | None = None
    origine_suggeree: str
    assigne: int | None = None
    version: int | None = None
    derniere_le: str | None = None


class PageDAmeliorations(BaseModel):
    lignes: list[VueDeLigne]
    page: int
    a_une_suite: bool
    compteurs: dict[str, int]


class VueDetaillee(VueDeLigne):
    replique: str | None = None
    confiance: float | None = None
    correction: dict[str, Any] | None = None
    cas: list[dict[str, Any]]
    nb_cas: int
    avancement: list[dict[str, Any]]
    recettes: list[dict[str, Any]]


class ChangementDAmelioration(BaseModel):
    etat: EtatAMain | None = None
    assigne: int | None = None
    origine: Origine | None = None


class LigneAJuger(BaseModel):
    id: str
    type: str
    workflow_id: int | None = None
    workflow_nom: str = ""
    run_id: int | None = None
    test: str | None = None
    le: str | None = None
    duree: float | None = None
    motif: str | None = None


class TestDepuisUnProbleme(BaseModel):
    # Sans critères, un problème du juge prend « l'agent ne redit pas cette réplique » ; un autre problème doit les donner.
    criteres: list[dict[str, Any]] | None = None


class Rejeu(BaseModel):
    ok: bool
    reussis: int
    total: int
    suite_complete: bool
    etat: str


async def _probleme_ou_404(user: UserModel, amelioration_id: int) -> dict[str, Any]:
    probleme = await db_client.lire_une_amelioration(user.selected_organization_id, amelioration_id)
    if probleme is None:
        raise HTTPException(status_code=404, detail="Improvement not found")
    return probleme


@router.get("/ameliorations", response_model=PageDAmeliorations)
async def lire_les_ameliorations(
    etat: Literal["a_trier", "en_cours", "testee", "publiee"] = Query("a_trier"),
    workflow_id: int | None = Query(None),
    page: int = Query(0, ge=0),
    user: UserModel = Depends(get_user_with_selected_organization),
) -> dict[str, Any]:
    return await vues.liste(user.selected_organization_id, etat=etat, workflow_id=workflow_id, page=page)


@router.get("/ameliorations/a-juger", response_model=list[LigneAJuger])
async def lire_la_file_a_juger(user: UserModel = Depends(get_user_with_selected_organization)) -> list[dict[str, Any]]:
    organisation = user.selected_organization_id
    elements = await file_du_juge.lister(organisation)
    resumes = await db_client.resumes_de_runs(organisation, [int(e["run_id"]) for e in elements if e.get("run_id")])
    noms = await db_client.noms_des_agents(organisation, sorted({int(e["workflow_id"]) for e in elements if e.get("workflow_id")}))
    lignes = []
    for e in elements:
        resume = resumes.get(int(e["run_id"])) if e.get("run_id") else None
        lignes.append(
            {
                "id": e["id"],
                "type": e.get("type", "appel"),
                "workflow_id": e.get("workflow_id"),
                "workflow_nom": noms.get(int(e["workflow_id"]), "") if e.get("workflow_id") else "",
                "run_id": e.get("run_id"),
                "test": e.get("test"),
                "le": (resume["cree_le"].isoformat() if resume and resume.get("cree_le") else e.get("le")),
                "duree": resume.get("duree") if resume else None,
                "motif": resume.get("motif") if resume else None,
            }
        )
    return lignes


@router.get("/ameliorations/{amelioration_id}", response_model=VueDetaillee)
async def lire_une_amelioration(amelioration_id: int, user: UserModel = Depends(get_user_with_selected_organization)) -> dict[str, Any]:
    probleme = await _probleme_ou_404(user, amelioration_id)
    return await vues.detail(user.selected_organization_id, probleme)


@router.put("/ameliorations/{amelioration_id}", response_model=VueDetaillee)
async def changer_une_amelioration(
    amelioration_id: int, corps: ChangementDAmelioration, user: UserModel = Depends(get_user_with_selected_organization)
) -> dict[str, Any]:
    organisation = user.selected_organization_id
    probleme = await _probleme_ou_404(user, amelioration_id)
    champs = corps.model_fields_set
    if not champs:
        raise HTTPException(status_code=422, detail="Nothing to change")
    changes: dict[str, Any] = {}
    if "etat" in champs and corps.etat is not None:
        # « Testée » et « Publiée » ne se posent jamais à la main : le rejeu vert et la publication les posent.
        if probleme["etat"] in ("testee", "publiee") and corps.etat != "ignoree":
            raise HTTPException(status_code=409, detail="This problem was tested or published: only ignoring it is possible")
        changes["etat"] = corps.etat
    if "assigne" in champs:
        if corps.assigne is not None and not await db_client.is_user_member_of_organization(corps.assigne, organisation):
            raise HTTPException(status_code=404, detail="User not found in this organization")
        changes["assigne"] = corps.assigne
    if "origine" in champs and corps.origine is not None:
        changes["origine"] = corps.origine
    ecrit = await db_client.modifier_une_amelioration(organisation, amelioration_id, **changes)
    if ecrit is None:
        raise HTTPException(status_code=404, detail="Improvement not found")
    return await vues.detail(organisation, ecrit)


def _resultat_ou_http(resultat: dict[str, Any]) -> dict[str, Any]:
    if resultat.get("ok") is False and resultat.get("erreur"):
        raise HTTPException(status_code=422, detail=resultat["erreur"])
    return resultat


@router.post("/ameliorations/{amelioration_id}/test")
async def creer_un_test_depuis_la_replique(
    amelioration_id: int,
    corps: TestDepuisUnProbleme | None = None,
    user: UserModel = Depends(get_user_with_selected_organization),
) -> dict[str, Any]:
    """Un test depuis le cas le plus récent qui a un appel et un rang : l'appel est relu avec l'organisation, le test est rendu fictif."""
    organisation = user.selected_organization_id
    probleme = await _probleme_ou_404(user, amelioration_id)
    cas = next((c for c in reversed(probleme["cas"]) if c.get("run_id") and c.get("rang")), None)
    if cas is None:
        raise HTTPException(status_code=422, detail="No call with a faulty reply to build a test from")
    criteres = (corps.criteres if corps else None) or []
    if not criteres and probleme["releve_par"] == "juge" and probleme.get("replique"):
        criteres = [{"type": "texte_absent", "texte": probleme["replique"][:60]}]
    if not criteres:
        raise HTTPException(status_code=422, detail="Give the criteria of the test: this problem has no reply to forbid")
    contexte = Contexte(user=user, workflow_id=probleme["workflow_id"])
    resultat = _resultat_ou_http(
        await executer(
            "tests_creer",
            {
                "workflow_id": probleme["workflow_id"],
                "nom": probleme["titre"][:120],
                "criteres": criteres,
                "run_id": cas["run_id"],
                "rang": cas["rang"],
                "origine": "recette" if vues.origine_suggeree(probleme) == "recette" else "code",
            },
            contexte,
        )
    )
    await db_client.modifier_une_amelioration(
        organisation, amelioration_id, avancement={**probleme["avancement"], "test_cree": True}
    )
    return resultat


@router.post("/ameliorations/{amelioration_id}/rejouer", response_model=Rejeu)
async def rejouer_la_suite_de_l_agent(
    amelioration_id: int, user: UserModel = Depends(get_user_with_selected_organization)
) -> dict[str, Any]:
    probleme = await _probleme_ou_404(user, amelioration_id)
    contexte = Contexte(user=user, workflow_id=probleme["workflow_id"])
    rendu = _resultat_ou_http(await executer("tests_rejouer", {"workflow_id": probleme["workflow_id"], "repetitions": 3}, contexte))
    apres = await db_client.lire_une_amelioration(user.selected_organization_id, amelioration_id)
    return {
        "ok": bool(rendu.get("ok")),
        "reussis": int(rendu.get("reussis") or 0),
        "total": int(rendu.get("total") or 0),
        "suite_complete": bool(rendu.get("suite_complete")),
        "etat": (apres or probleme)["etat"],
    }


@router.get("/qualite")
async def lire_la_qualite(
    jours: int = Query(7),
    workflow_id: int | None = Query(None),
    user: UserModel = Depends(get_user_with_selected_organization),
) -> dict[str, Any]:
    # Une adresse envoie « 7 » ou « 30 » en texte : un `Literal[7, 30]` le refusait toujours (422), la page Qualité restait en erreur.
    if jours not in (7, 30):
        raise HTTPException(status_code=422, detail="jours doit valoir 7 ou 30")
    return await qualite.calculer(user.selected_organization_id, jours=jours, workflow_id=workflow_id)
