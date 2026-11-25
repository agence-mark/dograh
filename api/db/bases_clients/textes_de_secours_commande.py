"""[.mark] Lot 7b-C2 : les textes de secours de la base et de la source de la commande.

Un texte de secours est la phrase qu'un refus portait déjà dans ``suggestion`` : le modèle ne la reçoit plus et le code ne la dit plus (lot 7b-C5 : le modèle muet est relancé avec les faits du refus) ; elle reste jusqu'à C7. Chaque fonction est pure et ne lit que les faits du refus (plus les mots dits des nombres, des montants et des heures) :
``test_p1f_lot7c7_signal_du_secours`` prouve que ses faits portent chaque valeur du texte (``refus.suggestion`` est vide pour les refus vidés au lot 7b-C7a). Un texte qui lit une valeur absente des faits la fait ajouter au refus.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from api.services.commande import textes_de_secours as TS
from api.services.mots_dits import liste_dite_et, montant_en_lettres

Faits = Mapping[str, Any]


def _est_ce(dits: list[str]) -> str:
    return f"Est-ce {' ou '.join(dits)} ?"


# --------------------------------------------------------------------------- #
# Le jour et l'heure dits (``source_commande.resolution_du_jour_et_de_l_heure``)
# --------------------------------------------------------------------------- #


def quel_jour(faits: Faits) -> str:
    return "Pour quel jour ?"


def heure_passee_sans_jour(faits: Faits) -> str:
    return f"Il est déjà plus de {faits['heure_dite']} : pour quel jour ?"


def heure_ambigue(faits: Faits) -> str:
    return _est_ce(list(faits["candidats_heure"]))


def jour_ambigu(faits: Faits) -> str:
    return _est_ce([c["jour_dit"] for c in faits["candidats"]])


def quelle_heure_ce_jour(faits: Faits) -> str:
    return f"À quelle heure, {faits['jour_dit']} ?"


def quelle_heure_exactement(faits: Faits) -> str:
    return "À quelle heure exactement ?"


def heure_passee(faits: Faits) -> str:
    return "Cette heure est déjà passée, pour quelle heure ?"


# --------------------------------------------------------------------------- #
# La fermeture (``SourceClasseur.etat``) : l'état ne dit que ``statut``, ``reprise_dite`` et ``planifiee_permise``
# --------------------------------------------------------------------------- #


def fermeture(etat: Faits) -> str:
    reprise = f" Nous reprenons à {etat['reprise_dite']}." if etat.get("reprise_dite") else ""
    # D15 : quand le réglage du type permet de commander pour plus tard, la fermeture le propose (un créneau de la prochaine ouverture).
    propose = " Je peux prendre votre commande pour plus tard, sur un créneau de la prochaine ouverture." if etat.get("planifiee_permise") else ""
    if etat["statut"] == "LIVRAISON_TERMINEE":
        return "Les livraisons sont terminées pour aujourd'hui." + reprise + propose
    if etat["statut"] == "PAUSE_TYPE":
        return "Nous sommes en pause pour le moment." + reprise + propose
    return "Nous sommes fermés pour le moment." + reprise + propose


# --------------------------------------------------------------------------- #
# Un message demandé par l'appelant (``SourceClasseur.envoyer``)
# --------------------------------------------------------------------------- #


def envoi_indisponible(faits: Faits) -> str:
    return "Je ne peux pas envoyer de message pour le moment."


def envoye(faits: Faits) -> str:
    return "C'est envoyé."


# --------------------------------------------------------------------------- #
# La carte : les choix d'un produit, d'une formule, les lignes de la commande (``restauration_commande``)
# --------------------------------------------------------------------------- #


def choix_hors_produit(faits: Faits) -> str:
    return "Ce choix n'existe pas pour ce produit."


def quantite_de_choix_invalide(faits: Faits) -> str:
    return "Quantité de choix invalide."


def option_trop_de_fois(faits: Faits) -> str:
    return f"{faits['nom']} ne se prend pas plus de {faits['maximum']} fois."


def choix_obligatoire(faits: Faits) -> str:
    return f"Il faut choisir : {faits['nom']}."


def pas_plus_pour(faits: Faits) -> str:
    return f"Pas plus de {faits['maximum']} pour : {faits['nom']}."


def choix_hors_formule(faits: Faits) -> str:
    return "Ce choix n'existe pas dans cette formule."


def element_de_formule_indisponible(faits: Faits) -> str:
    return "Un élément de la formule n'est plus disponible."


def une_seule_alternative(faits: Faits) -> str:
    return "Une seule alternative."


def ne_peut_pas_retirer(faits: Faits) -> str:
    return f"On ne peut pas retirer : {faits['retire']}."


def quantite_invalide(faits: Faits) -> str:
    return "Quantité invalide."


def produit_hors_carte(faits: Faits) -> str:
    return "Ce produit n'est pas à la carte."


def prix_different(faits: Faits) -> str:
    return "Le prix ne correspond pas à la carte."


# --------------------------------------------------------------------------- #
# La zone, le mode et le créneau voulu
# --------------------------------------------------------------------------- #


def hors_zone(faits: Faits) -> str:
    """Faits : ``commune`` (``nom``) et ``communes_livrees`` quand l'adresse est reconnue, sinon rien (aucune zone, ou zone introuvable)."""
    commune = faits.get("commune")
    if not commune:
        return "Nous ne livrons pas à cette adresse."
    livrees = list(faits.get("communes_livrees") or [])
    return f"Nous ne livrons pas à {commune['nom']}." + (f" Nous livrons {liste_dite_et(livrees)}." if livrees else "")


