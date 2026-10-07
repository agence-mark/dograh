"""[.mark] The connectors on screen (plan connecteurs-agent, step 2; l-agent-travaille L5).

All scoped to the signed-in user's organization (D6): the catalogue, this organization's
connections and their state, and the authorization link to send the client. Nothing in a
request names another organization. l-agent-collegue (L4): the hub's translators and the one
the organization books in (« Integrations »).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.db.models import UserModel
from api.schemas.traducteurs import ChoixTraducteurs, TraducteurVue
from api.services.auth.depends import get_user_with_selected_organization
from api.services.integrations.connectors import nango
from api.services.integrations.connectors.catalogue import connecteur, connecteurs

router = APIRouter(prefix="/connecteurs", tags=["connecteurs"])


class ParametreVue(BaseModel):
    nom: str
    type: str
    description: str
    obligatoire: bool
    choix: list[str] = []
    liste_du_contexte: str | None = None


class ActionVue(BaseModel):
    nom: str
    description: str
    ecrit: bool
    anticipable_permis: bool
    parametres: list[ParametreVue]
    reglages_par_defaut: dict


class ConnecteurVue(BaseModel):
    nom: str
    libelle: str
    integration: str
    actions: list[ActionVue]
    interne: bool = False


class ConnexionVue(BaseModel):
    connecteur: str | None = None
    integration: str
    connection_id: str
    creee_le: str | None = None
    erreurs: int = 0


class EtatConnexions(BaseModel):
    nango_configure: bool
    connexions: list[ConnexionVue] = Field(default_factory=list)
    erreur: str | None = None


class DemandeLien(BaseModel):
    connecteurs: list[str] = Field(min_length=1, max_length=10)


class Lien(BaseModel):
    lien: str | None
    expire_le: str | None = None


@router.get("/catalogue", response_model=list[ConnecteurVue])
async def get_catalogue(user: UserModel = Depends(get_user_with_selected_organization)):
    return [
        ConnecteurVue(
            nom=c.nom,
            libelle=c.libelle,
            integration=c.integration,
            interne=c.interne,
            actions=[
                ActionVue(
                    nom=a.nom,
                    description=a.description,
                    ecrit=a.ecrit,
                    anticipable_permis=a.anticipable_permis,
                    parametres=[
                        ParametreVue(**{**p.__dict__, "choix": list(p.choix)})
                        for p in a.parametres
                    ],
                    reglages_par_defaut=a.reglages_par_defaut,
                )
                for a in c.actions
            ],
        )
        for c in connecteurs()
    ]


@router.get("/connexions", response_model=EtatConnexions)
async def get_connexions(
    user: UserModel = Depends(get_user_with_selected_organization),
):
    if not nango.nango_configure():
        return EtatConnexions(nango_configure=False)
    par_integration = {c.integration: c.nom for c in connecteurs()}
    try:
        liste = await nango.connexions(user.selected_organization_id)
    except nango.NangoIndisponible as erreur:
        return EtatConnexions(nango_configure=True, erreur=str(erreur))
    return EtatConnexions(
        nango_configure=True,
        connexions=[
            ConnexionVue(
                connecteur=par_integration.get(c.integration),
                integration=c.integration,
                connection_id=c.connection_id,
                creee_le=c.creee_le,
                erreurs=c.erreurs,
            )
            for c in liste
        ],
    )


@router.post("/lien", response_model=Lien)
async def post_lien(
    demande: DemandeLien, user: UserModel = Depends(get_user_with_selected_organization)
):
    from api.services.hub.traducteurs import traducteur

    integrations = []
    for nom in demande.connecteurs:
        c = connecteur(nom)
        if c is None:
            # l-agent-collegue (L4): a translator of the hub with no action of its own (Outlook)
            # is connected the same way, by its software's integration.
            t = traducteur(nom)
            if t is None:
                raise HTTPException(status_code=422, detail=f"Unknown connector « {nom} ».")
            if t.integration not in integrations:
                integrations.append(t.integration)
            continue
        if c.interne:
            raise HTTPException(
                status_code=422,
                detail=f"« {c.libelle} » is internal: there is nothing to connect.",
            )
        if c.integration not in integrations:
            integrations.append(c.integration)
    try:
        return Lien(
            **await nango.lien_d_autorisation(
                user.selected_organization_id, integrations
            )
        )
    except nango.NangoIndisponible as erreur:
        raise HTTPException(status_code=503, detail=str(erreur)) from None


# --------------------------------------------------------------------------- #
# l-agent-collegue, L4 (H2, H8): the hub's translators, and the one this organization uses
# --------------------------------------------------------------------------- #


@router.get("/traducteurs", response_model=list[TraducteurVue])
async def get_traducteurs(
    user: UserModel = Depends(get_user_with_selected_organization),
):
    from api.services.hub.traducteurs import traducteurs

    return [
        TraducteurVue(
            systeme=t.systeme,
            libelle=t.libelle,
            domaine=t.domaine,
            integration=t.integration,
            reference_agenda=t.reference_agenda,
            operations={o.objet: list(o.operations) for o in t.objets},
        )
        for t in traducteurs()
    ]


@router.get("/traducteurs/choix", response_model=ChoixTraducteurs)
async def get_choix_traducteurs(
    user: UserModel = Depends(get_user_with_selected_organization),
):
    from api.services.hub.choix import lire_choix

    return await lire_choix(user.selected_organization_id)


@router.put("/traducteurs/choix", response_model=ChoixTraducteurs)
async def put_choix_traducteurs(
    choix: ChoixTraducteurs,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    from api.services.hub.choix import ecrire_choix
    from api.services.hub.traducteurs import traducteur

    if choix.agenda is not None:
        t = traducteur(choix.agenda)
        if t is None or t.domaine != "agenda":
            raise HTTPException(
                status_code=422,
                detail=f"« {choix.agenda} » is not a calendar software of the hub.",
            )
    return await ecrire_choix(user.selected_organization_id, choix)
