"""[.mark] Module Restauration, lot 9 : le BRANCHEMENT d'un établissement à HubRise (OAuth, abonnement aux messages, import complet).

Le flux (T-03 : OAuth maison, Nango n'étant pas prêt) :

1. ``commencer_le_branchement`` : pose un ``state`` ALÉATOIRE, à USAGE UNIQUE, qui n'est gardé qu'EN EMPREINTE (SHA-256) dans Redis, dix minutes, avec
   l'organisation, l'établissement et la personne qui demande ; rend l'adresse d'autorisation de HubRise (liste fermée).
2. HubRise renvoie la personne vers ``/restauration/caisse/hubrise/retour?code=…&state=…`` : ``terminer_le_branchement`` consomme le ``state`` (lu et
   effacé d'un seul geste : un second passage, ou un ``state`` forgé, est refusé), échange le code contre le jeton (serveur à serveur), range le jeton dans
   le COFFRE d'identifiants de Dograh (``external_credentials``, par organisation) et ne garde dans la base du client que sa RÉFÉRENCE, relie le point
   de vente à l'établissement, s'abonne aux messages (sinon : mode passif, relève toutes les 30 s), puis importe tout (carte, ruptures, état).
3. Un point de vente déjà relié à un AUTRE établissement ou à une autre organisation est refusé : jamais deux.

Secrets : ``HUBRISE_CLIENT_ID`` et ``HUBRISE_CLIENT_SECRET`` (variables d'environnement) ; jamais imprimés. Le secret de notre application signe aussi les
messages que HubRise nous envoie (``X-HubRise-Hmac-SHA256``, ``hubrise_reception.py``).
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from typing import Any
from urllib.parse import urlencode

import redis.asyncio as aioredis
from loguru import logger

from api.constants import BACKEND_API_ENDPOINT, REDIS_URL
from api.db import db_client
from api.db.bases_clients import connexion as base_client
from api.db.bases_clients import restauration_liaison as liaison_db
from api.db.bases_clients.horloge import horloge
from api.db.point_de_vente_client import PointDeVenteDejaPris
from api.services.base_client import rattachement
from api.services.restauration import flux
from api.services.restauration.prises import hubrise_client as hc
from api.services.restauration.prises.prise import ContexteDePrise, enregistrer_prise_liee
from api.services.restauration.prises.prise_hubrise import NOM, PriseHubrise
from api.services.restauration.synchro_caisse import dire_la_liaison, importer_la_caisse

DUREE_DU_STATE_S = 600
CLE_STATE = "mark:resto:hubrise:state:"
PORTEE = "location[orders.read,orders.write,catalog.read,inventory.read,inventory.write,customer_list.read]"
# Lot 19 bis (N1, prouvé en 06) : ``own_order.update`` ne rend que les changements de NOS commandes (celles créées par notre connexion), sous la même forme de message
# (``resource_type: order``, ``event_type: update``, ``order_id``) : on ne reçoit plus la vie de tous les canaux. ``order.create`` reste : une commande créée dans la caisse
# (M10, lot 26) arrive par lui, elle entre au classeur.
EVENEMENTS = {"order": ["create"], "own_order": ["update"], "catalog": ["update"], "inventory": ["patch"], "location": ["update"]}
CHEMIN_RETOUR = "/api/v1/restauration/caisse/hubrise/retour"
CHEMIN_RAPPEL = "/api/v1/restauration/caisse/hubrise/rappel"


class NonConfiguree(RuntimeError):
    """``HUBRISE_CLIENT_ID`` / ``HUBRISE_CLIENT_SECRET`` absents : la prise ne peut pas se brancher (jamais un secret de substitution)."""


class BranchementRefuse(ValueError):
    """Le retour de HubRise n'est pas valable (``state`` inconnu, expiré ou déjà utilisé ; code refusé ; point de vente déjà pris). ``code`` : fermé."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def identifiants_de_l_application() -> tuple[str, str]:
    identifiant, secret = os.getenv("HUBRISE_CLIENT_ID"), os.getenv("HUBRISE_CLIENT_SECRET")
    if not identifiant or not secret:
        raise NonConfiguree("HubRise n'est pas configuré sur ce serveur.")
    return identifiant, secret


def secret_de_signature() -> str:
    """Le secret qui signe les messages de HubRise (celui de notre application)."""
    return identifiants_de_l_application()[1]


def adresse_de_retour() -> str:
    return BACKEND_API_ENDPOINT.rstrip("/") + CHEMIN_RETOUR


def adresse_de_rappel() -> str:
    return BACKEND_API_ENDPOINT.rstrip("/") + CHEMIN_RAPPEL


