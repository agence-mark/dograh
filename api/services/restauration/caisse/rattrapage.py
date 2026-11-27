"""[.mark] Module Restauration, lot 10 : le RATTRAPAGE, les alertes et la santé des liaisons (tâches planifiées de ``tasks/arq.py``).

Chaque tâche parcourt les bases clientes rattachées, une par une, puis les établissements, un par un ; l'échec de l'un n'arrête pas les autres et se voit
(journal, liaison, flux). Toutes sont rejouables sans effet double :

- ``rattrapage_des_envois`` (chaque minute) : une commande restée ``nouvelle`` ou ``envoyee`` dont l'envoi est à reprendre (reprise espacée) repart par
  ``envoyer_la_commande`` : la prise cherche par NOTRE numéro avant de renvoyer ; filet (lot 8b-1a, E11 ; lot 8b-1b, T24) : une commande ``retenue`` dont la fin de
  l'appel n'a pas été jouée (serveur redémarré) part comme à la fin de l'appel, après le délai réglé du module (``filet_retenue_min``), dès que son appel est noté terminé
  OU ne peut plus être en cours (un appel planté n'est jamais noté terminé) ; une ligne qui ne peut vraiment pas partir alerte le restaurant une fois ;
- ``alerte_des_commandes_sans_reponse`` (chaque minute) : une commande que la caisse a reçue mais pas prise en charge depuis ``alerte_sans_reponse_min`` minutes
  (réglable, T-09), ou dès l'heure promise moins la marge ``MARGE_AVANT_L_HEURE`` si elle vient avant, prévient une personne, UNE fois par commande ;
- ``relecture_de_nuit`` (la nuit) : relecture complète de la carte, des ruptures et de l'état de chaque caisse (filet de tout ce qu'un message aurait manqué) ; une
  liaison rompue n'est pas relue (le jeton est refusé : on ne harcèle pas la caisse) ;
- les prises qui ne préviennent de rien (l'imprimante) sont interrogées par elles-mêmes : alertes de tickets (``tickets``).

La relève des messages gardés par la caisse (mode passif) est dans ``prises/hubrise_reception.py``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

import asyncpg
from loguru import logger

from api.db.bases_clients import connexion as base_client
from api.db.bases_clients import restauration, restauration_liaison as liaison_db
from api.db.bases_clients.restauration_commun import MODES, maintenant
from api.db.bases_clients.restauration_reglage import reglages_du_module
from api.services.base_client.rattachement import organisations_rattachees
from api.constants import TEXT_CHAT_INACTIVITY_SWEEP_LOOKBACK_SECONDS
from api.schemas.workflow_configurations import MAX_CALL_DURATION_SECONDS
from api.services.restauration.appel_et_memoire.memoire_de_l_appel import EtatDeLAppel, etats_des_appels_en_base
from api.services.restauration.caisse.envoi_a_la_fin import envoyer_la_commande_retenue
from api.services.restauration.caisse.envoi_caisse import Secours, alerter, secours_par_defaut, envoyer_la_commande
from api.services.restauration.caisse.prises.prise import ContexteDePrise, capacites_de, prise_de_l_etablissement
from api.services.restauration.caisse.synchro_caisse import importer_la_caisse

CLE_ALERTE = "mark:resto:sans-reponse:"
# Lot 8b-1b (T24 (1)) : un appel à la voix ne dure jamais plus que le plafond de la plateforme ; passé ce temps après le dernier « oui », il est fini, noté ou non.
PLUS_LONG_APPEL_A_LA_VOIX = timedelta(seconds=MAX_CALL_DURATION_SECONDS)
# Au-delà, plus rien ne fermera l'appel (le balayage des parties au clavier ne remonte pas plus loin) : la ligne ne peut vraiment pas partir seule.
LIMITE_DU_FILET = timedelta(seconds=TEXT_CHAT_INACTIVITY_SWEEP_LOOKBACK_SECONDS)
RAISON_ACCORD_RETIRE = "commande retenue dont le client a retiré son accord (allergie dite après le oui) : elle n'est pas envoyée, à vérifier avec le client"
RAISON_DU_FILET = "commande retenue d'un appel qui n'a jamais fini : à vérifier, à saisir à la main si le client l'attend"
EtatsDesAppels = Callable[[list[str]], Awaitable["dict[str, EtatDeLAppel] | None"]]


async def par_base(bases: list[tuple[int, str]] | None, travail: Callable[[Any, int, str], Awaitable[Any]]) -> dict[str, Any]:
    """Joue ``travail(connexion, organisation, nom_base)`` sur chaque base rattachée. L'échec d'une base n'arrête pas les autres."""
    sortie: dict[str, Any] = {}
    for organization_id, nom_base in bases if bases is not None else await organisations_rattachees():
        try:
            connexion = await base_client.connecter(nom_base)
        except Exception as erreur:  # noqa: BLE001
            logger.error(f"[.mark] Restaurant catch-up: no connection for organization {organization_id}: {type(erreur).__name__}")
            sortie[str(organization_id)] = {"erreur": "base_injoignable"}
            continue
        try:
            sortie[str(organization_id)] = await travail(connexion, organization_id, nom_base)
        except Exception as erreur:  # noqa: BLE001 -- rejouée au prochain passage, sans effet double
            logger.error(f"[.mark] Restaurant catch-up failed for organization {organization_id}: {type(erreur).__name__}")
            sortie[str(organization_id)] = {"erreur": type(erreur).__name__}
        finally:
            await connexion.close()
    return sortie


