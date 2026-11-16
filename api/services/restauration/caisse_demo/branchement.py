"""[.mark] Module Restauration, lot 20 : brancher la VRAIE prise HubRise d'un établissement du Labo sur un restaurant de test de la caisse de démo.

Le même chemin que « Brancher ma caisse » (``hubrise_liaison.terminer_le_branchement``), sans la page d'autorisation : un jeton NEUF de la caisse de démo est rangé
au coffre d'identifiants de l'organisation (avec le drapeau ``demo``, jamais l'adresse), le point de vente est relié à l'établissement, la prise s'abonne aux messages signés
(notre adresse de réception) et importe tout (carte, ruptures, état). Aucun code spécial côté prise : elle parle à la caisse de démo comme à HubRise.

Gardes : interrupteur allumé et organisation Labo (``garde``) ; l'établissement est relu contre la base de l'organisation ; un restaurant de test ne sert qu'UN établissement.
"""

from __future__ import annotations

from typing import Any

from api.db import db_client
from api.db.bases_clients import connexion as base_client
from api.db.bases_clients import restauration_direct
from api.db.bases_clients import restauration_liaison as liaison_db
from api.db.bases_clients.horloge import horloge
from api.db.point_de_vente_client import PointDeVenteDejaPris
from api.services.base_client import rattachement
from api.services.restauration import flux
from api.services.restauration.caisse_demo import garde, restaurants
from api.services.restauration.caisse_demo.adresse import adresse_de_la_caisse
from api.services.restauration.caisse_demo.moteur import catalogue_id_de, liste_de_clients_de
from api.services.restauration.prises import hubrise_client as hc
from api.services.restauration.prises import hubrise_liaison as hl
from api.services.restauration.prises.prise import ContexteDePrise
from api.services.restauration.prises.prise_hubrise import NOM
from api.services.restauration.synchro_caisse import dire_la_liaison, importer_la_caisse


class BranchementDeDemoRefuse(ValueError):
    """Le branchement est refusé. ``code`` : ``non_permis`` · ``restaurant_inconnu`` · ``base_absente`` · ``etablissement_inconnu`` · ``deja_pris``."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


async def brancher(organization_id: int, user_id: int, restaurant_id: int, etablissement_id: int, *, transport=None, saut_import: bool = False) -> dict[str, Any]:
    """Rend ``{point_de_vente, passif, import}``. Lève ``BranchementDeDemoRefuse``."""
    if not await garde.caisse_de_demo_permise(organization_id):
        raise BranchementDeDemoRefuse("non_permis")
    restaurant = await db_client.lire_restaurant_de_demo(organization_id, restaurant_id)
    if restaurant is None:
        raise BranchementDeDemoRefuse("restaurant_inconnu")
    nom_base = await rattachement.nom_de_la_base(organization_id)
    if not nom_base:
        raise BranchementDeDemoRefuse("base_absente")
    connexion = await base_client.connecter(nom_base)
    try:
        cle = await liaison_db.cle_du_site(connexion, etablissement_id)
        if cle is None:
            raise BranchementDeDemoRefuse("etablissement_inconnu")
        point_de_vente = restaurant["point_de_vente"]
        try:
            await db_client.lier_point_de_vente(organization_id, NOM, point_de_vente, cle, horloge(organization_id).maintenant())
        except PointDeVenteDejaPris:
            raise BranchementDeDemoRefuse("deja_pris") from None
        jeton = await restaurants.donner_un_jeton(organization_id, restaurant_id)
        donnees = {
            "token": jeton, "fournisseur": NOM, "point_de_vente": point_de_vente, "catalogue": catalogue_id_de(restaurant), "liste_clients": liste_de_clients_de(restaurant),
            "compte": point_de_vente.rsplit("-", 1)[0], "demo": True,
        }
        reference = await hl._ranger_le_jeton(organization_id, user_id, etablissement_id, await liaison_db.acces(connexion, etablissement_id), donnees)
        await liaison_db.poser_liaison(connexion, etablissement_id, NOM, point_de_vente, "ok", source="mark", auteur=f"branchement-demo:{user_id}")
        await liaison_db.poser_acces(connexion, etablissement_id, reference)
        client = hc.ClientHubrise(
            jeton, point_de_vente=point_de_vente, catalogue=donnees["catalogue"], liste_clients=donnees["liste_clients"], transport=transport, labo=True, base=adresse_de_la_caisse()
        )
        passif = await hl.s_abonner(client, connexion, etablissement_id)
        bilan = None
        if saut_import:
            await dire_la_liaison(connexion, organization_id, etablissement_id, "ok", synchro=True)
        else:
            prise = await hl._fabrique(ContexteDePrise(connexion, organization_id, etablissement_id, nom_base, transport))
            bilan = await importer_la_caisse(prise, connexion, organization_id, etablissement_id)
        await flux.emettre(organization_id, etablissement_id, "caisse.liaison", {"etat": "ok"})
    finally:
        await connexion.close()
    return {"point_de_vente": point_de_vente, "passif": passif, "import": bilan}


async def etablissement_du_restaurant(organization_id: int, restaurant: dict[str, Any]) -> str | None:
    """La clé de l'établissement que joue ce restaurant de test (celui auquel il est branché), ou ``None``."""
    lie = await db_client.retrouver_le_point_de_vente(NOM, restaurant["point_de_vente"])
    return lie["etablissement_cle"] if lie and lie["organization_id"] == organization_id else None


