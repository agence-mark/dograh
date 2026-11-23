"""[.mark] Module Restauration, lot 3 : l'ENVOI d'une commande enregistrée vers sa prise (le branchement du contrat).

``enregistrer_commande(..., declencher_envoi=)`` appelle, APRÈS l'enregistrement validé, une fonction qui ne reçoit que le
numéro. ``declencheur_vers_la_prise`` la fabrique : elle relit la commande dans le classeur (de CET établissement), l'envoie à
la prise, et fait avancer le statut par le chemin fermé (``changer_statut``). Rejouable sans effet double : une commande déjà
au-delà de ``nouvelle``/``envoyee`` n'est pas renvoyée ; avant un renvoi, une prise qui le permet est interrogée par NOTRE
numéro (``chercher_avant_renvoi``). Un échec ne casse jamais l'enregistrement : il s'écrit au journal d'erreur, la commande reste
``envoyee``/``nouvelle`` et le rattrapage (lot 10) la reprend. Les lots 9 et 10 posent leur file de tâches autour de ce geste.
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from loguru import logger

from api.db.bases_clients import restauration
from api.db.bases_clients.restauration_commande import commande_complete
from api.db.bases_clients.restauration_commun import Connexion
from api.db.bases_clients.restauration_liaison import (
    garder_le_motif_du_refus,
    marquer_la_cause_de_l_echec,
    poser_l_heure_annoncee,
    poser_ref_fournisseur,
)
from api.services.restauration.caisse.prises import adaptation
from api.services.restauration.caisse.prises.prise import GesteNonPermis, Prise, ResultatEnvoi

SOURCE = "mark"
# Étape renvoyée par la prise -> statut du chemin fermé (contrat § 3). ``imprimee`` : le ticket est sorti, la suite se lit au
# journal du ticket (lot 10). ``inconnu`` : la commande reste ``envoyee``.
STATUT_DE_L_ETAPE = {
    "recue": "recue", "imprimee": "recue", "acceptee": "acceptee", "en_preparation": "en_preparation", "prete": "prete",
    "terminee": "terminee", "refusee": "refusee", "annulee": "annulee",
}


@dataclass(frozen=True)
class EnvoiApplique:
    """Ce qui s'est passé : ``fait`` (rien à faire), ``envoyee``, ``refusee``, ``a_reprendre`` (panne)."""

    issue: str
    statut: str | None  # le statut du classeur après l'envoi
    pour_l_outil: str | None  # ``TRANSMISE`` ou ``OK`` (adaptation) ; ``None`` si rien n'a été envoyé
    resultat: ResultatEnvoi | None = None
    renvoi_evite: bool = False  # la prise connaissait déjà la commande (recherche par notre numéro)
    ecart_de_total: tuple[int, int] | None = None  # (notre total, celui de la caisse) en centimes, quand ils diffèrent après l'envoi (lot 19 bis, K4)


