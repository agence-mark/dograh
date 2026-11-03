"""[.mark] Qui a le droit d'entrer dans quelle organisation, et de faire quoi.

Appelé par ``get_user`` à CHAQUE requête authentifiée (``services/auth/depends.py``) :

1. l'organisation vient de l'adresse (en-tête ``X-Mark-Organisation``, posé par l'écran d'après ``/clients/<org>`` ou
   ``/labo``) ; ``selected_organization_id`` ne sert qu'en défaut ; une clé d'API garde SON organisation ;
2. l'organisation demandée doit être accessible au compte : membre de l'organisation, et, pour un compte de
   l'équipe, ouverte par son rôle (le Labo, tous les clients, ou des clients choisis) ;
3. la route doit avoir une décision au registre (``registre_routes``) : permission, membre, ou exemption écrite ;
   une route sans décision est REFUSÉE (fermé par défaut) ;
4. le geste d'écriture qui exige une permission est écrit au journal (qui, quoi, quel espace, quand).

Un compte sans rôle d'équipe n'a que les routes ``MEMBRE`` de ses propres organisations.
"""

from __future__ import annotations

from fastapi import HTTPException
from loguru import logger
from sqlalchemy.orm import object_session
from starlette.requests import HTTPConnection

from api.db import db_client
from api.db.equipe_client import AccesCompte
from api.services.equipe_mark.registre_routes import (
    ECRITURE,
    Exemption,
    Permission,
    decision_de,
)

ENTETE_ORGANISATION = "X-Mark-Organisation"
PREFIXE_API = "/api/v1"
ROUTES_QUI_JOURNALISENT_ELLES_MEMES = ("/equipe-mark/", "/espaces/")


def organisation_est_ouverte(acces: AccesCompte, organization_id: int, labo_id: int | None) -> bool:
    """Le rôle ouvre-t-il cette organisation ? (le Labo, tous les clients, ou des clients choisis)."""
    if labo_id is not None and organization_id == labo_id:
        return acces.labo_ouvert
    return acces.tous_les_clients or organization_id in acces.organisations


async def organisation_accessible(
    user_id: int, organization_id: int, acces: AccesCompte | None, labo_id: int | None
) -> bool:
    """Membre de l'organisation et, pour un compte de l'équipe, ouverte par son rôle.

    Un compte de l'équipe dont le rôle ouvre l'organisation en devient membre à la première visite : une
    organisation créée après lui est donc accessible sans geste de personne.
    """
    if acces is not None:
        if not organisation_est_ouverte(acces, organization_id, labo_id):
            return False
        if not await db_client.is_user_member_of_organization(user_id, organization_id):
            await db_client.add_user_to_organization(user_id, organization_id)
        return True
    return bool(await db_client.is_user_member_of_organization(user_id, organization_id))


def _chemin_de_la_route(connexion: HTTPConnection) -> tuple[str, str] | None:
    route = connexion.scope.get("route")
    if route is None:
        return None
    modele = getattr(route, "path_format", None) or getattr(route, "path", None)
    if not modele:
        return None
    if modele.startswith(PREFIXE_API):
        modele = modele[len(PREFIXE_API) :] or "/"
    methode = "WS" if connexion.scope.get("type") == "websocket" else connexion.scope.get("method", "GET")
    return methode.upper(), modele


def _fixer_organisation(user, organization_id: int | None) -> None:
    """Change l'organisation de CETTE requête sans jamais l'écrire en base : le compte est détaché de sa session d'abord."""
    session = object_session(user)
    if session is not None:
        session.expunge(user)
    user.selected_organization_id = organization_id


async def appliquer_acces(connexion: HTTPConnection, user, *, par_cle_api: bool) -> None:
    """Fixe l'organisation de la requête et vérifie l'accès ; lève 400, 403 sinon. Modifie ``user`` en mémoire seulement."""
    from api.services.builder.constantes import organisation_bibliotheque
    from api.services.equipe_mark.espaces import rafraichir_labo

    await rafraichir_labo()  # le Labo marqué en base (cache court) ; le repli par variable ne sert que sans marquage
    labo_id = organisation_bibliotheque()
    acces = await db_client.acces_du_compte(user.id)
    brut = (connexion.headers.get(ENTETE_ORGANISATION) or "").strip()

    if par_cle_api:
        # Une clé d'API appartient à UNE organisation : l'adresse ne peut pas la déplacer.
        if brut and brut != str(user.selected_organization_id):
            raise HTTPException(status_code=403, detail="An API key is scoped to its own organization")
    elif brut:
        if not brut.isdigit():
            raise HTTPException(status_code=400, detail="Invalid organization in the address")
        demandee = int(brut)
        if not await organisation_accessible(user.id, demandee, acces, labo_id):
            raise HTTPException(status_code=403, detail="Organization not accessible")
        _fixer_organisation(user, demandee)
    elif user.selected_organization_id is not None and acces is not None:
        # Défaut : l'organisation choisie auparavant, si le rôle l'ouvre encore ; sinon aucune.
        if not organisation_est_ouverte(acces, user.selected_organization_id, labo_id):
            _fixer_organisation(user, None)

    # --- la décision de la route
    position = _chemin_de_la_route(connexion)
    if position is None:
        return
    methode, chemin = position
    trouvee = decision_de(methode, chemin)
    if trouvee is None:
        logger.error(f"Route without permission decision: {methode} {chemin}")
        raise HTTPException(status_code=403, detail="Route without a permission decision")
    decision, _ = trouvee
    if isinstance(decision, Exemption):
        return
    if isinstance(decision, Permission):
        if acces is None or decision.cle not in acces.permissions:
            raise HTTPException(status_code=403, detail=f"Permission required: {decision.cle}")
        # Les routes de l'équipe et des espaces écrivent elles-mêmes leur ligne (avec le détail du geste).
        if methode in ECRITURE and not chemin.startswith(ROUTES_QUI_JOURNALISENT_ELLES_MEMES):
            await journaliser(
                user,
                decision.cle,
                user.selected_organization_id,
                {"route": f"{methode} {chemin}"},
            )


def auteur_du_journal(user) -> str:
    """L'identifiant du compte (jamais une adresse), ou l'auteur du portail pour une clé d'API."""
    return getattr(user, "mark_auteur", None) or str(getattr(user, "provider_id", None) or user.id)


async def journaliser(user, action: str, organization_id: int | None, detail: dict | None = None) -> None:
    """Une ligne au journal. Une panne d'écriture se consigne et ne bloque jamais le geste déjà autorisé."""
    try:
        await db_client.ecrire_journal(
            user_id=getattr(user, "id", None),
            auteur=auteur_du_journal(user),
            action=action,
            organization_id=organization_id,
            detail=detail,
        )
    except Exception:
        logger.exception("Journal write failed")
