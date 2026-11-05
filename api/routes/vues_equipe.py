"""[.mark] Les vues « tous clients » de l'équipe (builder partie 3, sous-lot 10 ; SE-3, E-3).

Une route d'équipe .mark, **en lecture seule**, qui montre d'un coup ce que le rôle du compte ouvre (le Labo, tous les clients, ou
des clients choisis) : « À améliorer », Qualité, les compteurs du Labo, la colonne Client de Conversations, le Chat du Labo.

* ``GET /vues-equipe/ameliorations``   les problèmes d'un état, tous clients, avec le client de chacun ;
* ``GET /vues-equipe/qualite``         les indicateurs par client et par agent (7 ou 30 jours) ;
* ``GET /vues-equipe/compteurs``       une ligne par client (agents, appels, note, signalements) et les totaux ;
* ``GET /vues-equipe/conversations``   les appels de tous les clients ouverts (même fonction que ``/espaces/conversations``) ;
* ``GET /vues-equipe/chat``            les conversations du builder de tous les clients ouverts.

⛔ Droits vérifiés à CHAQUE requête, jamais par une clé d'API (403, quelle que soit son organisation) ni par un compte sans rôle d'équipe
(403). La liste des organisations est celle que le rôle ouvre (``espaces.lister_espaces``) : un rôle à « clients choisis » ne voit que les
siens, et une organisation qu'il n'ouvre pas est un 404, comme si elle n'existait pas. Le filtre par organisation est DANS chaque requête
(``organization_id IN (…)``), les listes sont paginées, aucune requête n'est faite par client. Aucune route n'écrit.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from api.db import db_client
from api.db.models import UserModel
from api.routes.ameliorations import VueDeLigne
from api.routes.espaces import ConversationsEquipeResponse, conversations_de_l_equipe
from api.services.auth.depends import get_user
from api.services.boucle import qualite, vues
from api.services.equipe_mark import espaces
from api.services.equipe_mark.acces import acces_de, est_par_cle_api

router = APIRouter(prefix="/vues-equipe", tags=["vues-equipe"])

PAR_PAGE = 50


async def equipe(
    user: UserModel = Depends(get_user),
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> UserModel:
    """403 pour une clé d'API (le portail, un script) ou pour un compte sans rôle d'équipe, à chaque requête."""
    if x_api_key or est_par_cle_api(user):
        raise HTTPException(status_code=403, detail="The team views are not open to an API key")
    if await acces_de(user) is None:
        raise HTTPException(status_code=403, detail="Reserved to the .mark team")
    return user


async def _portee(user: UserModel, organization_id: int | None) -> dict[int, str]:
    """Les organisations que la requête peut lire : id -> nom affiché. Une organisation que le rôle n'ouvre pas : 404."""
    ouvertes = {e["id"]: e["nom"] for e in await espaces.lister_espaces(user)}
    if organization_id is None:
        return ouvertes
    if organization_id not in ouvertes:
        raise HTTPException(status_code=404, detail="Space not found")
    return {organization_id: ouvertes[organization_id]}


# ---------------------------------------------------------------------- À améliorer
class LigneAmeliorationEquipe(VueDeLigne):
    organization_id: int
    organization_nom: str


class PageAmeliorationsEquipe(BaseModel):
    lignes: list[LigneAmeliorationEquipe]
    page: int
    a_une_suite: bool
    compteurs: dict[str, int]