def adresse_non_comprise(faits: Faits) -> str:
    return "Je n'ai pas compris l'adresse, pouvez-vous la répéter ?"


def quelle_commune(faits: Faits) -> str:
    return "Dans quelle commune se trouve l'adresse ?"


def commune_ambigue(faits: Faits) -> str:
    """Faits : ``candidats`` (chacun avec ``nom`` et ``departement``)."""
    return "Est-ce " + " ou ".join(f"{c['nom']} ({c['departement']})" for c in faits["candidats"]) + " ?"


def minimum_non_atteint(faits: Faits) -> str:
    return f"Le minimum de commande est de {montant_en_lettres(faits['minimum'])}."


def mode_non_compris(faits: Faits) -> str:
    return "Je n'ai pas compris le mode de la commande."


def pas_de_commande_pour_plus_tard(faits: Faits) -> str:
    return "Je ne prends pas de commande pour plus tard."


def commandes_jusqu_a(faits: Faits) -> str:
    return f"Je prends les commandes jusqu'à {faits['jusqu_a']} : pour quand la voulez-vous ?"


def trop_tot(faits: Faits) -> str:
    return "C'est trop tôt pour moi."


def ferme_a_cette_heure(faits: Faits) -> str:
    """Fermé à l'heure voulue : ``rouvre_dit`` (le moment où l'on rouvre, dit) seulement quand on le connaît, sinon la phrase du moment."""
    if faits.get("rouvre_dit"):
        return f"À cette heure nous sommes fermés. Nous rouvrons {faits['rouvre_dit']} : pour quelle heure à partir de là ?"
    return TS.pas_de_commande_en_ce_moment(faits)


def creneau_complet(faits: Faits) -> str:
    return f"Ce créneau est complet, je peux vous proposer {faits['proposition_dite']}."


# --------------------------------------------------------------------------- #
# Ce qui manque à la demande, le règlement, la remise, la commande introuvable
# (les manques qui ont une phrase au catalogue ``phrases_du_manque`` la prennent de là : articles, téléphone, adresse, paiement)
# --------------------------------------------------------------------------- #


def situer_l_adresse(faits: Faits) -> str:
    return "Je dois situer l'adresse de livraison."


def relire_la_commande(faits: Faits) -> str:
    return "Je vous relis la commande avant de l'enregistrer."


def origine_invalide(faits: Faits) -> str:
    return "Origine de la commande invalide."


def heure_non_valable(faits: Faits) -> str:
    return "L'heure demandée n'est pas valable."


def prenom_trop_long(faits: Faits) -> str:
    return "Prénom trop long."




def reglement_invalide(faits: Faits) -> str:
    return "Règlement invalide."


def plafond_titre_depasse(faits: Faits) -> str:
    return "Le montant en titres-restaurant dépasse le plafond."


def titre_et_alcool(faits: Faits) -> str:
    return "Les titres-restaurant ne paient pas l'alcool."


def titre_sans_rendu(faits: Faits) -> str:
    return "On ne rend pas la monnaie sur un titre-restaurant."


def montant_de_paiement_invalide(faits: Faits) -> str:
    return "Montant de paiement invalide."


def reglement_incomplet(faits: Faits) -> str:
    return "Le règlement ne couvre pas exactement le total."


def remise_non_applicable(faits: Faits) -> str:
    return "Cette remise ne s'applique pas à votre commande."


def commande_introuvable(faits: Faits) -> str:
    return "Je ne trouve pas cette commande."
