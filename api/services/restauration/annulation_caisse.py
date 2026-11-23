"""[.mark] Module Restauration, lot 19 bis (K5) : dire à la caisse qu'une commande est ANNULÉE, sans jamais la laisser vivante en cuisine.

Avant : l'annulation passait la commande à ``annulee`` chez nous puis prévenait la caisse ; un échec (réseau, 5xx, 429, commande « pas encore connue ») était avalé avec une ligne de
journal, rien ne la rejouait, et le restaurant préparait une commande que l'agent avait dite annulée. Maintenant l'annulation est GARDÉE « à dire » (``annulation_a_dire_le``) avant
d'être tentée, effacée quand la caisse l'a reçue, et le rattrapage (``rattrapage_des_envois``) la rejoue, espacée ; au ``TENTATIVES_MAX``-ième essai raté une alerte part, UNE fois.
Rejouer une annulation est sans risque (HubRise l'accepte depuis tout statut et deux fois de suite : 04a, 04b) ; une caisse qui ne connaît pas encore la commande (404, 04h, ou recherche
vide) n'a pas encore reçu l'envoi : on réessaie.
"""

from __future__ import annotations

import uuid
from typing import Any

from api.db.bases_clients import restauration_liaison as liaison_db
from api.db.bases_clients.restauration_commande import commande_complete
from api.db.bases_clients.restauration_commun import Connexion
from api.services.restauration.envoi_caisse import (
    TENTATIVES_MAX,
    Secours,
    _secours_par_defaut,
)
from api.services.restauration.prises.prise import GesteNonPermis, Prise
from api.services.restauration.secours import secours_de_la_commande
from loguru import logger


def texte_de_l_annulation_perdue(commande: dict, essais: int) -> tuple[str, str]:
    """Le sujet et le texte : la commande est annulée chez nous mais la caisse ne l'a pas su ; une personne doit l'annuler en caisse (ou vérifier qu'elle n'y est pas)."""
    court = commande.get("numero_court") or str(commande["numero"])[:8]
    corps = (
        f"La commande {court} a été annulée mais la caisse ne l'a pas su après {essais} essais. Annulez-la dans la caisse si elle y apparaît, sinon elle sera préparée.\n"
        f"Order {court} was cancelled but the till did not get the news after {essais} tries. Cancel it in the till if it shows there, or it will be prepared.\n\n"
        f"Téléphone : {(commande.get('client') or {}).get('telephone') or '-'}\n"
    )
    return f"Commande {court} annulée mais pas en caisse / cancelled but still in the till", corps


async def dire_l_annulation(
    connexion: Connexion, organization_id: int | None, etablissement_id: int, prise: Prise | None, numero: str | uuid.UUID, *, secours: Secours | None = None
) -> bool:
    """Garde l'annulation « à dire » puis la dit à la caisse. ``True`` si la caisse l'a reçue. Ne lève jamais (R1 : une panne se voit au journal et le rattrapage rejoue)."""
    numero_s = str(numero)
    try:
        gardee = await liaison_db.garder_l_annulation_a_dire(connexion, etablissement_id, numero_s)  # fausse : jamais envoyée à la caisse, rien à rejouer (un essai est fait quand même)
        if prise is None or not prise.capacites.annulation:
            await liaison_db.annulation_dite_a_la_caisse(connexion, etablissement_id, numero_s)  # cette caisse ne sait pas annuler : rien à rejouer
            return False
        recue = False
        try:
            ref_de_la_caisse = await liaison_db.ref_de_la_commande_de_la_caisse(connexion, etablissement_id, numero_s)
            resultat = await prise.annuler_commande(numero_s, **({"ref_fournisseur": ref_de_la_caisse} if ref_de_la_caisse else {}))
            recue = resultat.statut == "ENVOYEE"  # « REFUSEE » : la caisse ne connaît pas (encore) la commande
        except GesteNonPermis:
            await liaison_db.annulation_dite_a_la_caisse(connexion, etablissement_id, numero_s)
            return False
        except Exception as erreur:  # noqa: BLE001 -- R1 : la caisse en panne ne défait pas l'annulation, le rattrapage la rejoue
            logger.error(f"[.mark] Order {numero_s}: telling the till about the cancellation failed: {type(erreur).__name__}")
        if recue:
            await liaison_db.annulation_dite_a_la_caisse(connexion, etablissement_id, numero_s)
            return True
        if not gardee:
            return False
        essais = await liaison_db.compter_un_essai_d_annulation(connexion, etablissement_id, numero_s)
        if essais >= TENTATIVES_MAX and await liaison_db.marquer_l_alerte_d_annulation(connexion, etablissement_id, numero_s):
            await _alerter(connexion, organization_id, etablissement_id, numero_s, essais, secours or _secours_par_defaut)
        return False
    except Exception as erreur:  # noqa: BLE001
        logger.error(f"[.mark] Order {numero_s}: keeping the cancellation to tell the till failed: {type(erreur).__name__}")
        return False


async def _alerter(connexion: Connexion, organization_id: int | None, etablissement_id: int, numero: str, essais: int, secours: Secours) -> None:
    commande = await commande_complete(connexion, etablissement_id, numero)
    if commande is None:
        return
    sujet, texte = texte_de_l_annulation_perdue(commande, essais)
    bilan: Any = await secours_de_la_commande(connexion, organization_id, etablissement_id, commande, "annulation non reçue par la caisse")
    logger.info(f"[.mark] Order {numero}: cancellation rescue ladder {bilan}")
    try:
        await secours(organization_id, sujet, texte)
    except Exception as erreur:  # noqa: BLE001 -- dire une panne ne doit pas en faire une seconde
        logger.error(f"[.mark] Order {numero}: the cancellation rescue message failed: {type(erreur).__name__}")
