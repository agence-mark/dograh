"""[.mark] Lot 7b-C3 : les textes de secours de la réservation (feuille : rien de ``services.reservation`` n'y est importé, la base et le moteur la lisent tous deux).

Un texte de secours est la phrase qu'un refus ou une question portait déjà dans ``suggestion`` : le modèle ne la reçoit plus (R = A, le repli du code ne la dit que lorsque le
modèle s'est tu deux fois sur le refus). Chaque fonction est pure et ne lit que les faits du refus (plus les mots dits des nombres) : ``resultat.suggestion == texte(faits)`` est ce que
prouve le test de chaque refus. Un texte qui lit une valeur absente des faits la fait ajouter au refus.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from api.services.mots_dits import liste_dite, nombre_en_lettres

Faits = Mapping[str, Any]


# --------------------------------------------------------------------------- #
# Les refus de la base (``restauration_reservation``) : une fonction par ``faits.detail``
# --------------------------------------------------------------------------- #


def passe(faits: Faits) -> str:
    return "Ce moment est déjà passé."


def trop_tot(faits: Faits) -> str:
    return "C'est trop tôt pour moi, il me faut un peu plus de temps."


def trop_loin(faits: Faits) -> str:
    return "C'est trop loin pour que je réserve."


def hors_service(faits: Faits) -> str:
    return "Nous ne prenons pas de réservation à cette heure-là."


def groupe_trop_grand(faits: Faits) -> str:
    return "Pour un groupe de cette taille, c'est l'équipe qui s'en occupe : je lui laisse un message pour qu'elle vous rappelle ?"


def ferme(faits: Faits) -> str:
    return "Nous ne prenons pas de réservation sur ce moment."


def complet(faits: Faits) -> str:
    return "Nous sommes complets à cette heure-là."


def type_ferme(faits: Faits) -> str:
    return "Nous ne prenons pas de réservation en ce moment."


def plus_modifiable(faits: Faits) -> str:
    return "Cette réservation n'est plus modifiable."


def passee(faits: Faits) -> str:
    return "Cette réservation est passée, je ne peux plus la changer."


DU_DETAIL: dict[str, Callable[[Faits], str]] = {
    "passe": passe, "trop_tot": trop_tot, "trop_loin": trop_loin, "hors_service": hors_service, "groupe_trop_grand": groupe_trop_grand, "ferme": ferme,
    "complet": complet, "type_ferme": type_ferme, "plus_modifiable": plus_modifiable, "passee": passee,
}


def refus_de_la_base(faits: Faits) -> str:
    """Le texte d'un refus de la base d'après son ``detail`` ; avec ``propositions`` (les créneaux libres les plus proches), il les propose."""
    texte = DU_DETAIL[faits["detail"]](faits)
    dites = [p["quand_dit"] for p in faits.get("propositions") or []]
    return f"{texte} Je peux vous proposer {' ou '.join(dites)}." if dites else texte


# --------------------------------------------------------------------------- #
# Ce qui manque, ou ne se lit pas, à la base (``creer_reservation``, ``modifier_reservation``) ; les six premiers textes sont aussi ceux de ``phrases_du_manque``
# --------------------------------------------------------------------------- #

PERSONNES = "Pour combien de personnes ?"
JOUR = "Pour quel jour ?"
HEURE = "À quelle heure ?"
NOM = "À quel nom ?"
TELEPHONE = "Quel est votre numéro de téléphone ?"
NOM_ET_JOUR_D_AVANT = "À quel nom et pour quel jour était votre réservation ?"


def combien_de_personnes(faits: Faits) -> str:
    return PERSONNES


def quel_jour_et_quelle_heure(faits: Faits) -> str:
    return "Pour quel jour et à quelle heure ?"


def a_quel_nom_je_mets_la_reservation(faits: Faits) -> str:
    return "À quel nom je mets la réservation ?"


def nom_trop_long(faits: Faits) -> str:
    return "Ce nom est trop long."


def numero_illisible(faits: Faits) -> str:
    return "Je n'ai pas bien compris le numéro : vous pouvez le redire ?"


def quel_numero(faits: Faits) -> str:
    return TELEPHONE


def note_trop_longue(faits: Faits) -> str:
    return "Cette note est trop longue."


# --------------------------------------------------------------------------- #
# Ce qui est déjà fait, et la recherche d'une réservation (``restauration_reservation``)
# --------------------------------------------------------------------------- #


def personnes_dites(n: int) -> str:
    return f"{nombre_en_lettres(n)} personne" + ("s" if n > 1 else "")


def deja_reservee(faits: Faits) -> str:
    return f"C'est déjà réservé pour {faits['quand_dit']}."


def deja_comme_cela(faits: Faits) -> str:
    return "C'est déjà comme cela."


def deja_annulee(faits: Faits) -> str:
    return "Cette réservation est déjà annulée."


def sous_quel_nom_et_quel_jour(faits: Faits) -> str:
    return "Sous quel nom, et pour quel jour ?"


def pas_de_reservation(faits: Faits) -> str:
    return "Je ne trouve pas de réservation."


def une_reservation(faits: Faits) -> str:
    seule = faits["reservations"][0]
    return f"Vous avez une réservation {seule['quand_dit']} pour {personnes_dites(seule['couverts'])}."


def plusieurs_reservations(faits: Faits) -> str:
    return f"Je trouve {len(faits['reservations'])} réservations."


# --------------------------------------------------------------------------- #
# Les questions du moteur (``services.reservation.moteur``) ; les manques déjà posés plus haut (personnes, numéro, nom) y sont repris
# --------------------------------------------------------------------------- #


def quel_jour(faits: Faits) -> str:
    return JOUR


def quelle_heure(faits: Faits) -> str:
    return HEURE


def que_change_je(faits: Faits) -> str:
    return "Qu'est-ce que je change : l'heure, le nombre de personnes ?"


# --------------------------------------------------------------------------- #
# Ce que le moteur rend après un geste (disponibilités, recherche, changement, annulation)
# --------------------------------------------------------------------------- #


def complets_ce_jour(faits: Faits) -> str:
    """Aucun créneau libre ce jour-là, ou dans la partie du jour dite (``partie``)."""
    return f"Nous sommes complets ce jour-là, pour le {faits['partie']}." if faits.get("partie") else "Nous sommes complets ce jour-là."


def il_y_a_de_la_place(faits: Faits) -> str:
    return f"Il y a de la place à {liste_dite([c['heure_dite'] for c in faits['creneaux']])}."


def refus_complet_du_moteur(faits: Faits) -> str:
    """Le créneau demandé n'est pas libre : ses plus proches (``propositions``), sinon rien de libre ce jour-là."""
    dites = [p["heure_dite"] for p in faits.get("propositions") or []]
    return f"Nous ne pouvons pas à cette heure-là. Je peux vous proposer {liste_dite(dites)}." if dites else "Nous sommes complets ce jour-là."


