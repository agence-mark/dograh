"""[.mark] Partie 3, L5b (décision 16 de l'audit) : la page de pilotage d'un client, pour l'équipe .mark.

``GET /vues-equipe/pilotage/{organization_id}?periode=24h|7j|30j|90j`` (7 jours par défaut) : une seule réponse qui assemble ce que
la page montre (``services/pilotage_client``). Le client est lu dans l'ADRESSE et contrôlé à chaque requête contre ce que le rôle du
compte ouvre (404 sinon, comme s'il n'existait pas) ; une clé d'API ou un compte sans rôle d'équipe reçoit 403. Lecture seule.
La permission est celle des autres vues de l'équipe (``conversations.voir``, règle ``/vues-equipe`` du registre).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.db.models import UserModel
from api.routes.vues_equipe import _portee, equipe
from api.services import pilotage_client

router = APIRouter(prefix="/vues-equipe/pilotage", tags=["vues-equipe"])


class ChiffrePilotage(BaseModel):
    id: Literal["appels", "resolus", "transferes", "note", "cout", "duree"]
    valeur: float | None
    precedente: float | None
    tendance: float | None
    disponible: bool
    # Pourquoi il manque : aucun appel sur la période, bilan non rangé, juge éteint, coût non relevé, durée non relevée.
    raison: Literal["aucun_appel", "bilan", "juge", "prix", "duree"] | None


class MotifPilotage(BaseModel):
    motif: str
    appels: int
    part_resolu: float | None
    part_transferts: float | None
    note: float | None


class AutreBranche(BaseModel):
    nom: str
    part: int
    version: int | None


class PretPilotage(BaseModel):
    etat: Literal["pret", "afaire", "bloque"]
    n: int


class AgentPilotage(BaseModel):
    id: int
    nom: str
    version: int | None
    publie: bool
    part: int
    autres: list[AutreBranche]
    appels: int
    note: float | None
    pret: PretPilotage | None


class AlerteActive(BaseModel):
    id: str | None
    type: str | None
    workflow_id: int | None
    workflow_nom: str
    resume: str
    levee_le: str


class AlertesPilotage(BaseModel):
    total: int
    liste: list[AlerteActive]


class EtapeInstallation(BaseModel):
    numero: int
    titre: dict[str, str]
    etat: str


class InstallationPilotage(BaseModel):
    etapes: list[EtapeInstallation]
    prochaine: int | None
    faites: int
    total: int


class DernierMessage(BaseModel):
    fil_id: int
    sujet: str
    texte: str
    auteur: str
    cree_le: str


class RelationPilotage(BaseModel):
    ouverts: int
    non_lus: int
    demandes_nouvelles: int
    dernier: DernierMessage | None


class GestePilotage(BaseModel):
    id: int
    action: str
    qui: str | None
    par_builder: bool
    quand: str


class Pilotage(BaseModel):
    periode: Literal["24h", "7j", "30j", "90j"]
    jours: int
    en_service: bool
    chiffres: list[ChiffrePilotage] | None
    tronque: bool
    motifs: list[MotifPilotage] | None
    agents: list[AgentPilotage] | None
    alertes: AlertesPilotage | None
    problemes_graves: int | None
    installation: InstallationPilotage | None
    relation: RelationPilotage | None
    activite: list[GestePilotage] | None
    illisibles: list[str]


@router.get("/{organization_id}", response_model=Pilotage)
async def pilotage_d_un_client(
    organization_id: int,
    periode: Literal["24h", "7j", "30j", "90j"] = Query(pilotage_client.PERIODE_PAR_DEFAUT),
    user: UserModel = Depends(equipe),
) -> dict[str, Any]:
    await _portee(user, organization_id)  # 404 si le rôle n'ouvre pas ce client
    return await pilotage_client.assembler(organization_id, periode)
