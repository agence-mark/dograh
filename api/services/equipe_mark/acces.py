"""[.mark] Qui a le droit d'entrer dans quelle organisation, et de faire quoi.

Appelé par ``get_user`` à CHAQUE requête authentifiée (``services/auth/depends.py``) :

1. l'organisation vient de l'adresse (en-tête ``X-Mark-Organisation``, posé par l'écran d'après ``/clients/<org>`` ou
   ``/labo``) ; ``selected_organization_id`` ne sert qu'en défaut ; une clé d'API garde SON organisation ;
2. l'organisation demandée doit être accessible au compte : membre de l'organisation, et, pour un compte de
   l'équipe, ouverte par son rôle (le Labo, tous les clients, ou des clients choisis) ;
3. la route doit avoir une décision au registre (``registre_routes``) : permission, membre, ou exemption écrite ;
   une route sans décision est REFUSÉE (fermé par défaut) ;
4. le geste d'écriture qui exige une permission est écrit au journal (qui, quoi, quel espace, quand) APRÈS une réponse réussie.

Un compte sans rôle d'équipe n'a que les routes ``MEMBRE`` de ses propres organisations.

Une requête par clé d'API est marquée ``user.par_cle_api`` : elle n'a JAMAIS le rôle d'équipe de la personne qui a créé
la clé (revue serveur B1). ``acces_de``, ``synchroniser_appartenances``, ``lister_espaces``, la liste des organisations
et ``est_membre_de_l_equipe`` le respectent ; les routes ``/espaces`` lui sont fermées.
"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
from loguru import logger
from starlette.requests import HTTPConnection

from api.db import db_client
from api.db.equipe_client import AccesCompte, detacher_de_sa_session
from api.services.equipe_mark.permissions import PERMISSIONS, PERMISSIONS_DE_CLE, PERMISSIONS_IMPLIQUEES
from api.services.equipe_mark.registre_routes import (
    ECRITURE,
    Exemption,
    Permission,
    decision_de,
    ecrit_quelque_chose,
)

CLE_JOURNAL_DIFFERE = "mark_journal_differe"
ENTETE_ORGANISATION = "X-Mark-Organisation"
# R3 M1 : l'écran dit « je suis dans le Labo » ; sans identifiant, le serveur lit le Labo lui-même, jamais un client.
ENTETE_ESPACE = "X-Mark-Espace"
PREFIXE_API = "/api/v1"
# Partie 3, 17a : la clé n'a que la liste fermée ``PERMISSIONS_DE_CLE``. Ceci en est le complément (tout ce qui lui est refusé).
PERMISSIONS_JAMAIS_PAR_CLE = frozenset(PERMISSIONS) - PERMISSIONS_DE_CLE
# Écritures fermées aux clés même sous une permission qu'elles portent (lancer ou changer une campagne d'appels sortants).
ROUTES_ECRITURE_FERMEES_AUX_CLES = ("/campaign",)
ROUTES_QUI_JOURNALISENT_ELLES_MEMES = ("/equipe-mark/", "/espaces/", "/installations-client", "/user/api-keys")
# Les espaces sont la vue de l'équipe sur tous ses clients : jamais par une clé d'API (B1).
# RV (point 3) : l'agent en fichiers (export comme import) n'a pas sa propre permission de lecture : fermé aux clés (``18-a-exposer.md``).
ROUTES_FERMEES_AUX_CLES = ("/espaces", "/vues-equipe", "/agent-fichiers")
# Clôture, lot A (D10) : la lecture des agents, des outils et du builder est fermée à une clé SANS rôle d'un client (la clé du Labo et une clé
# portée par un rôle gardent la leur). Les documents (connaissances) restent ouverts : le portail les lit.
ROUTES_LECTURE_FERMEES_AUX_CLES_DE_CLIENT = ("/workflow", "/tools", "/builder", "/agents")
LECTURE_FERMEE_AUX_CLES_DE_CLIENT = frozenset({"GET", "HEAD"})
# Clôture, lot A (D11) : le miroir de Claude Code ne se range qu'avec la clé du Labo, quel que soit le rôle d'une autre clé.
ROUTES_RESERVEES_A_LA_CLE_DU_LABO = ("/builder/miroir",)


def est_par_cle_api(user) -> bool:
    return bool(getattr(user, "par_cle_api", False))


async def acces_de(user) -> AccesCompte | None:
    """Le rôle d'équipe du compte de la requête ; ``None`` pour une clé d'API, quel que soit le rôle de son créateur."""
    if est_par_cle_api(user):
        return None
    return await db_client.acces_du_compte(user.id)


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
    detacher_de_sa_session(user)
    user.selected_organization_id = organization_id


async def appliquer_acces(connexion: HTTPConnection, user, *, par_cle_api: bool) -> None:
    """Fixe l'organisation de la requête et vérifie l'accès ; lève 400, 403 sinon. Modifie ``user`` en mémoire seulement."""
    from api.services.builder.constantes import organisation_bibliotheque
    from api.services.equipe_mark.espaces import rafraichir_labo

    await rafraichir_labo()  # le Labo marqué en base (cache court) ; le repli par variable ne sert que sans marquage
    labo_id = organisation_bibliotheque()
    # Une clé d'API est un accès de machine à UNE organisation, sans rôle d'équipe (B1) : marqué avant toute lecture
    # (attribut en mémoire, hors des colonnes : jamais écrit en base), posé à CHAQUE requête dans les deux sens, car un
    # même objet de compte peut servir deux requêtes (carte d'identité d'une session partagée).
    user.par_cle_api = bool(par_cle_api)
    user.par_porte_mcp = False  # posé à True par la seule porte MCP (``mcp_server/auth.py``), jamais par une route HTTP
    acces = await acces_de(user)
    brut = (connexion.headers.get(ENTETE_ORGANISATION) or "").strip()
    espace = (connexion.headers.get(ENTETE_ESPACE) or "").strip().lower()

    if espace and not par_cle_api:
        # Page du Labo : l'organisation est le Labo, ou la requête est refusée. Jamais le repli sur l'organisation du compte.
        if espace != "labo":
            raise HTTPException(status_code=400, detail="Invalid space in the address")
        if labo_id is None:
            raise HTTPException(status_code=403, detail="Organization not accessible")
        if brut and brut != str(labo_id):
            raise HTTPException(status_code=403, detail="Organization not accessible")
        brut = str(labo_id)

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
    if par_cle_api and any(chemin == r or chemin.startswith(r + "/") for r in ROUTES_FERMEES_AUX_CLES):
        raise HTTPException(status_code=403, detail="Not available to an API key")
    if par_cle_api and methode in ECRITURE and any(chemin == r or chemin.startswith(r + "/") for r in ROUTES_ECRITURE_FERMEES_AUX_CLES):
        raise HTTPException(status_code=403, detail="Not available to an API key")
    if par_cle_api and methode in LECTURE_FERMEE_AUX_CLES_DE_CLIENT and any(
        chemin == r or chemin.startswith(r + "/") for r in ROUTES_LECTURE_FERMEES_AUX_CLES_DE_CLIENT
    ):
        from api.services.equipe_mark.droits_effectifs import lecture_fermee_a_la_cle_de_client

        if lecture_fermee_a_la_cle_de_client(user):
            raise HTTPException(status_code=403, detail="Not available to an API key of a client")
    if par_cle_api and chemin in ROUTES_RESERVEES_A_LA_CLE_DU_LABO:
        from api.services.equipe_mark.droits_effectifs import est_cle_du_labo

        if not est_cle_du_labo(user):
            raise HTTPException(status_code=403, detail="Reserved to the Labo API key")
    trouvee = decision_de(methode, chemin)
    if trouvee is None:
        logger.error(f"Route without permission decision: {methode} {chemin}")
        raise HTTPException(status_code=403, detail="Route without a permission decision")
    decision, _ = trouvee
    if isinstance(decision, Exemption):
        return
    if isinstance(decision, Permission):
        journal_cle = decision.cle  # RV2 (M-3) : pour une clé, la permission réellement requise (``pour_cle``), pas celle de la session
        if par_cle_api:
            # Une clé d'API est un accès de machine à UNE organisation. Clôture, lot A (D21) : ses permissions viennent de la table unique
            # (``droits_effectifs``) : le rôle qu'elle porte (borné par son créateur, jamais les gestes de l'équipe) ou, sans rôle, la liste
            # fermée des clés (17a). Une clé sans rôle ne lit ni les agents, ni les outils, ni le builder d'un client (D10).
            from api.services.equipe_mark.droits_effectifs import permissions_de

            permissions = await permissions_de(user)
            if decision.pour_cle is not None and decision.pour_cle in permissions:
                journal_cle = decision.pour_cle
            elif decision.cle in permissions:
                journal_cle = decision.cle
            else:
                requise = decision.pour_cle or decision.cle
                raise HTTPException(status_code=403, detail=f"Permission required: {requise} (not available to this API key)")
        elif acces is None or not (
            decision.cle in acces.permissions
            or PERMISSIONS_IMPLIQUEES.get(decision.cle) in acces.permissions
            or (decision.pour_cle is not None and decision.pour_cle in acces.permissions)
        ):
            raise HTTPException(status_code=403, detail=f"Permission required: {decision.cle}")
        # Les routes de l'équipe et des espaces écrivent elles-mêmes leur ligne (avec le détail du geste).
        # Clôture, SA-2 : la ligne ne s'écrit qu'APRÈS une réponse réussie (``journal_apres_succes``), jamais avant la route : un geste
        # en échec (4xx, 500) n'y figure pas. D23 : une route déclarée sans effet (``SANS_ECRITURE``) n'écrit aucune ligne ; une vraie écriture en écrit exactement une, avec sa cible.
        if methode in ECRITURE and not chemin.startswith(ROUTES_QUI_JOURNALISENT_ELLES_MEMES) and ecrit_quelque_chose(methode, chemin):
            detail: dict = {"route": f"{methode} {chemin}"}
            cible = _cible_de_la_requete(connexion)
            if cible:
                detail["cible"] = cible
            differer_le_journal(connexion, user, journal_cle, user.selected_organization_id, detail)


_PARAMETRES_SECRETS = ("token", "secret", "jeton", "password", "mot_de_passe")


def _cible_de_la_requete(connexion) -> dict | None:
    """Les paramètres d'ADRESSE de la requête (``workflow_id``, ``tool_uuid``...), jamais le corps ni un paramètre qui ressemble à un secret."""
    brut = getattr(connexion, "path_params", None) or {}
    cible = {
        str(cle): (valeur if isinstance(valeur, int) else str(valeur)[:80])
        for cle, valeur in brut.items()
        if isinstance(valeur, (int, str)) and not any(m in str(cle).lower() for m in _PARAMETRES_SECRETS)
    }
    return cible or None