async def envoyer_une_commande(connexion: Connexion, etablissement_id: int, prise: Prise, numero: str | uuid.UUID) -> EnvoiApplique:
    commande = await commande_complete(connexion, etablissement_id, numero)
    if commande is None:
        return EnvoiApplique("fait", None, None)  # pas une commande de cet établissement : rien
    statut = commande["statut"]
    if commande["cree_par"] == "caisse":
        return EnvoiApplique("fait", statut, None)  # lot 26 (M10) : une commande créée dans la caisse n'est JAMAIS renvoyée à la caisse
    if statut not in ("nouvelle", "envoyee"):
        return EnvoiApplique("fait", statut, None)
    numero_s = commande["numero"]
    if statut == "nouvelle":
        passe = await restauration.changer_statut(connexion, etablissement_id, numero_s, "nouvelle", "envoyee", SOURCE)
        if passe.statut == "DEJA_FAIT":
            # Revue de clôture (1) : un autre travail vient de faire ce passage et envoie déjà la commande ; seul celui qui obtient
            # « OK » envoie, jamais deux commandes en cuisine.
            return EnvoiApplique("fait", "envoyee", None)
        if passe.statut != "OK":
            return EnvoiApplique("fait", passe.faits.get("statut_actuel"), None)
    elif adaptation.doit_chercher_avant_renvoi(prise.capacites):
        # Un renvoi : la prise a peut-être déjà la commande (envoi parti, réponse perdue). On la cherche par notre numéro.
        try:
            connue = await prise.chercher_commande(numero_s)
        except GesteNonPermis:
            connue = None
        except Exception as erreur:  # noqa: BLE001 -- lot 19 bis (K1) : une caisse qui ne répond pas à la recherche est une panne : l'essai est compté, jamais retenté sans fin ni sans alerte
            logger.error(f"[.mark] Order {numero_s}: looking the order up in the {prise.nom} socket failed: {type(erreur).__name__}")
            return EnvoiApplique("a_reprendre", "envoyee", None, ResultatEnvoi("INDISPONIBLE", raison="caisse_injoignable"))
        if connue is not None:
            resultat = ResultatEnvoi("ENVOYEE", etape=connue.get("etape"), ref_fournisseur=connue.get("ref_fournisseur"), motif=connue.get("motif_de_la_caisse"))
            return await _appliquer(connexion, etablissement_id, prise, numero_s, "envoyee", resultat, True)
    try:
        resultat = await prise.envoyer_commande(commande)
    except json.JSONDecodeError as erreur:  # une réponse illisible de la caisse est une panne de la caisse, pas une erreur de notre code
        logger.error(f"[.mark] Order {numero_s}: the {prise.nom} socket sent an unreadable answer: {erreur!r}")
        return EnvoiApplique("a_reprendre", "envoyee", None, ResultatEnvoi("INDISPONIBLE", raison="caisse_injoignable"))
    except ERREURS_DE_NOTRE_CODE as erreur:
        return await _echec_de_notre_code(connexion, etablissement_id, numero_s, prise, erreur)
    except Exception as erreur:  # noqa: BLE001 -- une prise qui lève est une panne : on le voit, on reprend
        logger.error(f"[.mark] Order {numero_s}: sending to the {prise.nom} socket failed: {erreur!r}")
        return EnvoiApplique("a_reprendre", "envoyee", None, ResultatEnvoi("INDISPONIBLE", raison="caisse_injoignable"))
    applique = await _appliquer(connexion, etablissement_id, prise, numero_s, "envoyee", resultat, False)
    return _avec_l_ecart_de_total(applique, commande["total"], resultat)


def _avec_l_ecart_de_total(applique: EnvoiApplique, notre_total: int, resultat: ResultatEnvoi) -> EnvoiApplique:
    """Lot 19 bis (K4) : le total que la caisse a compté diffère du nôtre (elle arrondit, ou calcule les options autrement) : on le dit, on ne renvoie rien. Seul ``total`` est lu (``total_discrepancy`` est déprécié)."""
    if resultat.statut != "ENVOYEE" or resultat.total_caisse is None or resultat.total_caisse == notre_total:
        return applique
    return dataclasses.replace(applique, ecart_de_total=(notre_total, resultat.total_caisse))


# Lot 16 (audit caisse § 3.4 : cinq commandes du 17/11 perdues, un ``AttributeError`` de la traduction pris pour une panne) : ce qui se lève de NOTRE code (traduction impossible, attribut,
# clé, type, valeur) n'est JAMAIS une panne de la caisse : la rejouer cinq fois ne servirait à rien. Les pannes de réseau (``OSError``, délai, ``httpx``) ne sont pas dans cette liste.
ERREURS_DE_NOTRE_CODE = (AttributeError, KeyError, TypeError, ValueError, IndexError, AssertionError, NotImplementedError)