def _empreinte(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


async def _redis() -> aioredis.Redis:
    return aioredis.from_url(REDIS_URL, decode_responses=True, socket_timeout=3, socket_connect_timeout=3)


async def commencer_le_branchement(organization_id: int, etablissement_id: int, user_id: int) -> str:
    """L'adresse d'autorisation de HubRise pour CET établissement. Le ``state`` n'est jamais gardé en clair."""
    identifiant, _ = identifiants_de_l_application()
    state = secrets.token_urlsafe(32)
    r = await _redis()
    try:
        ok = await r.set(CLE_STATE + _empreinte(state), json.dumps({"o": organization_id, "e": etablissement_id, "u": user_id}), ex=DUREE_DU_STATE_S, nx=True)
    finally:
        await r.aclose()
    if not ok:
        raise RuntimeError("State déjà posé : réessayer.")  # collision de 256 bits : jamais en pratique
    requete = urlencode({"redirect_uri": adresse_de_retour(), "client_id": identifiant, "scope": PORTEE, "state": state})
    return f"{hc.BASE_AUTORISATION}/authorize?{requete}"


async def _consommer_le_state(state: str) -> dict[str, int]:
    """Lit ET efface le ``state`` d'un seul geste (``GETDEL``) : un second passage le trouve vide. Refuse un ``state`` inconnu, expiré ou mal formé."""
    if not isinstance(state, str) or not (20 <= len(state) <= 200):
        raise BranchementRefuse("state_invalide")
    r = await _redis()
    try:
        brut = await r.getdel(CLE_STATE + _empreinte(state))
    finally:
        await r.aclose()
    if brut is None:
        raise BranchementRefuse("state_invalide")
    try:
        donnees = json.loads(brut)
        return {"organization_id": int(donnees["o"]), "etablissement_id": int(donnees["e"]), "user_id": int(donnees["u"])}
    except (ValueError, KeyError, TypeError):
        raise BranchementRefuse("state_invalide") from None


async def _ranger_le_jeton(organization_id: int, user_id: int, etablissement_id: int, uuid_existant: str | None, donnees: dict[str, Any]) -> str:
    """Le jeton va dans le coffre d'identifiants de Dograh (rangé par organisation). Une reconnexion REMPLACE le jeton de la référence déjà posée.
    ⛔ « Débrancher » désactive le jeton ; le reprendre sans le réactiver laissait une liaison « ok » sans prise (lot 19, SA-23).
    Après un débranchement, le jeton du même nom est réactivé avec les données neuves (le nom est unique par organisation)."""
    if uuid_existant and await db_client.get_credential_by_uuid(uuid_existant, organization_id):
        await db_client.update_credential(uuid_existant, organization_id, credential_data=donnees)
        return uuid_existant
    nom = f"caisse-hubrise-{etablissement_id}"
    ancien = next((c for c in await db_client.get_credentials_for_organization(organization_id, active_only=False) if c.name == nom), None)
    if ancien is not None:
        await db_client.reactiver_credential(ancien.credential_uuid, organization_id, donnees)  # actif ou désactivé : jeton neuf, actif
        return ancien.credential_uuid
    cree = await db_client.create_credential(
        organization_id, user_id, nom, "bearer_token", donnees, description="Caisse HubRise de l'établissement (module Restauration : ne pas modifier)"
    )
    return cree.credential_uuid


async def terminer_le_branchement(code: str, state: str, *, transport=None, saut_import: bool = False) -> dict[str, Any]:
    """Le retour de HubRise. Rend ``{organization_id, etablissement_id, point_de_vente, passif, import}`` ou lève ``BranchementRefuse`` / ``ErreurHubrise``."""
    cible = await _consommer_le_state(state)
    org, etab, user = cible["organization_id"], cible["etablissement_id"], cible["user_id"]
    identifiant, secret = identifiants_de_l_application()
    jeton = await hc.echanger_le_code(code, identifiant, secret, transport=transport)
    nom_base = await rattachement.nom_de_la_base(org)
    if not nom_base:
        raise BranchementRefuse("base_absente")
    connexion = await base_client.connecter(nom_base)
    try:
        cle = await liaison_db.cle_du_site(connexion, etab)
        if cle is None:
            raise BranchementRefuse("etablissement_inconnu")  # jamais lié à un établissement que cette base ne connaît pas
        point_de_vente = str(jeton["location_id"])
        try:
            await db_client.lier_point_de_vente(org, NOM, point_de_vente, cle, horloge(nom_base).maintenant())
        except PointDeVenteDejaPris:
            raise BranchementRefuse("point_de_vente_deja_pris") from None
        donnees = {
            "token": jeton["access_token"], "fournisseur": NOM, "point_de_vente": point_de_vente, "catalogue": jeton.get("catalog_id"),
            "liste_clients": jeton.get("customer_list_id"), "compte": jeton.get("account_id"),
        }
        reference = await _ranger_le_jeton(org, user, etab, await liaison_db.acces(connexion, etab), donnees)
        await liaison_db.poser_liaison(connexion, etab, NOM, point_de_vente, "ok", source="mark", auteur=f"branchement:{user}")
        await liaison_db.poser_acces(connexion, etab, reference)
        client = hc.ClientHubrise(jeton["access_token"], point_de_vente=point_de_vente, catalogue=donnees["catalogue"], liste_clients=donnees["liste_clients"], transport=transport)
        passif = await s_abonner(client, connexion, etab)
        bilan = None
        if not saut_import:
            contexte = ContexteDePrise(connexion, org, etab, nom_base, transport)
            bilan = await importer_la_caisse(await _fabrique(contexte), connexion, org, etab)
        else:
            await dire_la_liaison(connexion, org, etab, "ok", synchro=True)
        await flux.emettre(org, etab, "caisse.liaison", {"etat": "ok"})
    finally:
        await connexion.close()
    return {"organization_id": org, "etablissement_id": etab, "point_de_vente": point_de_vente, "passif": passif, "import": bilan}


async def s_abonner(client: hc.ClientHubrise, connexion, etablissement_id: int) -> bool:
    """Abonne la connexion aux messages signés. Si notre adresse n'est pas joignable par HubRise (le cas en local) ou si l'abonnement est refusé : MODE PASSIF
    (``url: null``, la relève des messages toutes les 30 s, lot 10). Rend ``True`` si la liaison est en mode passif."""
    try:
        await client.requete("POST", "/callback", corps={"url": adresse_de_rappel(), "events": EVENEMENTS}, rejouable=True)
        passif = False
    except hc.ErreurHubrise as erreur:
        if isinstance(erreur, hc.JetonRefuse):
            raise
        logger.warning(f"[.mark] HubRise callback subscription refused ({erreur.code}): passive mode for establishment {etablissement_id}")
        await client.requete("POST", "/callback", corps={"url": None, "events": EVENEMENTS}, rejouable=True)
        passif = True
    await liaison_db.poser_la_veille(connexion, etablissement_id, passif=passif)
    return passif


async def _fabrique(contexte: ContexteDePrise) -> PriseHubrise:
    """La prise HubRise de CET établissement : son jeton est relu du coffre de SON organisation (jamais d'un autre). Sans accès : une prise qui refuse tout geste."""
    reference = await liaison_db.acces(contexte.connexion, contexte.etablissement_id) if contexte.organization_id is not None else None
    credential = await db_client.get_credential_by_uuid(reference, contexte.organization_id) if reference else None
    donnees = (credential.credential_data or {}) if credential else {}
    if not donnees.get("token"):
        return PriseHubrise()
    suite: dict[str, Any] = {}
    if donnees.get("demo"):
        # Lot 20 : une liaison à la CAISSE DE DÉMO. L'adresse n'est JAMAIS lue du coffre (un client pourrait y écrire) : elle est celle de ce serveur, et seule
        # l'organisation marquée Labo, interrupteur allumé, peut s'y brancher. Sinon la prise refuse tout geste : jamais une prise d'un client sur la caisse de démo.
        from api.services.restauration.caisse_demo import garde
        from api.services.restauration.caisse_demo.adresse import adresse_de_la_caisse

        if not await garde.caisse_de_demo_permise(contexte.organization_id):
            return PriseHubrise()
        suite = {"labo": True, "base": adresse_de_la_caisse()}
    client = hc.ClientHubrise(
        donnees["token"], point_de_vente=donnees.get("point_de_vente"), catalogue=donnees.get("catalogue"), liste_clients=donnees.get("liste_clients"), transport=contexte.transport,
        **suite,
    )

    async def sur_jeton_refuse():
        if contexte.organization_id is None:
            return
        await dire_la_liaison(contexte.connexion, contexte.organization_id, contexte.etablissement_id, "rompue", "jeton_refuse")

    async def genre(code: str):
        return await liaison_db.genre_du_code(contexte.connexion, contexte.etablissement_id, code)

    return PriseHubrise(client, sur_jeton_refuse=sur_jeton_refuse, genre_de_code=genre)


enregistrer_prise_liee(NOM, _fabrique)
