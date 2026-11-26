"""[.mark] Moteur de la commande : le changement ou l'annulation d'une commande déjà enregistrée.

Le moteur est découpé par sujet (``moteur/__init__.py`` garde tous les noms publics). Lot 8b-1b (§ 17 l.404) : le changement réécrit la ligne en base, l'annulation ne touche pas la caisse.
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from typing import Any
from loguru import logger

from api.services.commande import etape as ETAPE
from api.services.commande import panier as P
from api.services.commande.resultat import Resultat
from api.services.commande.source import Source
from api.services.commande.moteur.socle import Appelant, Reglages, _avec, _r, commande_de_l_appel
from api.services.commande.moteur.prealables import chiffrer_le_panier
from api.services.commande.moteur.articles import etat_apres_ajout
from api.services.commande.moteur.reglement import _le_reglement
from api.services.commande.moteur.enregistrement import reecrire


async def annuler_commande_enregistree(source: Source, p: dict[str, Any], regles: Reglages) -> Resultat:
    """Elle annule la commande de CET appel, déjà enregistrée (lot 8b-1b, E6 ; § 17 l.404) : sa ligne ``retenue`` passe à « annulée » en base au tour même (le filet
    du rattrapage ne peut jamais l'envoyer) ; la caisse n'en a jamais rien reçu, elle n'est ni lue ni informée (A8 tombe : plus de statut de caisse pendant l'appel). Refusée
    avec la raison quand la commande est introuvable ou que la base refuse (la ligne n'est plus ``retenue``)."""
    commande = commande_de_l_appel(p)
    if commande is None:
        return _avec(_r("INTROUVABLE", {"raison": "commande_introuvable"}, ""), p)
    r = await source.annuler_une_commande(str(commande["numero"]))
    if r.statut not in ("OK", "DEJA_FAIT"):
        logger.error(f"[.mark] commande {commande.get('numero_court')} : l'annulation est refusée par la base ({r.statut})")
        return _avec(_r("INTERDIT", {"raison": "annulation_impossible", "numero_court": commande.get("numero_court")}, ""), p)
    ETAPE.transition(p, ETAPE.ANNULEE_APRES_ENREGISTREMENT, numero_court=commande.get("numero_court"))
    CONV.poser_question(p, None)
    return _avec(_r("OK", {"commande_annulee": commande.get("numero_court")}, ""), p)


def _manque_pour_remplacer(source: Source, p: dict[str, Any]) -> str | None:
    """Ce qui manque au panier changé pour être enregistré à la place de l'autre (les manques que ``enregistrer_commande`` refuserait) : ``articles`` ou ``adresse``, ou ``None``."""
    if not P.lignes_pretes(p) and not P.a_completer(p):
        return "articles"
    if p.get("mode") in ("livraison",) and (not p.get("adresse") or not p.get("zone")):
        return "adresse"
    return None


def manque_pour_remplacer(source: Source, p: dict[str, Any]) -> str | None:
    """7c : le même constat, lu par la porte avant d'attendre la taille d'une ligne (Pierre A2 : tout ou rien, le manque d'abord)."""
    return _manque_pour_remplacer(source, p)


async def changer_commande_enregistree(source: Source, p: dict[str, Any], regles: Reglages, appelant: Appelant, avant: dict[str, Any]) -> Resultat:
    """La commande de CET appel, déjà enregistrée, vient d'être changée dans le panier (« finalement deux tiramisus », « mettez-la en mega ») : lot 8b-1b (E4 ; § 17 l.404),
    sa ligne ``retenue`` est RÉÉCRITE en base, à sa place (même numéro) ; rien ne part ni ne s'annule en caisse pendant l'appel, la fin de l'appel enverra la dernière version.
    ``avant`` : le panier d'avant la fiche. Quand il manque quelque chose, que le nouveau panier ne se chiffre pas, que le règlement ne tient plus ou que la base refuse la
    nouvelle version (tout ou rien, Pierre A2), rien n'est changé et la raison est rendue : le panier redevient celui d'avant, ou la commande enregistrée quand la fiche
    refusée complétait une ligne en attente (T16, option C ; ``lignes_en_attente_retirees``)."""
    commande = commande_de_l_appel(avant) or {}

    def remettre(r: Resultat) -> Resultat:
        retirees = P.revenir_apres_un_refus(p, avant)  # T16, option C
        if retirees:
            r = Resultat(r.statut, {**(r.faits or {}), "lignes_en_attente_retirees": retirees}, r.suggestion, r.manque)
        return _avec(r, p)

    manque = _manque_pour_remplacer(source, p)
    if manque is not None:
        # Clôture, lot B4 (M2) : ce qui manque à la nouvelle version (passer en livraison sans adresse, retirer la seule ligne) se constate avant toute écriture
        faits = {"raison": "changement_incomplet", "manque": manque, "numero_court": commande.get("numero_court")}
        return remettre(_r("INCOMPLETE", faits, "", manque))  # C7 B5 : le modèle dit ce qui manque (les articles : c'est une annulation ; l'adresse) d'après le manque
    if P.a_completer(p):
        return _avec(await etat_apres_ajout(source, p, regles, {}), p)  # la ligne changée attend encore sa réponse : rien n'est réécrit
    chiffre = await chiffrer_le_panier(source, p, regles)
    if chiffre.statut != "OK":
        return remettre(chiffre)
    paiement, refus = await _le_reglement(source, p, chiffre.faits["total"], p.get("paiement") or {})
    if refus is not None:
        return remettre(refus)
    r = await reecrire(source, p, regles, appelant, chiffre, paiement, str(commande.get("numero")))
    if r.statut != "ENREGISTREE":
        logger.error(f"[.mark] commande {commande.get('numero_court')} : la nouvelle version n'est pas écrite ({r.statut}), la commande d'avant est gardée")
        # la commande d'avant reste celle de l'appel, telle quelle (étape, empreinte et accord d'avant, sans nouvelle relecture) ; le modèle reçoit le fait et le dit
        return remettre(Resultat(r.statut, {**(r.faits or {}), "raison": "changement_refuse", "commande_d_avant_gardee": True, "numero_court": commande.get("numero_court")},
                                 r.suggestion, r.manque))
    faits = {**r.faits, "remplace": commande.get("numero_court")}
    if p.get("adresse") and p.get("adresse") != avant.get("adresse"):
        faits["adresse"] = P.voie_de_l_adresse(p["adresse"])  # E-2 : le modèle dit la nouvelle adresse (exigée de sa phrase)
    return Resultat(r.statut, faits, r.suggestion, r.manque)
