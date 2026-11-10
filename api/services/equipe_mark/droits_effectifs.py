"""[.mark] Clôture, lot A (D21) : UNE seule table de droits pour l'écran, l'API et chaque outil MCP.

Les permissions d'une requête sont calculées ici et nulle part ailleurs :

* **session** (écran) : les permissions du rôle d'équipe du compte ;
* **clé d'API portée par un rôle** : les permissions de ce rôle, bornées par celles de son créateur AU MOMENT DE L'APPEL (un créateur qui perd un
  droit le fait perdre à sa clé), et l'organisation de la clé doit rester ouverte au rôle de son créateur ; jamais les gestes de l'équipe elle-même
  (``PERMISSIONS_JAMAIS_PAR_CLE_A_ROLE``) ;
* **clé d'API sans rôle** (clé d'avant ou du portail) : la liste fermée ``PERMISSIONS_DE_CLE``.

Une lecture qui échoue ferme (aucune permission) : on ne prête pas de droits sur une base lente.
"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
from loguru import logger

from api.db import db_client
from api.services.equipe_mark.permissions import (
    PERMISSIONS_DE_CLE,
    PERMISSIONS_IMPLIQUEES,
    PERMISSIONS_JAMAIS_PAR_CLE_A_ROLE,
)


def avec_les_permissions_impliquees(permissions) -> frozenset[str]:
    permissions = frozenset(permissions)
    return permissions | {implicite for implicite, requise in PERMISSIONS_IMPLIQUEES.items() if requise in permissions}


async def permissions_de_la_cle(user) -> frozenset[str]:
    """Les permissions d'une clé d'API (``user.cle_api_role_id`` posé par l'authentification par clé)."""
    role_id = getattr(user, "cle_api_role_id", None)
    if role_id is None:
        return PERMISSIONS_DE_CLE
    try:
        role = await db_client.obtenir_role(role_id)
        createur = await db_client.acces_du_compte(user.id)
        if role is None or createur is None:
            return frozenset()
        from api.services.builder.constantes import organisation_bibliotheque
        from api.services.equipe_mark.acces import organisation_est_ouverte

        org = getattr(user, "selected_organization_id", None)
        labo = organisation_bibliotheque()
        if org is None or not organisation_est_ouverte(createur, org, labo):
            return frozenset()
        bornes = avec_les_permissions_impliquees(createur.permissions)
        return frozenset(p for p in role["permissions"] if p in bornes and p not in PERMISSIONS_JAMAIS_PAR_CLE_A_ROLE)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[droits] droits de clé illisibles ({type(erreur).__name__}) : aucune permission")
        return frozenset()


async def permissions_de(user) -> frozenset[str]:
    """Les permissions de la requête, session ou clé, avec les permissions impliquées."""
    if getattr(user, "par_cle_api", False):
        return avec_les_permissions_impliquees(await permissions_de_la_cle(user))
    try:
        acces = await db_client.acces_du_compte(user.id)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[droits] droits illisibles ({type(erreur).__name__}) : aucune permission")
        return frozenset()
    return avec_les_permissions_impliquees(acces.permissions) if acces is not None else frozenset()


async def exiger_une_cle_a_role_vivante(user) -> None:
    """SA-9 (2) : une clé PORTÉE PAR UN RÔLE dont les permissions sont vides (créateur absent, retiré de l'équipe, bloqué, organisation plus
    ouverte au créateur ni au rôle) n'a plus d'accès du tout : ni les routes ouvertes à tout membre, ni les outils MCP de lecture.
    Une clé sans rôle (portail) n'est pas concernée."""
    if getattr(user, "par_cle_api", False) and getattr(user, "cle_api_role_id", None) is not None and not await permissions_de_la_cle(user):
        raise HTTPException(status_code=403, detail="This API key no longer has any rights (its creator or its role no longer opens this space)")


def est_cle_sans_role(user) -> bool:
    return bool(getattr(user, "par_cle_api", False)) and getattr(user, "cle_api_role_id", None) is None


def est_cle_du_labo(user) -> bool:
    """Clé d'API rattachée à l'organisation Labo (la clé de Claude Code de .mark)."""
    from api.services.builder.constantes import organisation_bibliotheque

    labo = organisation_bibliotheque()
    return bool(getattr(user, "par_cle_api", False)) and labo is not None and getattr(user, "selected_organization_id", None) == labo


def lecture_fermee_a_la_cle_de_client(user) -> bool:
    """D10 : une clé SANS rôle d'une organisation qui n'est pas le Labo ne lit ni les agents, ni les outils, ni le builder.
    La clé du Labo et une clé portée par un rôle (droits de la personne) gardent leur lecture."""
    return est_cle_sans_role(user) and not est_cle_du_labo(user)