@router.get("/ameliorations", response_model=PageAmeliorationsEquipe)
async def ameliorations_de_tous_les_clients(
    etat: Literal["a_trier", "en_cours", "testee", "publiee"] = Query("a_trier"),
    organization_id: int | None = Query(None, description="Un seul client (sinon tous ceux que le rôle ouvre)"),
    page: int = Query(0, ge=0),
    user: UserModel = Depends(equipe),
) -> dict[str, Any]:
    portee = await _portee(user, organization_id)
    ids = list(portee)
    lignes, suite = await db_client.lister_ameliorations_des_organisations(ids, etat=etat, page=page, par_page=PAR_PAGE)
    if lignes:
        workflows = sorted({p["workflow_id"] for p in lignes})
        noms, juges, tous = await asyncio.gather(
            db_client.noms_des_agents_des_organisations(ids, workflows),
            db_client.appels_des_agents_des_organisations(ids, jours=vues.JOURS_DE_FREQUENCE, juges_seulement=True),
            db_client.appels_des_agents_des_organisations(ids, jours=vues.JOURS_DE_FREQUENCE),
        )
    else:
        noms, juges, tous = {}, {}, {}
    compteurs = await db_client.compter_ameliorations_des_organisations(ids)
    return {
        "lignes": [
            {
                **vues.vue_en_liste(p, noms.get(p["workflow_id"], ""), vues.frequence(p, juges, tous)),
                "organization_id": p["organization_id"],
                "organization_nom": portee.get(p["organization_id"], ""),
            }
            for p in lignes
        ],
        "page": page,
        "a_une_suite": suite,
        "compteurs": {e: compteurs.get(e, 0) for e in vues.ETATS_DE_L_ECRAN},
    }


# ---------------------------------------------------------------------- Qualité
class QualiteParClient(BaseModel):
    organization_id: int
    organization_nom: str
    appels: int
    juges: int
    note: float | None
    part_issue: float | None
    part_transferts: float | None
    part_raccroches: float | None
    reponse_mediane: float | None


class QualiteParAgent(QualiteParClient):
    workflow_id: int
    workflow_nom: str
    version: int | None


class QualiteEquipe(BaseModel):
    jours: int
    # Les chiffres de tous les clients ouverts, avec les mêmes clés que la page Qualité d'un client.
    mondial: dict[str, Any]
    motifs: list[dict[str, Any]]
    par_client: list[QualiteParClient]
    agents: list[QualiteParAgent]
    total_agents: int
    limit: int
    offset: int


def _chiffres(resume: dict[str, Any]) -> dict[str, Any]:
    cles = ("appels", "juges", "note", "part_issue", "part_transferts", "part_raccroches", "reponse_mediane")
    return {k: resume.get(k) for k in cles}


