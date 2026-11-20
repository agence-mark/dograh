"""[.mark] Module Restauration, lot 10 : le RATTRAPAGE, les alertes et la santé des liaisons (tâches planifiées de ``tasks/arq.py``).

Chaque tâche parcourt les bases clientes rattachées, une par une, puis les établissements, un par un ; l'échec de l'un n'arrête pas les autres et se voit
(journal, liaison, flux). Toutes sont rejouables sans effet double :

- ``rattrapage_des_envois`` (chaque minute) : une commande restée ``nouvelle`` ou ``envoyee`` dont l'envoi est à reprendre (reprise espacée) repart par
  ``envoyer_la_commande`` : la prise cherche par NOTRE numéro avant de renvoyer ;
- ``alerte_des_commandes_sans_reponse`` (chaque minute) : une commande que la caisse a reçue mais pas prise en charge depuis ``alerte_sans_reponse_min`` minutes
  (3 par défaut, réglable, T-09) prévient une personne, UNE fois par commande ;
- ``relecture_de_nuit`` (la nuit) : relecture complète de la carte, des ruptures et de l'état de chaque caisse (filet de tout ce qu'un message aurait manqué) ; une
  liaison rompue n'est pas relue (le jeton est refusé : on ne harcèle pas la caisse) ;
- les prises qui ne préviennent de rien (l'imprimante) sont interrogées par elles-mêmes : alertes de tickets (``tickets``).

La relève des messages gardés par la caisse (mode passif) est dans ``prises/hubrise_reception.py``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from api.db.bases_clients import connexion as base_client
from api.db.bases_clients import restauration, restauration_liaison as liaison_db
from api.db.bases_clients.restauration_commun import MODES, maintenant
from api.services.base_client.rattachement import organisations_rattachees
from api.services.restauration.envoi_caisse import Secours, _alerter, _secours_par_defaut, envoyer_la_commande
from api.services.restauration.prises.prise import ContexteDePrise, capacites_de, prise_de_l_etablissement
from api.services.restauration.synchro_caisse import importer_la_caisse

CLE_ALERTE = "mark:resto:sans-reponse:"


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


async def rattrapage_des_envois(_ctx=None, bases: list[tuple[int, str]] | None = None, *, transport: Any = None, secours: Secours | None = None) -> dict[str, Any]:
    async def travail(connexion, organization_id: int, nom_base: str) -> int:
        envoyees = 0
        for etablissement_id in await liaison_db.ids_des_sites(connexion):
            for numero in await liaison_db.commandes_a_reprendre(connexion, etablissement_id):
                await envoyer_la_commande(organization_id, nom_base, etablissement_id, numero, transport=transport, secours=secours, connexion=connexion)
                envoyees += 1
        return envoyees

    return await par_base(bases, travail)


async def liaisons_de_la_base(connexion) -> list[dict]:
    """Toutes les liaisons de la base (une ligne par établissement relié)."""
    sortie = []
    for etablissement_id in await liaison_db.ids_des_sites(connexion):
        liaison = await liaison_db.liaison(connexion, etablissement_id)
        if liaison is not None:
            sortie.append({"etablissement_id": etablissement_id, **liaison})
    return sortie


async def alerte_des_commandes_sans_reponse(_ctx=None, bases: list[tuple[int, str]] | None = None, *, secours: Secours | None = None) -> dict[str, Any]:
    secours = secours or _secours_par_defaut

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
                    await _alerter(connexion, organization_id, etab, c["numero"], secours, f"restée nouvelle depuis {minutes} minutes", nouvelle_depuis_min=minutes)
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
