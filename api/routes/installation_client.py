"""[.mark] Partie 3, sous-lot 9 (SE-5, § 5 du plan) : « Nouveau client » qui installe vraiment.

- ``POST /installations-client``                              crée le client (organisation, nom) et son installation (étape 1) ;
- ``GET  /installations-client/ouvertes``                     les installations ouvertes des clients que le rôle ouvre (« Reprendre ») ;
- ``GET  /installations-client/courante``                     l'installation ouverte du client de l'adresse ;
- ``POST /installations-client/courante/etapes/{n}``          exécute l'étape n (sautée si faite ; confirmation si elle dépense) ;
- ``POST /installations-client/courante/etapes/{n}/passer``   laisse de côté une étape passable.

Permission ``clients.creer`` (registre), jamais par une clé d'API. Le client est celui de l'ADRESSE (en-tête contrôlé par
``get_user``), jamais un identifiant du corps. Un refus rend ``{code, fr, en}`` (une phrase, jamais un texte interne).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from pydantic import BaseModel, ConfigDict, Field

from api.db.models import UserModel
from api.services.auth.depends import get_user, get_user_with_selected_organization
from api.services.installation_client import moteur
from api.services.installation_client.executants import identifiant as identifiant_de

router = APIRouter(prefix="/installations-client", tags=["installations-client"])


class PhraseInstallation(BaseModel):
    fr: str
    en: str


class EtapeVue(BaseModel):
    numero: int
    cle: str
    titre: PhraseInstallation
    passable: bool
    depense: bool
    etat: Literal["a_faire", "en_cours", "faite", "erreur", "passee"]
    le: datetime | None = None
    par: int | None = None
    erreur: PhraseInstallation | None = None
    code_erreur: str | None = None
    resultat: dict[str, Any] = Field(default_factory=dict)


class EstimationInstallation(BaseModel):
    scenarios: int
    montant: float | None = None
    plafond: float | None = None
    devise: str = "USD"


class AgentDuClient(BaseModel):
    id: int
    nom: str


class InstallationVue(BaseModel):
    id: int
    organization_id: int
    nom: str
    etat: Literal["ouverte", "terminee", "abandonnee"]
    cree_le: datetime
    etapes: list[EtapeVue]
    prochaine: int | None = None
    estimation: EstimationInstallation | None = None
    agents_du_client: list[AgentDuClient] | None = None


class EchecInstallation(BaseModel):
    code: str
    fr: str
    en: str


class ResultatEtape(BaseModel):
    installation: InstallationVue
    sautee: bool
    echec: EchecInstallation | None = None
    # Rendu une seule fois (étape 7 : la fiche du portail, avec la clé et le mot de passe), jamais rangé.
    montre: dict[str, Any] | None = None


class InstallationResume(BaseModel):
    id: int
    organization_id: int
    nom: str
    cree_le: datetime
    prochaine: int | None = None
    faites: int
    erreur: bool


class DemandeDemarrer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nom: str = Field(min_length=1, max_length=100, description="Company name, as shown everywhere.")
    identifiant: str | None = Field(
        default=None,
        min_length=3,
        max_length=60,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
        description="Stable identifier of the organization; derived from the name when omitted.",
    )


class EtablissementDemande(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nom: str = Field(min_length=1, max_length=100)
    horaires_ouverture: str | None = Field(default=None, max_length=500)


class PersonneDemande(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prenom: str = Field(min_length=1, max_length=100)
    nom: str | None = Field(default=None, max_length=100)
    role: str | None = Field(default=None, max_length=100)
    mail: str | None = Field(default=None, max_length=200)


class SujetDemande(BaseModel):
    model_config = ConfigDict(extra="forbid")
    libelle: str = Field(min_length=1, max_length=100)
    destinataires: list[int] = Field(default_factory=list, max_length=50, description="Indexes in ``personnes``.")


class PropositionDemande(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connecteur: str = Field(min_length=1, max_length=60)
    compte: str | None = Field(default=None, max_length=60)
    message: str | None = Field(default=None, max_length=500)


class DonneesEtape(BaseModel):
    """Ce que chaque étape reçoit de la fenêtre (les champs d'une autre étape sont ignorés)."""

    model_config = ConfigDict(extra="forbid")
    mode: Literal["creer", "rattacher"] | None = None
    nom_base: str | None = Field(default=None, max_length=63)
    etablissements: list[EtablissementDemande] | None = Field(default=None, max_length=20)
    personnes: list[PersonneDemande] | None = Field(default=None, max_length=50)
    sujets: list[SujetDemande] | None = Field(default=None, max_length=50)
    propositions: list[PropositionDemande] | None = Field(default=None, max_length=30)
    workflow_id: int | None = Field(default=None, ge=1)
    scenario_ids: list[str] | None = Field(default=None, max_length=50)


class DemandeEtape(BaseModel):
    model_config = ConfigDict(extra="forbid")
    donnees: DonneesEtape = Field(default_factory=DonneesEtape)
    confirmer: bool = Field(default=False, description="Required for a step that spends money (the estimated amount was shown).")


def _http(refus: moteur.RefusInstallation) -> HTTPException:
    return HTTPException(status_code=refus.statut, detail=refus.detail())


@router.post("", response_model=InstallationVue, status_code=201)
async def demarrer_une_installation(corps: DemandeDemarrer, user: UserModel = Depends(get_user)):
    ident = corps.identifiant or f"client-{identifiant_de(corps.nom, '-', 50)}"
    try:
        return await moteur.demarrer(user, corps.nom.strip(), ident)
    except moteur.RefusInstallation as refus:
        raise _http(refus) from None


@router.get("/ouvertes", response_model=list[InstallationResume])
async def installations_ouvertes(user: UserModel = Depends(get_user)):
    return await moteur.ouvertes(user)


@router.get("/courante", response_model=InstallationVue)
async def installation_courante(user: UserModel = Depends(get_user_with_selected_organization)):
    try:
        return await moteur.lire(user.selected_organization_id)
    except moteur.RefusInstallation as refus:
        raise _http(refus) from None


@router.post("/courante/etapes/{numero}", response_model=ResultatEtape)
async def executer_une_etape(
    response: Response,
    corps: DemandeEtape,
    numero: int = Path(ge=1, le=9),
    user: UserModel = Depends(get_user_with_selected_organization),
):
    # L'étape 7 rend une clé et un mot de passe une seule fois : la réponse n'est gardée nulle part.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    try:
        return await moteur.executer(
            user, user.selected_organization_id, numero, corps.donnees.model_dump(exclude_none=True), confirmer=corps.confirmer
        )
    except moteur.RefusInstallation as refus:
        raise _http(refus) from None


@router.post("/courante/etapes/{numero}/passer", response_model=InstallationVue)
async def passer_une_etape(numero: int = Path(ge=1, le=9), user: UserModel = Depends(get_user_with_selected_organization)):
    try:
        return await moteur.passer(user, user.selected_organization_id, numero)
    except moteur.RefusInstallation as refus:
        raise _http(refus) from None
