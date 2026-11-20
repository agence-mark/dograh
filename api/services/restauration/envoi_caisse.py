"""[.mark] Module Restauration, lot 10 : l'ENVOI d'une commande enregistrée vers la prise de son établissement, en tâche de fond, avec le secours.

``envoyer_la_commande`` est le geste unique : l'appel qui vient d'enregistrer la commande le lance en fond (``source_commande``), le rattrapage le reprend
(``rattrapage``). Il construit la prise de CET établissement (son accès, jamais celui d'un autre), envoie par ``envoyer_une_commande`` (qui cherche par NOTRE
numéro avant tout renvoi : jamais deux commandes), écrit ``ref_fournisseur`` et dit au flux ce qui a changé.

Ce que la caisse répond ne se dit jamais au client (E-36) : l'agent a déjà dit « c'est enregistré ». Quand l'envoi n'aboutit PAS, une personne doit le savoir :

- la caisse REFUSE la commande (restaurant fermé, prix différent…) : secours tout de suite ;
- la caisse ne répond pas : la reprise est espacée (``commandes_a_reprendre``) ; au ``TENTATIVES_MAX``-ième essai raté, la commande passe en ``echec`` (définitif) et le
  secours part. Le secours = un message aux adresses de notification de l'organisation et de .mark (``notifier``, qui ne lève jamais), avec la commande jointe
  (numéro court, mode, heure, lignes, total, téléphone). Le routage de l'appel vers un humain relève de la téléphonie : non fait ici.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from api.db.bases_clients import connexion as base_client
from api.db.bases_clients import restauration
from api.db.bases_clients import restauration_liaison as liaison_db
from api.db.bases_clients.restauration_commande import commande_complete
from api.db.bases_clients.restauration_commun import Connexion
from api.services.base_client.rattachement import organisations_rattachees
from api.services.restauration import flux
from api.services.restauration.heure_caisse import prevenir_l_appelant
from api.services.restauration.prises.envoi import EnvoiApplique, envoyer_une_commande
from api.services.restauration.prises.prise import (
    ContexteDePrise,
    prise_de_l_etablissement,
)
from api.services.restauration.secours import secours_de_la_commande

TENTATIVES_MAX = 5
Secours = Callable[[int | None, str, str], Awaitable[Any]]


async def organisation_de_la_base(nom_base: str) -> int | None:
    for organisation, nom in await organisations_rattachees():
        if nom == nom_base:
            return organisation
    return None


def _euros(centimes: int) -> str:
    return f"{centimes // 100},{centimes % 100:02d} €"


def texte_du_secours(commande: dict, raison: str) -> tuple[str, str]:
    """Le sujet et le texte du secours : la commande est jointe pour qu'une personne la saisisse à la main."""
    court = commande.get("numero_court") or str(commande["numero"])[:8]
    lignes = "\n".join(f"  {l['quantite']} x {l['nom']}" + (f" ({l['note']})" if l.get("note") else "") for l in commande.get("lignes") or [])
    heure = commande.get("heure_annoncee")
    corps = (
        f"La commande {court} n'a pas pu être transmise à la caisse ({raison}). Elle est enregistrée ; il faut la saisir à la main.\n"
        f"Order {court} could not be sent to the till ({raison}). It is saved; please enter it by hand.\n\n"
        f"Mode : {commande['mode']}\nHeure annoncée : {heure.strftime('%d/%m %H:%M') if heure else 'dès que possible'}\n"
        f"Téléphone : {(commande.get('client') or {}).get('telephone') or '-'}\nTotal : {_euros(commande['total'])}\n\n{lignes}\n"
    )
    if commande.get("note"):
        corps += f"\nNote : {commande['note']}\n"
    return f"Commande {court} non transmise à la caisse / not sent to the till", corps


async def _secours_par_defaut(organization_id: int | None, sujet: str, texte: str) -> Any:
    from api.services.apres_appel.notification import notifier

    return await notifier(organization_id, sujet, texte)


