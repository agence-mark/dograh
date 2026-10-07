"""[.mark] The after-call on screen (chantier l-agent-travaille, L4, A1 to A10).

Scoped to the user's selected organization; a run is read in THAT organization (another
organization's run, or another agent's than the address says, is a 404).

- ``GET/PUT /organizations/apres-appel``              the settings (theme « After the call »)
- ``POST    /organizations/apres-appel/essai-mail``   a test mail through the mail server
- ``POST    /organizations/apres-appel/nuit``         the night task now (purge, counters)
- ``POST    /organizations/apres-appel/recapitulatif`` the recap mail now
- ``GET     /workflow/{id}/runs/{run}/apres-appel``    the section « After the call » of a run
- ``POST    /workflow/{id}/runs/{run}/apres-appel/{etape}/relancer``  « Retry »
- ``GET     /workflow/{id}/sms`` · ``POST /workflow/{id}/sms/apercu``  the SMS counter and preview (L6)
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError

from api.db import db_client
from api.db.bases_clients.connexion import BaseClientIndisponible
from api.db.models import UserModel
from api.schemas.apres_appel import (
    AdressesNotification,
    ApresAppelDuRun,
    EssaiMail,
    EtapeApresAppel,
    ReglagesApresAppel,
)
from api.services.apres_appel import chaine, mail, sms, taches
from api.services.apres_appel.notification import smtp_de_linstallation
from api.services.apres_appel.reglages import (
    adresses_de_lorganisation,
    adresses_mark,
    ecrire_reglages,
    lire_reglages,
    reglages_de_lagent,
    verifier_les_references,
)
from api.services.auth.depends import get_user_with_selected_organization
from api.services.base_client.rattachement import nom_de_la_base
from api.services.cles_reference import CleIntrouvable

router = APIRouter(prefix="/organizations/apres-appel", tags=["organizations"])
routeur_run = APIRouter(prefix="/workflow", tags=["workflow-apres-appel"])


class EcranApresAppel(BaseModel):
    reglages: ReglagesApresAppel
    adresses: AdressesNotification
    smtp_installation: bool
    base_rattachee: bool
    derniere_nuit: dict | None = None


class ResultatAction(BaseModel):
    statut: str
    detail: dict | None = None


async def _ecran(organization_id: int) -> EcranApresAppel:
    from api.db.bases_clients import apres_appel as sql
    from api.db.bases_clients.connexion import connecter

    nom = await nom_de_la_base(organization_id)
    derniere = None
    if nom:
        try:
            connexion = await connecter(nom)
            try:
                if await sql.a_le_journal_des_taches(connexion):
                    derniere = await sql.derniere_nuit(connexion)
            finally:
                await connexion.close()
        except BaseClientIndisponible:
            pass
    return EcranApresAppel(
        reglages=await lire_reglages(organization_id),
        adresses=AdressesNotification(
            organisation=await adresses_de_lorganisation(organization_id),
            installation=adresses_mark(),
        ),
        smtp_installation=smtp_de_linstallation() is not None,
        base_rattachee=bool(nom),
        derniere_nuit=derniere,
    )


@router.get("", response_model=EcranApresAppel)
async def get_apres_appel(
    user: UserModel = Depends(get_user_with_selected_organization),
):
    return await _ecran(user.selected_organization_id)


@router.put("", response_model=EcranApresAppel)
async def put_apres_appel(
    reglages: ReglagesApresAppel,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    org = user.selected_organization_id
    try:
        await verifier_les_references(org, reglages)
    except CleIntrouvable as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from None
    await ecrire_reglages(org, reglages)
    return await _ecran(org)


@router.post("/essai-mail", response_model=ResultatAction)
async def post_essai_mail(
    demande: EssaiMail,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    org = user.selected_organization_id
    reglages = await lire_reglages(org)
    try:
        identifiant = await mail.envoyer(
            reglages.smtp,
            org,
            [demande.destinataire],
            "Essai du serveur de mail (.mark)",
            "Ce mail d'essai a été envoyé depuis « After the call ». Le serveur de mail fonctionne.",
        )
    except mail.MailImpossible as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from None
    return ResultatAction(statut="envoye", detail={"message_id": identifiant})


@router.post("/nuit", response_model=ResultatAction)
async def post_nuit(user: UserModel = Depends(get_user_with_selected_organization)):
    org = user.selected_organization_id
    nom = await nom_de_la_base(org)
    if not nom:
        raise HTTPException(
            status_code=422,
            detail="No client database is attached to this organization.",
        )
    resultat = await taches.nuit_d_une_base(org, nom)
    if resultat.get("statut") != "faite":
        raise HTTPException(
            status_code=503, detail=resultat.get("erreur") or "Night task failed"
        )
    return ResultatAction(statut="faite", detail=resultat)


@router.post("/recapitulatif", response_model=ResultatAction)
async def post_recapitulatif(
    user: UserModel = Depends(get_user_with_selected_organization),
):
    org = user.selected_organization_id
    nom = await nom_de_la_base(org)
    if not nom:
        raise HTTPException(
            status_code=422,
            detail="No client database is attached to this organization.",
        )
    try:
        resultat = await taches.recapitulatif_d_une_organisation(org, nom, force=True)
    except (mail.MailImpossible, BaseClientIndisponible) as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from None
    if resultat.get("statut") == "sans_destinataire":
        raise HTTPException(
            status_code=422, detail="No default recipient in « Team and routing »."
        )
    return ResultatAction(statut=resultat["statut"], detail=resultat)


# --------------------------------------------------------------------------- #
# The section « After the call » of the run window
# --------------------------------------------------------------------------- #


async def _run_de_lorganisation(workflow_id: int, run_id: int, organization_id: int):
    run = await db_client.get_workflow_run(run_id, organization_id=organization_id)
    if run is None or run.workflow_id != workflow_id:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return run


def _vue(run, bloc: dict) -> ApresAppelDuRun:
    agent = reglages_de_lagent(
        getattr(run.definition, "workflow_configurations", None)
        if run.definition
        else None
    )
    actif = bool(bloc.get("actif"))
    ordre = chaine.etapes_de(agent) if agent.actif else []
    noms = ordre + [n for n in (bloc.get("etapes") or {}) if n not in ordre]
    etapes = []
    for nom in noms:
        brut = (bloc.get("etapes") or {}).get(nom)
        if brut is None:
            continue
        try:
            etapes.append(
                EtapeApresAppel(
                    nom=nom,
                    statut=brut.get("statut") or "en_attente",
                    tentatives=int(brut.get("tentatives") or 0),
                    definitive=bool(brut.get("definitive")),
                    detail=brut.get("detail"),
                    le=datetime.fromisoformat(brut["le"]) if brut.get("le") else None,
                    envois=list(brut.get("envois") or []),
                )
            )
        except (ValidationError, ValueError, TypeError):
            continue
    return ApresAppelDuRun(
        actif=actif,
        essai=bool(bloc.get("essai")),
        etapes=etapes,
        appel_id=bloc.get("appel_id"),
        demande_id=bloc.get("demande_id"),
        synthese=bloc.get("synthese"),
        autre_demande_ouverte_id=bloc.get("autre_demande_ouverte_id"),
    )


@routeur_run.get(
    "/{workflow_id}/runs/{run_id}/apres-appel", response_model=ApresAppelDuRun
)
async def get_apres_appel_du_run(
    workflow_id: int,
    run_id: int,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    run = await _run_de_lorganisation(
        workflow_id, run_id, user.selected_organization_id
    )
    return _vue(run, await db_client.lire_apres_appel(run_id))


@routeur_run.post(
    "/{workflow_id}/runs/{run_id}/apres-appel/{etape}/relancer",
    response_model=ApresAppelDuRun,
)
async def post_relancer_etape(
    workflow_id: int,
    run_id: int,
    etape: str,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    run = await _run_de_lorganisation(
        workflow_id, run_id, user.selected_organization_id
    )
    bloc = await db_client.lire_apres_appel(run_id)
    statut = ((bloc.get("etapes") or {}).get(etape) or {}).get("statut")
    if statut is None:
        raise HTTPException(status_code=404, detail="No such step on this run")
    if statut not in ("echec", "ignoree"):
        raise HTTPException(
            status_code=409, detail="Only a failed or skipped step can be retried"
        )
    await chaine.relancer(run_id, etape)
    return _vue(run, await db_client.lire_apres_appel(run_id))


# --------------------------------------------------------------------------- #
# The SMS of an agent (L6): the counter (D9) and the preview filled by a real call
# --------------------------------------------------------------------------- #


class CompteurSms(BaseModel):
    envoyes: int


class DemandeApercuSms(BaseModel):
    texte: str = Field(max_length=480)


class ApercuSms(BaseModel):
    texte: str
    longueur: int
    coupe: bool
    parties: int
    encodage: str
    run_id: int | None = None


async def _agent_de_lorganisation(workflow_id: int, organization_id: int):
    workflow = await db_client.get_workflow(
        workflow_id, organization_id=organization_id
    )
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@routeur_run.get("/{workflow_id}/sms", response_model=CompteurSms)
async def get_compteur_sms(
    workflow_id: int,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    await _agent_de_lorganisation(workflow_id, user.selected_organization_id)
    return CompteurSms(envoyes=await db_client.compter_sms(workflow_id))


@routeur_run.post("/{workflow_id}/sms/apercu", response_model=ApercuSms)
async def post_apercu_sms(
    workflow_id: int,
    demande: DemandeApercuSms,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    await _agent_de_lorganisation(workflow_id, user.selected_organization_id)
    run_id, fiche = await db_client.derniere_fiche(workflow_id)
    texte, coupe = sms.remplir(demande.texte, fiche)
    nombre, encodage = sms.parties(texte)
    return ApercuSms(
        texte=texte,
        longueur=len(texte),
        coupe=coupe,
        parties=nombre,
        encodage=encodage,
        run_id=run_id,
    )
