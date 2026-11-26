"""[.mark] Moteur de la commande : le changement ou l'annulation d'une commande déjà enregistrée.

Le moteur est découpé par sujet (``moteur/__init__.py`` garde tous les noms publics) ; les gestes sont ceux de l'ancien ``moteur.py``, inchangés.
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
import uuid
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
from api.services.commande.moteur.enregistrement import _brouillon_de_la_commande, enregistrer


def annulation_possible(source: Source) -> bool:
    """La prise sait-elle annuler (fiche de capacités) ? Lu AVANT de demander « vous êtes sûr ? » (DC4) : jamais une confirmation pour un refus."""
    return _permet_l_annulation(source)


def _permet_l_annulation(source: Source) -> bool:
    permet = getattr(source, "permet_l_annulation", None)
    return bool(permet and permet() and getattr(source, "annuler_une_commande", None))


async def annuler_commande_enregistree(source: Source, p: dict[str, Any], regles: Reglages) -> Resultat:
    """Elle annule la commande de CET appel, déjà enregistrée : elle passe à « annulée » dans le classeur et la prise est informée. Refusée avec la
    raison quand la prise ne sait pas annuler (fiche de capacités de sa prise) ou que la commande ne peut plus l'être (déjà remise)."""
    commande = commande_de_l_appel(p)
    if commande is None:
        return _avec(_r("INTROUVABLE", {"raison": "commande_introuvable"}, ""), p)
    if not _permet_l_annulation(source):
        return _avec(_r("INTERDIT", {"raison": "annulation_impossible", "numero_court": commande.get("numero_court")}, ""), p)
    r = await source.annuler_une_commande(str(commande["numero"]))
    if r.statut not in ("OK", "DEJA_FAIT"):
        return _avec(_r("INTERDIT", {"raison": "commande_deja_preparee", "numero_court": commande.get("numero_court")}, ""), p)
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


async def changer_commande_enregistree(source: Source, p: dict[str, Any], regles: Reglages, appelant: Appelant, avant: dict[str, Any]) -> Resultat:
    """La commande de CET appel, déjà enregistrée, vient d'être changée dans le panier (« finalement deux tiramisus », « mettez-la en mega ») :
    le changement est porté à la prise en remplaçant la commande (l'ancienne annulée, la nouvelle enregistrée à sa place : toujours une seule
    commande active pour l'appel, E30). ``avant`` : le panier d'avant la fiche. Quand la prise ne sait pas annuler, que le nouveau panier ne se
    chiffre pas ou que le règlement ne tient plus, rien n'est changé (le panier redevient celui d'avant) et la raison est rendue."""
    commande = commande_de_l_appel(avant) or {}

    def remettre(r: Resultat) -> Resultat:
        P.remplacer_par(p, avant)
        return _avec(r, p)

    if not _permet_l_annulation(source):
        return remettre(_r("INTERDIT", {"raison": "changement_impossible", "numero_court": commande.get("numero_court")}, ""))
    manque = _manque_pour_remplacer(source, p)
    if manque is not None:
        # Clôture, lot B4 (M2) : ce qui manque à la nouvelle commande se constate AVANT de toucher à la caisse ; avant, l'ancienne était annulée,
        # la nouvelle refusée (« incomplète ») et la commande perdue (passer en livraison sans adresse, retirer la seule ligne)
        faits = {"raison": "changement_incomplet", "manque": manque, "numero_court": commande.get("numero_court")}
        return remettre(_r("INCOMPLETE", faits, "", manque))  # C7 B5 : le modèle dit ce qui manque (les articles : c'est une annulation ; l'adresse) d'après le manque
    if P.a_completer(p):
        return _avec(await etat_apres_ajout(source, p, regles, {}), p)  # la ligne changée attend encore sa réponse : rien ne part à la prise
    chiffre = await chiffrer_le_panier(source, p, regles)
    if chiffre.statut != "OK":
        return remettre(chiffre)
    paiement, refus = await _le_reglement(source, p, chiffre.faits["total"], p.get("paiement") or {})
    if refus is not None:
        return remettre(refus)
    # Pierre A2 : tout ou rien. Ce que l'enregistrement refuserait (plafond des titres, rupture relue en base, fermeture, heure) se constate AVANT
    # d'annuler l'ancienne : un refus laisse la commande de l'appel telle quelle et le panier redevient celui d'avant
    verifier = getattr(source, "verifier_l_enregistrement", None)
    if verifier is not None:
        jeton = (p.get("relecture") or {}).get("jeton") or uuid.uuid4().hex
        a_blanc = await verifier(_brouillon_de_la_commande(p, chiffre, paiement, appelant, regles), jeton)
        if a_blanc.statut != "OK":
            return remettre(a_blanc)
    # La commande d'avant n'est JAMAIS annulée en caisse tant que la nouvelle n'est pas acceptée (Evan, 24/11) : la nouvelle part d'abord, l'ancienne ensuite.
    ETAPE.transition(p, ETAPE.ENREGISTREMENT_DEFAIT)
    r = await enregistrer(source, p, regles, appelant, chiffre, paiement)
    if r.statut not in ("ENREGISTREE", "TRANSMISE"):
        logger.error(f"[.mark] commande {commande.get('numero_court')} : la nouvelle version n'est pas acceptée ({r.statut}), l'ancienne reste en caisse")
        # la commande d'avant reste celle de l'appel, telle quelle (étape, empreinte et accord d'avant, sans nouvelle relecture) ; le modèle reçoit le fait et le dit
        return remettre(Resultat(r.statut, {**(r.faits or {}), "raison": "changement_refuse_par_la_caisse", "commande_d_avant_gardee": True, "numero_court": commande.get("numero_court")}, r.suggestion, r.manque))
    annulee = await source.annuler_une_commande(str(commande.get("numero")))
    if annulee.statut not in ("OK", "DEJA_FAIT"):
        logger.error(f"[.mark] commande {commande.get('numero_court')} : la nouvelle est acceptée mais l'ancienne n'a pas pu être annulée ({annulee.statut}) : risque de doublon en cuisine")
        alerter = getattr(source, "alerter_d_un_doublon", None)
        if alerter is not None:
            await alerter(str(commande.get("numero")), str((r.faits or {}).get("numero")))  # le restaurant le sait tout de suite
    return Resultat(r.statut, {**r.faits, "remplace": commande.get("numero_court")}, r.suggestion, r.manque)