@router.get("/qualite", response_model=QualiteEquipe)
async def qualite_de_tous_les_clients(
    jours: int = Query(7),
    organization_id: int | None = Query(None),
    limit: int = Query(PAR_PAGE, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: UserModel = Depends(equipe),
) -> dict[str, Any]:
    if jours not in (7, 30):
        raise HTTPException(status_code=422, detail="jours doit valoir 7 ou 30")
    portee = await _portee(user, organization_id)
    lignes = await db_client.runs_pour_la_qualite_des_organisations(list(portee), jours=jours)
    par_client: dict[int, list[dict[str, Any]]] = {}
    par_agent: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for ligne in lignes:
        par_client.setdefault(ligne["organization_id"], []).append(ligne)
        par_agent.setdefault((ligne["organization_id"], ligne["workflow_id"]), []).append(ligne)
    clients = [
        {"organization_id": org, "organization_nom": portee.get(org, ""), **_chiffres(qualite._resume(appels))}
        for org, appels in par_client.items()
    ]
    clients.sort(key=lambda c: (-c["appels"], c["organization_nom"].lower()))
    agents = []
    for (org, wf), appels in par_agent.items():
        version = next((a["version"] for a in appels if a.get("version") is not None), None)
        agents.append(
            {
                "organization_id": org,
                "organization_nom": portee.get(org, ""),
                "workflow_id": wf,
                "workflow_nom": appels[0]["workflow_nom"],
                "version": version,
                **_chiffres(qualite._resume(appels)),
            }
        )
    agents.sort(key=lambda a: (-a["appels"], a["organization_nom"].lower(), a["workflow_nom"]))
    return {
        "jours": jours,
        "mondial": qualite._resume(lignes),
        "motifs": qualite._motifs(lignes),
        "par_client": clients,
        "agents": agents[offset : offset + limit],
        "total_agents": len(agents),
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------- compteurs du Labo
class LigneCompteurs(BaseModel):
    organization_id: int
    organization_nom: str
    espace: Literal["labo", "client"]
    agents: int
    agents_publies: int
    appels_7j: int
    note: float | None
    signalements: int
    pannes: int


class CompteursEquipe(BaseModel):
    clients: list[LigneCompteurs]
    total: int
    limit: int
    offset: int
    totaux: dict[str, int]


@router.get("/compteurs", response_model=CompteursEquipe)
async def compteurs_de_tous_les_clients(
    organization_id: int | None = Query(None),
    limit: int = Query(PAR_PAGE, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: UserModel = Depends(equipe),
) -> dict[str, Any]:
    portee = await _portee(user, organization_id)
    labo = next((e["id"] for e in await espaces.lister_espaces(user) if e["espace"] == "labo"), None)
    ids = list(portee)
    # Quatre lectures groupées pour les clients, une pour les problèmes, une pour le Chat : jamais une par client.
    stats, par_etat, chat = await asyncio.gather(
        db_client.statistiques_des_clients_relation(ids),
        db_client.compter_ameliorations_des_organisations(ids),
        db_client.compter_les_fils_en_attente_des_organisations(ids),
    )
    triees = sorted(portee.items(), key=lambda p: p[1].lower())
    page = triees[offset : offset + limit]
    cles = ("agents", "agents_publies", "appels_7j", "signalements", "pannes")
    return {
        "clients": [
            {"organization_id": i, "organization_nom": n, "espace": "labo" if i == labo else "client", **stats[i]} for i, n in page
        ],
        "total": len(triees),
        "limit": limit,
        "offset": offset,
        "totaux": {
            **{k: sum(int(stats[i][k]) for i in portee) for k in cles},
            # Les pastilles de la barre dans le Labo : problèmes à trier et conversations du builder qui attendent, tous clients.
            "a_trier": int(par_etat.get("a_trier", 0)),
            "chat_en_attente": chat,
        },
    }


# ---------------------------------------------------------------------- Conversations (colonne Client)
@router.get("/conversations", response_model=ConversationsEquipeResponse)
async def conversations_de_tous_les_clients(
    organization_id: int | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: UserModel = Depends(equipe),
) -> ConversationsEquipeResponse:
    return await conversations_de_l_equipe(organization_id=organization_id, limit=limit, offset=offset, user=user)


# ---------------------------------------------------------------------- Chat du Labo
class FilEquipe(BaseModel):
    id: int
    organization_id: int
    organization_nom: str
    workflow_id: int | None
    titre: str
    etat: str
    cout: float
    changements: int
    auteur: str | None
    genre: str
    modifie_le: Any


class FilsEquipe(BaseModel):
    fils: list[FilEquipe]
    total: int
    limit: int
    offset: int


@router.get("/chat", response_model=FilsEquipe)
async def chat_de_tous_les_clients(
    organization_id: int | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: UserModel = Depends(equipe),
) -> dict[str, Any]:
    portee = await _portee(user, organization_id)
    fils, total = await db_client.lister_fils_des_organisations(list(portee), limite=limit, decalage=offset)
    return {
        "fils": [
            {
                "id": f.id,
                "organization_id": f.organization_id,
                "organization_nom": portee.get(f.organization_id, ""),
                "workflow_id": f.workflow_id,
                "titre": f.titre,
                "etat": f.etat,
                "cout": f.cout or 0.0,
                "changements": f.changements or 0,
                "auteur": f.auteur,
                "genre": f.genre or "principal",
                "modifie_le": f.modifie_le,
            }
            for f in fils
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
