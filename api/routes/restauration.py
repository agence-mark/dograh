"""[.mark] Module Restauration, lot 22 : la route d'écoute du flux en direct (contrat portail ↔ fork § 2 et 3).

``GET /restauration/flux?etablissements=1,2&role=equipe`` : un flux ``text/event-stream`` des établissements DE L'ORGANISATION de la clé
(ou de la session), jamais d'une autre. Permission : ``conversations.voir`` (ouverte à la clé du portail, registre des routes).

- L'organisation est celle de la requête ; chaque établissement demandé est relu contre la base de CETTE organisation avant
  d'ouvrir quoi que ce soit : un identifiant inconnu d'elle (d'une autre organisation, ou qui n'existe pas) fait refuser toute la
  demande (404, sans dire lequel), rien n'est lu.
- ``Last-Event-ID`` : la reprise rejoue ce qui a été manqué (sans perte ni doublon) ; ``event: flux.reprise_impossible`` quand des
  événements ont été retirés depuis : le client relit la base.
- ``role=tablette`` (Employé) : ``appel.tour`` (transcription) ne lui est jamais envoyé. Le portail, qui tient la clé, déclare le rôle
  de la personne qu'il sert ; sans ``role`` : ``equipe``.
- Aucune connexion de base n'est gardée pendant que le flux dure.
"""

from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from api.db.bases_clients.connexion import BaseClientIndisponible, connecter
from api.db.bases_clients.restauration_commun import etablissements_existants
from api.db.models import UserModel
from api.services.auth.depends import get_user_with_selected_organization
from api.services.base_client import rattachement
from api.services.restauration import flux

router = APIRouter(prefix="/restauration", tags=["restauration"])

MAX_ETABLISSEMENTS = 50
_LISTE = re.compile(r"^[0-9]{1,12}(,[0-9]{1,12})*$")


def _refus(code: int, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail=message)


async def _etablissements_de_l_organisation(organization_id: int, demandes: str) -> list[int]:
    if not _LISTE.match(demandes.strip()):
        raise _refus(422, "etablissements: a comma-separated list of establishment identifiers.")
    ids = list(dict.fromkeys(int(x) for x in demandes.strip().split(",")))
    if len(ids) > MAX_ETABLISSEMENTS or 0 in ids:
        raise _refus(422, f"etablissements: between 1 and {MAX_ETABLISSEMENTS} identifiers.")
    nom = await rattachement.nom_de_la_base(organization_id)
    if not nom:
        raise _refus(409, "Attach a client database first: the establishments live there.")
    try:
        connexion = await connecter(nom)
    except BaseClientIndisponible as erreur:
        raise _refus(503, str(erreur)) from None
    try:
        existants = await etablissements_existants(connexion, ids)
    finally:
        await connexion.close()
    if existants != set(ids):
        raise _refus(404, "Establishment not found.")  # sans dire lequel : jamais un moyen de sonder les identifiants d'une autre organisation
    return ids


@router.get(
    "/flux",
    responses={200: {"description": "Server-sent events: one event per change, resumable with Last-Event-ID.", "content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
async def get_flux(
    request: Request,
    etablissements: str = Query(description="Establishment identifiers of the organization, separated by commas."),
    role: Literal["equipe", "tablette"] = Query(default="equipe", description="``tablette``: the transcription (appel.tour) is never sent."),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """The live feed of the establishments, for the portal and the fork screens."""
    ids = await _etablissements_de_l_organisation(user.selected_organization_id, etablissements)
    generateur = flux.ecouter(
        user.selected_organization_id, ids, role=role, reprise=last_event_id, est_deconnecte=request.is_disconnected,
        nb_battements_max=_battements_max(),
    )
    return StreamingResponse(
        generateur, media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}
    )


def _battements_max() -> int:
    """Une seule valeur de production ; les tests la baissent pour qu'une réponse en flux se termine."""
    return flux.NB_BATTEMENTS_MAX
