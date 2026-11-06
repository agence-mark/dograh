"""[.mark] Ce que le portail du client lit et écrit du Hub « Relation clients » (U3 septies, E78).

Réservé à une CLÉ D'API (le portail, avec la clé de ce client) : une session reçoit 403. Tout se fait dans
l'organisation de la clé ; la clé d'une autre organisation ne voit rien. Une note interne n'est JAMAIS rendue, les notes
sur un client et les témoignages n'ont pas de route ici.

* ``/organizations/relation/fils`` : les fils, demandes de logiciel et signalements d'appel du client (paginés, « les miens »), l'envoi
  d'un message, d'une demande ou d'un signalement (qui crée, dans le même geste, un problème « À améliorer » relevé par le client) ;
* ``/organizations/relation/entree/verifier`` : le portail présente le lien d'entrée de .mark ; il est consommé (une
  seule fois, une minute, ce client seulement) et le portail ouvre avec le rôle .mark.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from loguru import logger

from api.services.auth.depends import get_user_with_selected_organization
from api.services.boucle import ingestion
from api.services.relation import hub

router = APIRouter(prefix="/organizations/relation", tags=["relation"])


async def portail(
    user: UserModel = Depends(get_user_with_selected_organization),
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> UserModel:
    if not hub.est_une_cle_d_api(x_api_key):
        raise HTTPException(status_code=403, detail="Reserved to the client portal (API key)")
    return user


def _auteur(user: UserModel) -> str:
    texte = (getattr(user, "mark_auteur", None) or "portail : client")
    return texte.removeprefix("portail :").strip() or "client"


class MessagePortail(BaseModel):
    id: int
    cote: Literal["client", "mark"]
    auteur: str
    texte: str
    cree_le: datetime


class FilPortail(BaseModel):
    id: int
    sorte: str
    sujet: str
    etat: str
    logiciel: str | None
    catalogue: str | None
    etat_demande: str | None
    # Signalement : l'appel signalé (``None`` pour les autres sortes ou si l'appel a été supprimé) ; ``ouvert_par`` : « portail : prénom nom ».
    run_id: int | None = None
    ouvert_par: str | None = None
    cree_le: datetime
    modifie_le: datetime
    dernier: MessagePortail | None = None
    messages: list[MessagePortail] | None = None


class FilIn(BaseModel):
    sorte: Literal["message", "demande_logiciel", "signalement"] = "message"
    sujet: str = Field(min_length=1, max_length=200)
    # Un signalement nomme l'appel (de CE client : un autre appel est un 404) ; refusé pour les autres sortes.
    run_id: int | None = Field(default=None, ge=1)
    texte: str = Field(min_length=1, max_length=8000)
    logiciel: str | None = Field(default=None, max_length=120)
    catalogue: str | None = Field(default=None, max_length=120)


class MessageIn(BaseModel):
    texte: str = Field(min_length=1, max_length=8000)


class VerifierIn(BaseModel):
    # Le jeton seul, ou le lien « <client>.<jeton> » tel que le portail le reçoit dans ``?lien=``.
    jeton: str = Field(min_length=10, max_length=240)


class EntreeVerifiee(BaseModel):
    entree_id: int
    auteur: str
    motif: str | None
    # L'adresse du membre de .mark qui entre (compte de l'équipe), pour que le portail nomme la personne ; ``None`` si le compte n'existe plus.
    adresse: str | None = None


_CHAMPS_FIL = (
    "id", "sorte", "sujet", "etat", "logiciel", "catalogue", "etat_demande", "run_id", "ouvert_par", "cree_le", "modifie_le",
)


def _sortie(fil: dict) -> FilPortail:
    """Une liste blanche de champs : ni l'organisation, ni le suivi, ni la lecture interne ne sortent."""
    return FilPortail(
        **{k: fil[k] for k in _CHAMPS_FIL},
        dernier=MessagePortail(**fil["dernier"]) if fil.get("dernier") else None,
        messages=[MessagePortail(**m) for m in fil["messages"]] if "messages" in fil else None,
    )


LIMITE_PAR_DEFAUT = 50
LIMITE_MAX = 100


@router.get("/fils", response_model=list[FilPortail])
async def mes_fils(
    reponse: Response,
    page: int = Query(0, ge=0, description="Page à partir de 0"),
    limit: int = Query(LIMITE_PAR_DEFAUT, ge=1, le=LIMITE_MAX),
    miens: bool = Query(False, description="Seulement les fils ouverts par l'auteur de la requête (en-tête X-Mark-Auteur)"),
    user: UserModel = Depends(portail),
) -> list[FilPortail]:
    """Les fils du client, le plus récent d'abord, paginés (``page`` et ``limit``) ; le total est dans l'en-tête ``X-Total-Count``.
    ``miens`` ne rend que ceux que l'auteur de la requête a ouverts : il faut alors ``X-Mark-Auteur`` (422 sinon, jamais « tous » en silence)."""
    auteur = getattr(user, "mark_auteur", None)
    if miens and not auteur:
        raise HTTPException(status_code=422, detail="« miens » needs the X-Mark-Auteur header")
    ouvert_par = auteur if miens else None
    organisation = user.selected_organization_id
    fils = await db_client.lister_fils_relation(
        [organisation], limite=limit, decalage=page * limit, ouvert_par=ouvert_par, avec_internes=False
    )
    reponse.headers["X-Total-Count"] = str(await db_client.compter_les_fils_d_une_organisation(organisation, ouvert_par=ouvert_par))
    return [_sortie(f) for f in fils]