async def _echec_de_notre_code(connexion, etablissement_id: int, numero: str, prise: Prise, erreur: Exception) -> EnvoiApplique:
    """Une erreur de notre code : la commande passe tout de suite en ``echec`` (cause ``code``, aucune nouvelle tentative), le type de l'erreur au journal (jamais son texte à l'écran)."""
    logger.error(f"[.mark] Order {numero}: a code error (not a {prise.nom} failure) stopped the sending: {type(erreur).__name__}")
    pas = await restauration.changer_statut(connexion, etablissement_id, numero, "envoyee", "echec", SOURCE)
    statut = "echec" if pas.statut in ("OK", "DEJA_FAIT") else pas.faits.get("statut_actuel", "envoyee")
    if statut == "echec":
        await marquer_la_cause_de_l_echec(connexion, etablissement_id, numero, "code")
    return EnvoiApplique("echec_code", statut, None, ResultatEnvoi("INDISPONIBLE", raison="erreur_de_code"))


async def _appliquer(connexion, etablissement_id, prise: Prise, numero: str, depart: str, resultat: ResultatEnvoi, renvoi_evite: bool) -> EnvoiApplique:
    if resultat.statut == "INDISPONIBLE":
        logger.warning(f"[.mark] Order {numero}: the {prise.nom} socket is unavailable, order left to retry")
        return EnvoiApplique("a_reprendre", depart, None, resultat)
    # Ce que la caisse a donné à NOTRE commande (jamais écrasé par du vide) : le lien des messages signés qui suivent.
    await poser_ref_fournisseur(connexion, etablissement_id, numero, resultat.ref_fournisseur)
    if resultat.heure_annoncee is not None:  # la caisse a posé SA heure (temps de préparation allongé) : le classeur la reprend, l'écran l'affiche
        await poser_l_heure_annoncee(connexion, etablissement_id, numero, resultat.heure_annoncee, "caisse")
    if resultat.statut == "ENVOYEE" and resultat.etape == "refusee":
        # Pierre 13 : la caisse a déjà refusé la commande quand on la lit (réponse à l'envoi, recherche avant renvoi, relecture d'un « déjà en caisse ») : c'est un REFUS, avec
        # son alerte et son motif, jamais un « envoyée » silencieux (le client croirait sa commande prise)
        resultat = dataclasses.replace(resultat, statut="REFUSEE", raison="après réception" + (f" ({resultat.motif[:120]})" if resultat.motif else ""))
        if resultat.motif:
            await garder_le_motif_du_refus(connexion, etablissement_id, numero, resultat.motif)  # N6 : le motif n'est plus perdu
    vers = "refusee" if resultat.statut == "REFUSEE" else STATUT_DE_L_ETAPE.get(resultat.etape or "inconnu")
    statut = depart
    if vers and vers != depart:
        pas = await restauration.changer_statut(connexion, etablissement_id, numero, depart, vers, SOURCE)
        statut = vers if pas.statut in ("OK", "DEJA_FAIT") else pas.faits.get("statut_actuel", depart)
    if resultat.statut == "REFUSEE":
        return EnvoiApplique("refusee", statut, None, resultat, renvoi_evite)
    return EnvoiApplique("envoyee", statut, adaptation.statut_pour_l_outil(prise.capacites, resultat.etape), resultat, renvoi_evite)


def declencheur_vers_la_prise(connexion: Connexion, etablissement_id: int, prise: Prise) -> Callable[[uuid.UUID], Awaitable[None]]:
    """La fonction à donner à ``enregistrer_commande(declencher_envoi=...)``. Ne lève jamais (R1 : l'échec se voit au journal)."""

    async def declencher(numero: uuid.UUID) -> None:
        try:
            await envoyer_une_commande(connexion, etablissement_id, prise, numero)
        except Exception as erreur:  # noqa: BLE001
            logger.error(f"[.mark] Order {numero}: the send trigger failed: {erreur!r}")

    return declencher