async def rattrapage_des_envois(
    _ctx=None, bases: list[tuple[int, str]] | None = None, *, transport: Any = None, secours: Secours | None = None,
    etats_des_appels: EtatsDesAppels = etats_des_appels_en_base,
) -> dict[str, Any]:
    async def travail(connexion, organization_id: int, nom_base: str) -> int:
        envoyees = 0
        for etablissement_id in await liaison_db.ids_des_sites(connexion):
            envoyees += await _partir_les_retenues_des_appels_finis(connexion, organization_id, nom_base, etablissement_id, etats_des_appels, secours or secours_par_defaut)
            for numero in await liaison_db.commandes_a_reprendre(connexion, etablissement_id):
                await envoyer_la_commande(organization_id, nom_base, etablissement_id, numero, transport=transport, secours=secours, connexion=connexion)
                envoyees += 1
            await _reprendre_les_annulations(connexion, organization_id, nom_base, etablissement_id, transport, secours)
        return envoyees

    return await par_base(bases, travail)


async def _partir_les_retenues_des_appels_finis(
    connexion, organization_id: int, nom_base: str, etablissement_id: int, etats_des_appels: EtatsDesAppels, secours: Secours
) -> int:
    """E11, T24 (1) : le panier de l'appel n'est plus lisible : la ligne telle qu'écrite au dernier « oui » (ou réécrite par un changement) part (§ 17 : appel coupé après
    l'accord, elle part). L'état des appels de chaque page se lit en UNE requête ; une lecture ratée ne décide rien (rejouée au passage suivant). Rejouable sans effet
    double (``changer_statut`` ne laisse passer qu'un geste, l'alerte ne se pose qu'une fois)."""
    delai = (await reglages_du_module(connexion, etablissement_id))["filet_retenue_min"]
    moment = await maintenant(connexion)
    parties, apres = 0, None
    while page := await liaison_db.commandes_retenues_a_reprendre(connexion, etablissement_id, jusqu_a=moment - timedelta(minutes=delai), apres=apres):
        etats = await etats_des_appels([appel_id for _, appel_id, _ in page])
        if etats is None:
            break
        for numero, appel_id, maj_le in page:
            parties += await _une_retenue(connexion, organization_id, nom_base, etablissement_id, numero, maj_le, etats.get(appel_id), moment, secours)
        apres = (page[-1][2], page[-1][0])
    return parties


