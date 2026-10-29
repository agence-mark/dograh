"""[.mark] passages-fiables (lot G) : la file de tri et les alertes de Dograh.

- ``GET /tri`` : les signalements (de l'agent et du code) des appels des 30 derniers jours, 50 appels par page, filtre par
  agent et par statut ;
- ``PUT /tri/{run_id}`` : change le statut d'un signalement (``annotations["tri"]`` du run, rien d'autre ne bouge) ;
- ``GET /alertes`` : les alertes de l'organisation (problème du client). Le portail (écran .mark, côté client) lira cette
  route plus tard ; rien du portail n'est codé ici.

⛔ Tout est scopé par ``organization_id`` de l'utilisateur : une organisation ne lit ni ne modifie le tri ou les alertes
d'une autre. Les lectures sont bornées (30 jours, runs qui portent quelque chose, 50 par page).
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user_with_selected_organization
from api.services.tri import donnees, pages

router = APIRouter(tags=["tri"])

StatutDeTri = Literal["ouvert", "en cours", "résolu", "fusionné"]


class LigneDeTri(BaseModel):
    run_id: int
    workflow_id: int
    workflow_nom: str
    cree_le: Optional[str] = None
    id: str
    source: Literal["agent", "code"]
    type: str
    categorie: Optional[str] = None
    motif: str = ""
    etape: Optional[str] = None
    tour: Optional[int] = None
    statut: StatutDeTri


class PageDeTri(BaseModel):
    lignes: list[LigneDeTri]
    page: int
    a_une_suite: bool
    jours: int = donnees.JOURS_DE_LECTURE
    par_page: int = donnees.RUNS_PAR_PAGE
    # Filtre par statut : la borne de lecture est atteinte avant de remplir la page ; la recherche s'est arrêtée là.
    recherche_tronquee: bool = False


class ChangementDeStatut(BaseModel):
    identifiant: str
    statut: StatutDeTri


class StatutEcrit(BaseModel):
    run_id: int
    identifiant: str
    statut: StatutDeTri


class LigneDAlerte(BaseModel):
    run_id: int
    workflow_id: int
    workflow_nom: str
    cree_le: Optional[str] = None
    id: str
    type: str
    detail: Optional[str] = None
    etape: Optional[str] = None
    outil: Optional[str] = None
    tour: Optional[int] = None
    heure: Optional[str] = None
    # envoye · non_envoye · deja_notifiee · en_cours · null (pas de mail tenté)
    mail: Optional[str] = None


class PageDAlertes(BaseModel):
    lignes: list[LigneDAlerte]
    page: int
    a_une_suite: bool
    jours: int = donnees.JOURS_DE_LECTURE
    par_page: int = donnees.RUNS_PAR_PAGE


MAX_PAGES_DE_RUNS_LUES = 20  # borne R7 : au plus 20 pages de runs lues pour remplir une page filtrée


@router.get("/tri", response_model=PageDeTri)
async def lire_la_file_de_tri(
    page: int = Query(0, ge=0),
    workflow_id: Optional[int] = Query(None),
    statut: Optional[StatutDeTri] = Query(None),
    user: UserModel = Depends(get_user_with_selected_organization),
) -> PageDeTri:
    if statut is None:
        runs, suite = await db_client.runs_avec(
            user.selected_organization_id,
            chemin=donnees.chemin_des_runs_a_trier(),
            cles=donnees.CLES_LUES_POUR_LE_TRI,
            page=page,
            workflow_id=workflow_id,
        )
        return PageDeTri(lignes=pages.lignes_de_tri(runs), page=page, a_une_suite=suite)
    # Le statut se lit dans les annotations du run : le filtre passe AVANT de couper la page. On lit les pages de runs
    # (bornées) jusqu'à remplir celle demandée ; la page 1 filtrée n'est jamais vide quand des lignes existent.
    par_page = donnees.RUNS_PAR_PAGE
    voulu = (page + 1) * par_page + 1
    lignes: list[dict] = []
    lues, encore = 0, True
    while encore and len(lignes) < voulu and lues < MAX_PAGES_DE_RUNS_LUES:
        runs, encore = await db_client.runs_avec(
            user.selected_organization_id,
            chemin=donnees.chemin_des_runs_a_trier(),
            cles=donnees.CLES_LUES_POUR_LE_TRI,
            page=lues,
            workflow_id=workflow_id,
        )
        lignes.extend(pages.lignes_de_tri(runs, statut))
        lues += 1
    # Borne atteinte avant de remplir la page : on ne promet pas une suite qu'on n'a pas lue (une page vide « avec suite »
    # renvoyait l'écran dans le vide) ; la réponse dit que la recherche est tronquée.
    tronquee = encore and len(lignes) < voulu
    suite = len(lignes) > (page + 1) * par_page
    return PageDeTri(
        lignes=lignes[page * par_page : (page + 1) * par_page], page=page, a_une_suite=suite, recherche_tronquee=tronquee
    )


@router.put("/tri/{run_id}", response_model=StatutEcrit)
async def changer_le_statut_d_un_signalement(
    run_id: int,
    corps: ChangementDeStatut,
    user: UserModel = Depends(get_user_with_selected_organization),
) -> StatutEcrit:
    organisation = user.selected_organization_id
    run = await db_client.run_de_l_organisation(organisation, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    # L'identifiant doit désigner un signalement de CE run : on n'écrit jamais un statut dans le vide.
    signalement = next((s for s in donnees.lire_les_signalements(run["gathered_context"]) if s["id"] == corps.identifiant), None)
    if signalement is None:
        raise HTTPException(status_code=404, detail="Flag not found")
    if not await db_client.ecrire_le_tri(organisation, run_id, corps.identifiant, corps.statut, user.id):
        raise HTTPException(status_code=404, detail="Run not found")
    return StatutEcrit(run_id=run_id, identifiant=signalement["id"], statut=corps.statut)


@router.get("/alertes", response_model=PageDAlertes)
async def lire_les_alertes(
    page: int = Query(0, ge=0),
    workflow_id: Optional[int] = Query(None),
    user: UserModel = Depends(get_user_with_selected_organization),
) -> PageDAlertes:
    runs, suite = await db_client.runs_avec(
        user.selected_organization_id,
        chemin=donnees.chemin_des_runs_en_alerte(),
        cles=donnees.CLES_LUES_POUR_LES_ALERTES,
        page=page,
        workflow_id=workflow_id,
    )
    return PageDAlertes(lignes=pages.lignes_d_alertes(runs), page=page, a_une_suite=suite)
