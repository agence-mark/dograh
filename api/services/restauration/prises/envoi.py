"""[.mark] Module Restauration, lot 3 : l'ENVOI d'une commande enregistrée vers sa prise (le branchement du contrat).

``enregistrer_commande(..., declencher_envoi=)`` appelle, APRÈS l'enregistrement validé, une fonction qui ne reçoit que le
numéro. ``declencheur_vers_la_prise`` la fabrique : elle relit la commande dans le classeur (de CET établissement), l'envoie à
la prise, et fait avancer le statut par le chemin fermé (``changer_statut``). Rejouable sans effet double : une commande déjà
au-delà de ``nouvelle``/``envoyee`` n'est pas renvoyée ; avant un renvoi, une prise qui le permet est interrogée par NOTRE
numéro (``chercher_avant_renvoi``). Un échec ne casse jamais l'enregistrement : il s'écrit au journal d'erreur, la commande reste
``envoyee``/``nouvelle`` et le rattrapage (lot 10) la reprend. Les lots 9 et 10 posent leur file de tâches autour de ce geste.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import asyncpg
from loguru import logger

from api.db.bases_clients import restauration
from api.db.bases_clients.restauration_liaison import poser_l_heure_annoncee, poser_ref_fournisseur
from api.db.bases_clients.restauration_commande import commande_complete
from api.services.restauration.prises import adaptation
from api.services.restauration.prises.prise import GesteNonPermis, Prise, ResultatEnvoi

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


async def envoyer_une_commande(connexion: asyncpg.Connection, etablissement_id: int, prise: Prise, numero: str | uuid.UUID) -> EnvoiApplique:
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
        if connue is not None:
            resultat = ResultatEnvoi("ENVOYEE", etape=connue.get("etape"), ref_fournisseur=connue.get("ref_fournisseur"))
            return await _appliquer(connexion, etablissement_id, prise, numero_s, "envoyee", resultat, True)
    try:
        resultat = await prise.envoyer_commande(commande)
    except Exception as erreur:  # noqa: BLE001 -- une prise qui lève est une panne : on le voit, on reprend
        logger.error(f"[.mark] Order {numero_s}: sending to the {prise.nom} socket failed: {erreur!r}")
        return EnvoiApplique("a_reprendre", "envoyee", None, ResultatEnvoi("INDISPONIBLE", raison="caisse_injoignable"))
    return await _appliquer(connexion, etablissement_id, prise, numero_s, "envoyee", resultat, False)


async def _appliquer(connexion, etablissement_id, prise: Prise, numero: str, depart: str, resultat: ResultatEnvoi, renvoi_evite: bool) -> EnvoiApplique:
    if resultat.statut == "INDISPONIBLE":
        logger.warning(f"[.mark] Order {numero}: the {prise.nom} socket is unavailable, order left to retry")
        return EnvoiApplique("a_reprendre", depart, None, resultat)
    # Ce que la caisse a donné à NOTRE commande (jamais écrasé par du vide) : le lien des messages signés qui suivent.
    await poser_ref_fournisseur(connexion, etablissement_id, numero, resultat.ref_fournisseur)
    if resultat.heure_annoncee is not None:  # la caisse a posé SA heure (temps de préparation allongé) : le classeur la reprend, l'écran l'affiche
        await poser_l_heure_annoncee(connexion, etablissement_id, numero, resultat.heure_annoncee, "caisse")
    vers = "refusee" if resultat.statut == "REFUSEE" else STATUT_DE_L_ETAPE.get(resultat.etape or "inconnu")
    statut = depart
    if vers and vers != depart:
        pas = await restauration.changer_statut(connexion, etablissement_id, numero, depart, vers, SOURCE)
        statut = vers if pas.statut in ("OK", "DEJA_FAIT") else pas.faits.get("statut_actuel", depart)
    if resultat.statut == "REFUSEE":
        return EnvoiApplique("refusee", statut, None, resultat, renvoi_evite)
    return EnvoiApplique("envoyee", statut, adaptation.statut_pour_l_outil(prise.capacites, resultat.etape), resultat, renvoi_evite)


def declencheur_vers_la_prise(connexion: asyncpg.Connection, etablissement_id: int, prise: Prise) -> Callable[[uuid.UUID], Awaitable[None]]:
    """La fonction à donner à ``enregistrer_commande(declencher_envoi=...)``. Ne lève jamais (R1 : l'échec se voit au journal)."""

    async def declencher(numero: uuid.UUID) -> None:
        try:
            await envoyer_une_commande(connexion, etablissement_id, prise, numero)
        except Exception as erreur:  # noqa: BLE001
            logger.error(f"[.mark] Order {numero}: the send trigger failed: {erreur!r}")

    return declencher
