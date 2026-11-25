"""[.mark] Lot 7b-C2 : les textes de secours de la base et de la source de la commande.

Un texte de secours est la phrase qu'un refus portait déjà dans ``suggestion`` : le modèle ne la reçoit plus (R = A, le repli du code ne la dit que lorsque le
modèle s'est tu deux fois sur le refus). Chaque fonction est pure et ne lit que les faits du refus (plus les mots dits des nombres, des montants et des heures) :
``refus.suggestion == texte(refus.faits)`` est ce que prouve le test de chaque refus. Un texte qui lit une valeur absente des faits la fait ajouter au refus.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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


def indisponible(faits: Faits) -> str:
    """Un produit ou un choix en rupture : ``nom`` le dit."""
    return f"{faits['nom']} n'est plus disponible."


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
