"""[.mark] Lot 8b-1a (E3 ; décision d'Evan du 24/11, plan § 17) : la commande de l'appel part en caisse UNE fois, à la fin de l'appel.

Au « oui » de la relecture, l'agent a écrit la commande ``retenue`` (``enregistrer_commande``). Le crochet ``fin_de_l_appel`` de la restauration (voix : le ``finally`` ;
clavier : la fin de la partie ou le tour qui la finit) appelle ``envoyer_la_commande_de_l_appel`` :

- ce que l'appel a écrit se lit dans la base de SON organisation : les lignes ``retenue`` dont ``appel_id`` est cet appel ; aucune (un agent sans commande, une commande
  jamais accordée) : rien ne part. Jamais l'interrupteur du module (la fin est jouée pour tous les modules, audit 8a) ;
- la ligne dont le panier de la fiche finale est à l'étape « enregistrée » sous ce numéro est accordée : ``retenue → nouvelle``, puis ``commande.creee``, le SMS de
  confirmation et l'envoi (``envoyer_la_commande``, le geste unique) ; toute autre ligne ``retenue`` de l'appel : ``retenue → annulee`` (sans caisse) ;
- rejouée (deux fins, fiche ``None`` d'un montage tombé) : sans effet double, ``changer_statut`` ne laisse passer qu'un geste et une fiche illisible ne fait rien.

Sa propre connexion : la mémoire de l'appel peut être fermée ou balayée. ⛔ Ne lève jamais (R1) : un échec est au journal, la ligne reste ``retenue``.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from api.db.bases_clients import connexion as base_client
from api.db.bases_clients import restauration
from api.db.bases_clients.restauration_commande import commande_complete
from api.db.bases_clients.restauration_commun import fuseau_de
from api.services.base_client import rattachement
from api.services.commande import etape as ETAPE
from api.services.commande import panier as P
from api.services.restauration.appel_et_memoire import flux
from api.services.restauration.caisse.envoi_caisse import envoyer_la_commande
from api.services.restauration.envois_et_sms import envois

logger = logging.getLogger(__name__)  # le journal standard (repris par celui de l'application) : l'échec y est écrit avec sa pile


def numero_accorde(fiche: dict | None) -> str | None:
    """Le numéro de la commande que l'appel finit accordée (étape « enregistrée ») ; ``None`` : rien d'accordé, ou pas de commande dans la fiche."""
    if not isinstance(fiche, dict) or not isinstance(fiche.get(P.CLE), dict):
        return None
    p = P.du_dossier(fiche)
    numero = (p.get("enregistree") or {}).get("numero")
    return str(numero) if numero and ETAPE.courante(p) == ETAPE.ENREGISTREE else None


async def envoyer_la_commande_de_l_appel(organization_id: int | None, run_id: Any, fiche: dict | None) -> None:
    """Voir le module. Une fiche sans commande (``None``, ou sans panier) : la base n'est pas ouverte."""
    if not isinstance(fiche, dict) or not isinstance(fiche.get(P.CLE), dict) or not run_id:
        return
    if not organization_id:
        logger.error(f"[.mark] Call {run_id} ended without its organization: its retained order is not sent")
        return
    try:
        nom_base = await rattachement.nom_de_la_base(organization_id)
        if not nom_base:
            return
        c = await base_client.connecter(nom_base)
    except Exception:  # R1 : la fin de l'appel ne casse jamais ; la ligne reste « retenue »
        logger.exception(f"[.mark] Call {run_id}: no connection to send its order")
        return
    try:
        await envoyer_les_commandes_retenues(c, organization_id, nom_base, str(run_id), fiche)
    except Exception:  # R1 : au journal, avec sa pile ; la ligne restée « retenue » est visible en base
        logger.exception(f"[.mark] Call {run_id}: sending its order at the end failed")
    finally:
        await c.close()


async def envoyer_les_commandes_retenues(c: Any, organization_id: int | None, nom_base: str, appel_id: str, fiche: dict) -> None:
    """Sur la connexion donnée : chaque ligne ``retenue`` de l'appel ``appel_id`` part (celle que la fiche finit accordée) ou est annulée. Sans organisation
    (un essai) : ni portail ni SMS, comme pendant l'appel."""
    lignes = await c.fetch("SELECT numero::text AS numero, site_id FROM mark.resto_commande WHERE appel_id = $1 AND statut = 'retenue'", appel_id)
    accorde = numero_accorde(fiche)
    for ligne in lignes:
        if ligne["numero"] == accorde:
            await envoyer_la_commande_retenue(c, organization_id, nom_base, ligne["site_id"], ligne["numero"])
        else:
            await _annuler(c, ligne["site_id"], ligne["numero"])


async def _annuler(c: Any, etablissement_id: int, numero: str) -> None:
    """Jamais réaccordée : annulée sans caisse. Le portail n'en a jamais rien su (``commande.creee`` part avec l'envoi) : aucun événement."""
    await restauration.changer_statut(c, etablissement_id, numero, "retenue", "annulee", "agent")


async def envoyer_la_commande_retenue(c: Any, organization_id: int | None, nom_base: str, etablissement_id: int, numero: str) -> None:
    """Accordée : ``retenue → nouvelle``, puis ``commande.creee``, le SMS et l'envoi. Le geste de la fin de l'appel, et du filet du rattrapage (E11)."""
    if (await restauration.changer_statut(c, etablissement_id, numero, "retenue", "nouvelle", "agent")).statut != "OK":
        return  # une autre fin l'a déjà fait passer : un seul geste
    commande = await commande_complete(c, etablissement_id, numero)
    if commande is not None and organization_id is not None:
        await _dire_la_commande_creee(c, organization_id, etablissement_id, commande)
    await envoyer_la_commande(organization_id, nom_base, etablissement_id, numero, connexion=c)


async def _dire_la_commande_creee(c: Any, organization_id: int, etablissement_id: int, commande: dict) -> None:
    """Le portail l'apprend (``commande.creee``) et le client reçoit son SMS de confirmation, seulement si l'établissement l'a allumé (éteint par défaut, lot 7, E-18)."""
    heure_annoncee = commande.get("heure_annoncee")
    await flux.emettre(
        organization_id, etablissement_id, "commande.creee",
        {"numero": str(commande["numero"]), "numero_court": commande["numero_court"], "mode": commande["mode"], "heure_annoncee": heure_annoncee, "total": commande["total"]},
    )
    client = commande.get("client") or {}
    heure = heure_annoncee.astimezone(ZoneInfo(await fuseau_de(c, etablissement_id))).strftime("%H:%M") if isinstance(heure_annoncee, datetime) else ""
    await envois.envoyer_apres(
        c, organization_id, etablissement_id, envois.COMMANDE_ENREGISTREE, client.get("telephone"),
        {"prenom": client.get("prenom") or "", "numero_court": commande["numero_court"], "heure": heure, "quand": heure}, str(commande["numero"]),
    )
