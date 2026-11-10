"""[.mark] builder partie 2, U4 : la préparation d'un agent et l'origine de ses réglages (lecture seule, rien de stocké).

* ``GET /workflow/{id}/preparation``      la liste de préparation calculée (``services/preparation``) ;
* ``GET /workflow/{id}/heritage-reglages`` pour chaque réglage : valeur effective et origine (``services/heritage_reglages``) ;
* ``GET|PUT /workflow/{id}/juge-vrais-appels`` (U6, J3) : « juge des vrais appels » de cet agent (``services/juge/file``), éteint par défaut.

Toute lecture est bornée à l'organisation de l'appelant : l'agent d'une autre organisation répond 404.
"""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.services import heritage_reglages
from api.services.preparation import liste as liste_pret
from api.services.juge import file as file_du_juge
from api.services.auth.depends import get_user
from api.services.modeles_reglages.service import ModeleRefuse

router = APIRouter(prefix="/workflow")


class EtapeDePreparation(BaseModel):
    id: str
    niveau: str
    etat: str
    theme: str
    source: str
    manquants: list[str] = []
    # [.mark] Clôture, SA-3 : le code et les paramètres de chaque manquant (même ordre), que l'écran traduit par identifiant.
    manquants_details: list[dict[str, Any]] = []
    # [.mark] Partie 3, SA-L3a : « Prêt à publier ». Où régler (étape, onglet), le contrôle qui garde la ligne et sa position, les
    # corrections en un clic, et le cas « sans effet » qu'elle dit.
    noeud_id: str | None = None
    controle: str | None = None
    position: str | None = None
    corrections: list[dict[str, Any]] = []
    constat: str | None = None
    liaison_id: str | None = None
    noms: list[str] = []
    onglet: str | None = None


class PreparationResponse(BaseModel):
    etapes: list[EtapeDePreparation]


class ReglageHerite(BaseModel):
    origine: str
    valeur: Any = None
    valeur_heritee: Any = None
    propre: bool
    modifiable: bool
    masquee: bool


class HeritageReglagesResponse(BaseModel):
    reglages: dict[str, ReglageHerite]


@router.get("/{workflow_id}/preparation")
async def lire_la_preparation(workflow_id: int, user: UserModel = Depends(get_user)) -> PreparationResponse:
    # [.mark] Partie 3 (SA-L3a) : la même liste « Prêt à publier » que la fenêtre Publier et le builder.
    try:
        lignes = await liste_pret.lire_la_liste(user.selected_organization_id, workflow_id)
    except ModeleRefuse as erreur:
        raise HTTPException(status_code=erreur.statut, detail=erreur.message) from None
    return PreparationResponse(etapes=[EtapeDePreparation(**ligne) for ligne in lignes])


@router.get("/{workflow_id}/heritage-reglages")
async def lire_l_heritage_des_reglages(workflow_id: int, user: UserModel = Depends(get_user)) -> HeritageReglagesResponse:
    try:
        reglages = await heritage_reglages.lire(user.selected_organization_id, workflow_id)
    except ModeleRefuse as erreur:
        raise HTTPException(status_code=erreur.statut, detail=erreur.message) from None
    return HeritageReglagesResponse(reglages={c: ReglageHerite(**v) for c, v in reglages.items()})


class JugeDesVraisAppels(BaseModel):
    """Le réglage par agent. En écriture, un filtre absent (``None``) reste comme il était ; en lecture, les valeurs effectives
    et ``etat_du_juge`` (``regle`` | ``eteint`` | ``sans_cle``) : le juge du Labo est-il prêt à juger ?"""

    actif: bool = False
    part: int | None = Field(default=None, ge=1, le=100, description="Share of the real calls judged, 1 to 100 %.")
    duree_min_s: int | None = Field(default=None, ge=0, le=600, description="Calls shorter than this are not judged (0 = no minimum).")
    repondeurs_exclus: bool | None = Field(default=None, description="Calls that ended on an answering machine are not judged.")
    vecu_eteints: list[Literal["frustration", "blanc", "gene_machine", "ecoute", "boucle"]] | None = Field(
        default=None,
        max_length=5,
        description="The caller-experience criteria this judge does NOT look at (none: all five are judged). Absent on write: unchanged.",
    )
    etat_du_juge: str | None = None


async def _agent_de_l_organisation(workflow_id: int, user: UserModel) -> None:
    if await db_client.get_workflow(workflow_id, organization_id=user.selected_organization_id) is None:
        raise HTTPException(status_code=404, detail="Agent not found")


async def _vue_du_juge(organisation: int, workflow_id: int) -> JugeDesVraisAppels:
    from api.services.juge import etat

    return JugeDesVraisAppels(**await file_du_juge.lire_reglages(organisation, workflow_id), etat_du_juge=await etat.etat_du_juge(organisation))


@router.get("/{workflow_id}/juge-vrais-appels")
async def lire_le_juge_des_vrais_appels(workflow_id: int, user: UserModel = Depends(get_user)) -> JugeDesVraisAppels:
    await _agent_de_l_organisation(workflow_id, user)
    return await _vue_du_juge(user.selected_organization_id, workflow_id)


@router.put("/{workflow_id}/juge-vrais-appels")
async def regler_le_juge_des_vrais_appels(
    workflow_id: int, requete: JugeDesVraisAppels, user: UserModel = Depends(get_user)
) -> JugeDesVraisAppels:
    await _agent_de_l_organisation(workflow_id, user)
    await file_du_juge.regler(
        user.selected_organization_id,
        workflow_id,
        requete.actif,
        part=requete.part,
        duree_min_s=requete.duree_min_s,
        repondeurs_exclus=requete.repondeurs_exclus,
        vecu_eteints=requete.vecu_eteints,
    )
    return await _vue_du_juge(user.selected_organization_id, workflow_id)