def auteur_du_journal(user) -> str:
    """L'identifiant du compte (jamais une adresse), ou l'auteur du portail pour une clé d'API."""
    return getattr(user, "mark_auteur", None) or str(getattr(user, "provider_id", None) or user.id)


def origine_du_geste(user) -> str:
    """D23 : d'où vient le geste, ``mcp`` (porte MCP), ``api`` (clé d'API) ou ``ecran`` (session)."""
    if getattr(user, "par_porte_mcp", False):
        return "mcp"
    return "api" if getattr(user, "par_cle_api", False) else "ecran"


def differer_le_journal(connexion, user, action: str, organization_id: int | None, detail: dict | None) -> None:
    """Retient la ligne du geste ; ``journal_apres_succes`` l'écrit une fois la réponse rendue, si elle est réussie.

    On retient des VALEURS (identifiant, auteur, origine), jamais l'objet de compte : il peut être détaché ou réutilisé par la
    requête suivante. Une connexion sans portée (appel direct, test) n'a rien à retenir : ``journal_apres_succes`` ne la voit pas.
    """
    scope = getattr(connexion, "scope", None)
    if not isinstance(scope, dict):
        return
    scope[CLE_JOURNAL_DIFFERE] = (
        SimpleNamespace(
            id=getattr(user, "id", None),
            mark_auteur=getattr(user, "mark_auteur", None),
            provider_id=getattr(user, "provider_id", None),
            par_porte_mcp=bool(getattr(user, "par_porte_mcp", False)),
            par_cle_api=bool(getattr(user, "par_cle_api", False)),
        ),
        action,
        organization_id,
        detail,
    )


async def journaliser(user, action: str, organization_id: int | None, detail: dict | None = None) -> None:
    """Une ligne au journal. Une panne d'écriture se consigne et ne bloque jamais le geste déjà autorisé."""
    try:
        await db_client.ecrire_journal(
            user_id=getattr(user, "id", None),
            auteur=auteur_du_journal(user),
            action=action,
            organization_id=organization_id,
            detail=detail,
            origine=origine_du_geste(user),
        )
    except Exception:
        logger.warning("Journal write failed")