def appel_fini(etat: EtatDeLAppel | None, dernier_oui: datetime, moment: datetime) -> bool:
    """L'appel est-il fini ? Noté terminé ; ou, à la voix, plus long que tout appel depuis le dernier « oui » (planté sans être noté). Au clavier, le balayage des parties
    inactives le note terminé. Inconnu : non. Un appel peut-être encore en cours n'est jamais pris pour fini (§ 17 : rien ne part pendant l'appel)."""
    return etat is not None and (etat.termine or (not etat.au_clavier and dernier_oui <= moment - PLUS_LONG_APPEL_A_LA_VOIX))


async def _une_retenue(
    connexion, organization_id: int, nom_base: str, etablissement_id: int, numero: str, maj_le: datetime, etat: EtatDeLAppel | None, moment: datetime, secours: Secours
) -> int:
    """Une ligne de la page : elle part si son appel est fini ; sinon, au-delà de la limite du filet, le restaurant est alerté une fois (la commande jointe) et le filet la
    laisse (ni annulée ni envoyée à l'aveugle ; la fin de l'appel, si elle arrive, l'envoie encore). La marque (un seul passage alerte) et l'alerte vont dans UNE transaction :
    une alerte qui lève défait la marque, le passage suivant la redit. Rend 1 si elle part."""
    if appel_fini(etat, maj_le, moment):
        if await liaison_db.accord_retire(connexion, etablissement_id, numero):
            return await _ne_pas_envoyer_une_retenue_sans_accord(connexion, organization_id, etablissement_id, numero, secours)
        logger.warning(f"[.mark] Order {numero}: its call ended without its end hook, the catch-up sends it")
        await envoyer_la_commande_retenue(connexion, organization_id, nom_base, etablissement_id, numero)
        return 1
    if maj_le > moment - LIMITE_DU_FILET:
        return 0
    async with connexion.transaction():
        if await liaison_db.marquer_l_alerte_du_filet(connexion, etablissement_id, numero):
            logger.error(f"[.mark] Order {numero}: retained, its call never ended, the restaurant is alerted")
            await alerter(connexion, organization_id, etablissement_id, numero, secours, RAISON_DU_FILET)
    return 0


async def _ne_pas_envoyer_une_retenue_sans_accord(connexion, organization_id: int, etablissement_id: int, numero: str, secours: Secours) -> int:
    """Lot 8b-3 (T35) : l'accord de cette ligne a été retiré (allergie dite après le « oui ») et son annulation n'a pas abouti : le filet ne l'envoie jamais sans nouveau « oui ». Il
    alerte le restaurant UNE fois (la marque et l'alerte vont dans UNE transaction, comme la limite du filet), puis passe la ligne à « annulée » ; une annulation qui échoue encore
    est journalisée ; la ligne reste ``retenue`` et marquée, alertée, hors de la lecture du filet : elle ne part jamais, le restaurant la voit. Le client n'entend rien de
    neuf. Rend 0 : rien ne part."""
    async with connexion.transaction():
        if await liaison_db.marquer_l_alerte_du_filet(connexion, etablissement_id, numero):
            logger.error(f"[.mark] Order {numero}: its agreement was withdrawn and its cancellation failed, the catch-up does not send it, the restaurant is alerted")
            await alerter(connexion, organization_id, etablissement_id, numero, secours, RAISON_ACCORD_RETIRE)
    try:
        await restauration.changer_statut(connexion, etablissement_id, numero, "retenue", "annulee", "agent")
    except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError):  # R1 : jamais envoyée ; la marque et l'alerte la gardent hors d'envoi
        logger.exception(f"[.mark] Order {numero}: the catch-up could not cancel a line whose agreement was withdrawn")
    return 0