async def _dire(connexion, organization_id: int | None, etablissement_id: int, numero: str, avant: str | None, apres: str | None) -> None:
    if organization_id is not None and avant and apres and avant != apres:
        await flux.emettre(organization_id, etablissement_id, "commande.statut", {"numero": numero, "de": avant, "vers": apres, "source": "agent"})


async def envoyer_la_commande(
    organization_id: int | None, nom_base: str, etablissement_id: int, numero: str | uuid.UUID, *, transport: Any = None, secours: Secours | None = None,
    connexion: Connexion | None = None,
) -> EnvoiApplique | None:
    """Envoie (ou reprend l'envoi de) UNE commande de CET établissement. Ne lève jamais (R1 : l'échec se voit au journal, au flux et par le secours)."""
    secours = secours or _secours_par_defaut
    propre = connexion is None
    try:
        c = connexion or await base_client.connecter(nom_base)
    except Exception as erreur:  # noqa: BLE001
        logger.error(f"[.mark] Order {numero}: no connection to send it: {type(erreur).__name__}")
        return None
    try:
        numero_s = str(numero)
        avant = await liaison_db.etat_de_la_commande(c, etablissement_id, numero_s)
        if avant is None:
            return None  # pas une commande de cet établissement
        prise = await prise_de_l_etablissement(ContexteDePrise(c, organization_id, etablissement_id, nom_base, transport))
        issue = await envoyer_une_commande(c, etablissement_id, prise, numero_s)
        apres = await liaison_db.etat_de_la_commande(c, etablissement_id, numero_s)
        await _dire(c, organization_id, etablissement_id, numero_s, avant["statut"], apres["statut"] if apres else None)
        if apres and apres["heure_annoncee"] is not None and apres["heure_annoncee"] != avant["heure_annoncee"]:
            # La caisse a répondu avec SON heure (temps de préparation allongé) : le classeur l'a reprise (``envoi``), le flux et l'appelant le savent.
            if organization_id is not None:
                await flux.emettre(organization_id, etablissement_id, "commande.heure", {"numero": numero_s, "heure_annoncee": apres["heure_annoncee"]})
            await prevenir_l_appelant(c, organization_id, etablissement_id, numero_s, apres["heure_annoncee"])
        if issue.ecart_de_total is not None:
            await _prevenir_d_un_ecart_de_total(c, organization_id, etablissement_id, numero_s, secours, *issue.ecart_de_total)
        if issue.issue == "refusee":
            await _alerter(c, organization_id, etablissement_id, numero_s, secours, f"refus de la caisse : {issue.resultat.raison if issue.resultat else 'autre'}")
        elif issue.issue == "echec_code":
            # Lot 16 : une erreur de NOTRE code : alerte tout de suite au restaurant et à .mark, sans les cinq essais d'une panne de caisse
            if organization_id is not None:
                await flux.emettre(organization_id, etablissement_id, "commande.statut", {"numero": numero_s, "de": "envoyee", "vers": "echec", "source": "agent"})
            await _alerter(c, organization_id, etablissement_id, numero_s, secours, "erreur de .mark, pas de la caisse")
        elif issue.issue == "a_reprendre":
            essais = await liaison_db.compter_un_essai_rate(c, etablissement_id, numero_s, ajouter=avant["statut"] == "envoyee")
            if essais >= TENTATIVES_MAX:
                pas = await restauration.changer_statut(c, etablissement_id, numero_s, "envoyee", "echec", "mark")
                if pas.statut == "OK":
                    await liaison_db.marquer_la_cause_de_l_echec(c, etablissement_id, numero_s, "caisse")
                if pas.statut == "OK" and organization_id is not None:
                    await flux.emettre(organization_id, etablissement_id, "commande.statut", {"numero": numero_s, "de": "envoyee", "vers": "echec", "source": "agent"})
                await _alerter(c, organization_id, etablissement_id, numero_s, secours, "la caisse ne répond pas")
        return issue
    except Exception as erreur:  # noqa: BLE001 -- R1 : une commande jamais perdue : elle reste à reprendre, l'échec est au journal
        logger.error(f"[.mark] Order {numero}: the send failed: {type(erreur).__name__}")
        return None
    finally:
        if propre:
            await c.close()