async def reservation_de_l_appel(organization_id: int, etablissement_id: int, appel_id: int) -> dict[str, Any] | None:
    """La réservation que CET essai (cette exécution) a faite dans CET établissement du Labo, ou ``None``. Rendue pour la fenêtre Caisse / POS : l'heure, les couverts, l'état,
    les tables. Jamais le prénom ni le numéro de l'appelant. L'établissement est relu contre la base de l'organisation (un identifiant d'ailleurs : ``None``)."""
    nom_base = await rattachement.nom_de_la_base(organization_id)
    if not nom_base:
        return None
    connexion = await base_client.connecter(nom_base)
    try:
        return await restauration_direct.reservation_de_l_appel(connexion, etablissement_id, str(appel_id))
    finally:
        await connexion.close()


async def debrancher(organization_id: int, restaurant_id: int) -> bool:
    """Coupe le lien de CE restaurant de test avec son établissement (le point de vente est libéré). Faux s'il n'était pas branché."""
    restaurant = await db_client.lire_restaurant_de_demo(organization_id, restaurant_id)
    if restaurant is None:
        return False
    cle = await etablissement_du_restaurant(organization_id, restaurant)
    if cle is None:
        return False
    await db_client.delier_le_point_de_vente(organization_id, NOM, cle)
    await db_client.modifier_restaurant_de_demo(organization_id, restaurant_id, {"jeton_empreinte": None, "callback_url": None}, horloge(organization_id).maintenant())
    nom_base = await rattachement.nom_de_la_base(organization_id)
    if nom_base:
        connexion = await base_client.connecter(nom_base)
        try:
            site = await liaison_db.site_par_cle(connexion, cle)
            if site is not None:
                await liaison_db.supprimer_la_liaison(connexion, site)
        finally:
            await connexion.close()
    return True


async def etablissements_du_labo(organization_id: int) -> list[dict[str, Any]]:
    """Les établissements de la base de l'organisation (celle du Labo) qu'un restaurant de test peut jouer : ``id``, ``cle``, ``nom``."""
    nom_base = await rattachement.nom_de_la_base(organization_id)
    if not nom_base:
        return []
    connexion = await base_client.connecter(nom_base)
    try:
        return [{"id": r["id"], "cle": r["cle"], "nom": r["nom"]} for r in await connexion.fetch("SELECT id, cle, nom FROM mark.site WHERE actif ORDER BY id")]
    finally:
        await connexion.close()