def deja_une_reservation_dans_cet_appel(faits: Faits) -> str:
    return "Vous avez déjà une réservation dans cet appel : pour la changer, dites ce qui change."


def aucune_reservation_a_venir(faits: Faits) -> str:
    return "Je ne trouve pas de réservation à venir."


def une_reservation_trouvee(faits: Faits) -> str:
    seule = faits["reservation"]
    return f"Vous avez une réservation {seule['quand_dit']} pour {personnes_dites(seule['personnes'])}."


def plusieurs_a_choisir(faits: Faits) -> str:
    """Le choix : les candidats que le code a dits (``candidats[].dit``), donc le résultat entier et non ses faits publics."""
    return "Vous en avez plusieurs : " + liste_dite([c["dit"] for c in faits["candidats"]]) + ". Laquelle ?"


def rien_ne_change(faits: Faits) -> str:
    return f"Rien ne change : votre réservation reste {faits['quand_dit']} pour {personnes_dites(faits['personnes'])}."


def laquelle(faits: Faits) -> str:
    """La question du choix quand le moteur n'a rien dit (``porte``) ; le choix lui-même se dit par ``plusieurs_a_choisir``."""
    return "Laquelle ?"


def une_seule_par_appel(faits: Faits) -> str:
    """La règle « une seule réservation par appel » quand celle de l'appel est annulée ; la promesse de transmission n'y est que si la demande est transmise (``transmise``)."""
    phrase = "Je ne peux prendre qu'une réservation par appel, et celle de cet appel est annulée."
    return f"{phrase} Je transmets votre demande à l'équipe, elle vous rappelle." if faits.get("transmise") else phrase


def capacite_non_reglee(faits: Faits) -> str:
    return "Je ne peux pas confirmer une place pour l'instant : je laisse un message à l'équipe pour qu'elle vous rappelle ?"


def du_refus(dernier: Any, transmise: bool) -> str:
    """Le texte que le code dit si le modèle se tait deux fois sur le refus du dernier retour (R = A) ; vide quand ce retour n'est pas un refus."""
    faits = dict(dernier.faits or {})
    if dernier.statut in ("REFUSEE", "INTROUVABLE"):
        return dernier.suggestion or ""
    if dernier.statut == "DEJA_FAIT" and faits.get("raison") == "deja_une_reservation_dans_cet_appel" and faits.get("deja_annulee"):
        return une_seule_par_appel({"transmise": transmise})
    if dernier.statut == "INCOMPLETE" and dernier.manque == "capacite":
        return capacite_non_reglee(faits)
    return ""