async def _reprendre_les_annulations(connexion, organization_id: int, nom_base: str, etablissement_id: int, transport: Any, secours: Secours | None) -> None:
    """Lot 19 bis (K5) : les annulations que la caisse n'a pas encore reçues sont redites (espacées), alerte au 5e essai raté. Rejouable sans effet double."""
    from api.services.restauration.caisse.annulation_caisse import dire_l_annulation

    numeros = await liaison_db.annulations_a_reprendre(connexion, etablissement_id)
    if not numeros:
        return
    prise = await prise_de_l_etablissement(ContexteDePrise(connexion, organization_id, etablissement_id, nom_base, transport))
    for numero in numeros:
        await dire_l_annulation(connexion, organization_id, etablissement_id, prise, numero, secours=secours)


async def liaisons_de_la_base(connexion) -> list[dict]:
    """Toutes les liaisons de la base (une ligne par établissement relié)."""
    sortie = []
    for etablissement_id in await liaison_db.ids_des_sites(connexion):
        liaison = await liaison_db.liaison(connexion, etablissement_id)
        if liaison is not None:
            sortie.append({"etablissement_id": etablissement_id, **liaison})
    return sortie


async def alerte_des_commandes_sans_reponse(_ctx=None, bases: list[tuple[int, str]] | None = None, *, secours: Secours | None = None) -> dict[str, Any]:
    secours = secours or secours_par_defaut

    async def travail(connexion, organization_id: int, nom_base: str) -> int:
        alertes = 0
        for liaison in await liaisons_de_la_base(connexion):
            if "acceptee" not in capacites_de(liaison["prise"]).etapes:
                continue  # une prise qui ne dit jamais « acceptée » (imprimante) n'a pas de « sans réponse » : l'outil dit TRANSMISE
            etab, minutes = liaison["etablissement_id"], liaison["alerte_sans_reponse_min"]
            if not await _ouvert_maintenant(connexion, etab):
                continue  # la documentation HubRise : « cinq minutes pendant les heures d'ouverture » ; fermé, personne n'est là pour accepter
            for c in await liaison_db.commandes_sans_reponse(connexion, etab, depuis_minutes=minutes):
                # Une seule alerte par commande, rejouable sans effet double : l'heure de l'alerte est posée par la seule requête qui la pose (``alerte_nouvelle_le``) ;
                # l'échelle de secours existante (ticket, SMS au gérant, mail ; l'appel au restaurant reste « non fait ») prévient une personne.
                if await liaison_db.marquer_l_alerte_nouvelle(connexion, etab, c["numero"]):
                    alertes += 1
                    await alerter(connexion, organization_id, etab, c["numero"], secours, f"restée nouvelle depuis {c['minutes']} minutes", nouvelle_depuis_min=c["minutes"], delai_min=minutes)
        return alertes

    return await par_base(bases, travail)


async def _ouvert_maintenant(connexion, etablissement_id: int) -> bool:
    """Vrai si l'établissement est ouvert à l'heure de la source d'heure (D6) pour au moins un type de commande : horaires, fermeture exceptionnelle, forçage, pause."""
    moment = await maintenant(connexion)
    for type_ in sorted(MODES):
        if (await restauration.etat_combine(connexion, etablissement_id, type_, moment))["ouvert"]:
            return True
    return False


async def relecture_de_nuit(_ctx=None, bases: list[tuple[int, str]] | None = None, *, transport: Any = None) -> dict[str, Any]:
    async def travail(connexion, organization_id: int, nom_base: str) -> dict[str, Any]:
        bilans: dict[str, Any] = {}
        for liaison in await liaisons_de_la_base(connexion):
            if liaison["etat"] in ("aucune", "rompue"):
                continue
            etab = liaison["etablissement_id"]
            prise = await prise_de_l_etablissement(ContexteDePrise(connexion, organization_id, etab, nom_base, transport))
            c = prise.capacites
            if c.carte != "lue" and c.ruptures != "lues" and not c.lit_l_etat:
                continue  # une prise qui n'a rien à relire (imprimante)
            bilans[str(etab)] = await importer_la_caisse(prise, connexion, organization_id, etab)
        return bilans

    return await par_base(bases, travail)