def texte_de_la_commande_restee_nouvelle(commande: dict, minutes: int) -> tuple[str, str]:
    """Lot 16 : le sujet et le texte quand la commande est ARRIVÉE à la caisse mais que personne ne l'a prise en charge au bout de ``minutes`` minutes (la commande est enregistrée)."""
    court = commande.get("numero_court") or str(commande["numero"])[:8]
    corps = (
        f"La commande {court} est arrivée à la caisse mais personne ne l'a prise en charge depuis {minutes} minutes. Vérifiez la caisse.\n"
        f"Order {court} reached the till but nobody has accepted it for {minutes} minutes. Please check the till.\n\n"
        f"Téléphone : {(commande.get('client') or {}).get('telephone') or '-'}\nTotal : {_euros(commande['total'])}\n"
    )
    return f"Commande {court} sans réponse de la caisse / no answer from the till", corps


def texte_de_l_ecart_de_total(commande: dict, notre_total: int, total_caisse: int) -> tuple[str, str]:
    """Lot 19 bis (K4) : la commande EST en caisse, mais la caisse a compté un autre total que celui annoncé au client ; une personne doit vérifier avant la préparation."""
    court = commande.get("numero_court") or str(commande["numero"])[:8]
    corps = (
        f"La commande {court} est bien arrivée à la caisse, mais la caisse a compté {_euros(total_caisse)} au lieu des {_euros(notre_total)} annoncés au client. Vérifiez le montant.\n"
        f"Order {court} reached the till, but the till counted {_euros(total_caisse)} instead of the {_euros(notre_total)} told to the customer. Please check the amount.\n\n"
        f"Téléphone : {(commande.get('client') or {}).get('telephone') or '-'}\n"
    )
    return f"Commande {court} : total différent en caisse / till total differs", corps


async def _prevenir_d_un_ecart_de_total(connexion, organization_id: int | None, etablissement_id: int, numero: str, secours: Secours, notre_total: int, total_caisse: int) -> None:
    """Un message au restaurant (un seul), sans l'échelle de secours : la commande n'est pas perdue, c'est son montant qu'il faut vérifier. Ne lève jamais."""
    try:
        commande = await commande_complete(connexion, etablissement_id, numero)
        if commande is None:
            return
        sujet, texte = texte_de_l_ecart_de_total(commande, notre_total, total_caisse)
        await secours(organization_id, sujet, texte)
    except Exception as erreur:  # noqa: BLE001 -- dire un écart ne doit pas en faire une panne
        logger.error(f"[.mark] Order {numero}: the total difference message failed: {type(erreur).__name__}")


async def _alerter(connexion, organization_id: int | None, etablissement_id: int, numero: str, secours: Secours, raison: str, *, nouvelle_depuis_min: int | None = None) -> None:
    commande = await commande_complete(connexion, etablissement_id, numero)
    if commande is None:
        return
    sujet, texte = texte_du_secours(commande, raison) if nouvelle_depuis_min is None else texte_de_la_commande_restee_nouvelle(commande, nouvelle_depuis_min)
    # L'échelle de Pierre (note HubRise § 10) : ticket sur l'imprimante liée, SMS au gérant, (appel : non fait) ; le mail ci-dessous part en plus.
    bilan = await secours_de_la_commande(connexion, organization_id, etablissement_id, commande, raison, nouvelle=nouvelle_depuis_min is not None)
    logger.info(f"[.mark] Order {numero}: rescue ladder {bilan}")
    try:
        await secours(organization_id, sujet, texte)
    except Exception as erreur:  # noqa: BLE001 -- dire une panne ne doit pas en faire une seconde
        logger.error(f"[.mark] Order {numero}: the rescue message failed: {type(erreur).__name__}")