@router.get("/fils/{fil_id}", response_model=FilPortail)
async def mon_fil(fil_id: int, user: UserModel = Depends(portail)) -> FilPortail:
    fil = await db_client.lire_fil_relation(user.selected_organization_id, fil_id, avec_internes=False)
    if fil is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return _sortie(fil)


@router.post("/fils", response_model=FilPortail, status_code=201)
async def ecrire_a_mark(corps: FilIn, user: UserModel = Depends(portail)) -> FilPortail:
    """« Écrire à .mark » ou « Demander un logiciel » : un nouveau fil dans l'organisation de la clé."""
    organisation = user.selected_organization_id
    if corps.sorte == "demande_logiciel" and not (corps.logiciel or "").strip():
        raise HTTPException(status_code=422, detail="A software request names the software")
    if corps.sorte == "signalement" and corps.run_id is None:
        raise HTTPException(status_code=422, detail="A report names the call")
    if corps.sorte != "signalement" and corps.run_id is not None:
        raise HTTPException(status_code=422, detail="Only a report is tied to a call")
    run = None
    if corps.sorte == "signalement":
        # L'appel est relu AVEC l'organisation de la clé : l'appel d'un autre client est un 404, comme un appel qui n'existe pas.
        run = await db_client.get_workflow_run(corps.run_id, organization_id=organisation)
        if run is None:
            raise HTTPException(status_code=404, detail="Call not found")
    fil = await db_client.creer_fil_relation(
        organisation,
        sorte=corps.sorte,
        sujet=corps.sujet.strip(),
        auteur=_auteur(user),
        texte=corps.texte.strip(),
        logiciel=(corps.logiciel or "").strip() or None,
        catalogue=(corps.catalogue or "").strip() or None,
        run_id=corps.run_id,
        ouvert_par=getattr(user, "mark_auteur", None),
    )
    if run is not None:
        # Le même geste : le signalement entre dans « À améliorer », relevé par le client. Le message du client est déjà écrit : une panne de
        # la boucle se consigne et ne le fait pas perdre (le fil reste, sans problème lié).
        try:
            probleme = await ingestion.ingerer_un_signalement_du_client(
                organisation, run.workflow_id, run.id, corps.sujet.strip(), corps.texte.strip()
            )
            await db_client.modifier_fil_relation(organisation, fil["id"], {"amelioration_id": probleme["id"]})
        except Exception:  # noqa: BLE001
            logger.exception("A client report was written but its improvement could not be created")
    complet = await db_client.lire_fil_relation(organisation, fil["id"], avec_internes=False)
    return _sortie(complet)


@router.post("/fils/{fil_id}/messages", response_model=MessagePortail, status_code=201)
async def repondre_a_mark(fil_id: int, corps: MessageIn, user: UserModel = Depends(portail)) -> MessagePortail:
    message = await db_client.ajouter_message_relation(
        user.selected_organization_id, fil_id, cote="client", auteur=_auteur(user), texte=corps.texte.strip()
    )
    if message is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return MessagePortail(**message)


@router.post("/entree/verifier", response_model=EntreeVerifiee)
async def verifier_entree(corps: VerifierIn, user: UserModel = Depends(portail)) -> EntreeVerifiee:
    """Le lien d'entrée de .mark : valable une minute, une seule fois, pour CE client seulement.

    Inconnu, rejoué, expiré ou d'un autre client : la même réponse 403, sans dire lequel.
    """
    jeton = hub.jeton_du_lien(user.selected_organization_id, corps.jeton)
    entree = await hub.consommer_lien(user.selected_organization_id, jeton) if jeton else None
    if entree is None:
        raise HTTPException(status_code=403, detail="Invalid or expired entry link")
    membre = await db_client.get_user_by_id(entree["user_id"]) if entree.get("user_id") else None
    return EntreeVerifiee(entree_id=entree["id"], auteur=entree["auteur"], motif=entree["motif"], adresse=getattr(membre, "email", None))


class EntreeTerminee(BaseModel):
    duree_secondes: int


@router.post("/entree/{entree_id}/fin", response_model=EntreeTerminee)
async def terminer_entree(entree_id: int, user: UserModel = Depends(portail)) -> EntreeTerminee:
    """V4 : le portail dit que la personne de .mark est sortie. Une seule fois, pour CE client seulement : la durée de la visite
    (``fin - entrée``) se lit ensuite dans le Hub. Inconnue, d'un autre client, jamais entrée ou déjà terminée : 404, sans dire laquelle."""
    fin = await db_client.terminer_entree_relation(user.selected_organization_id, entree_id, datetime.now(UTC))
    if fin is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    return EntreeTerminee(duree_secondes=fin["duree_secondes"])
