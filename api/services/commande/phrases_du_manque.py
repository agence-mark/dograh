"""[.mark] Chantier Partie 1, lot 4 (M13 ; B12, décision 1) : les phrases de ce qui manque à la commande, une par valeur fermée de « manque ».

La valeur fermée (``Manque``) est celle de l'état (``etat_pour_le_modele.ce_qui_manque_ensuite``, vocabulaire de B8). La phrase n'est plus donnée au modèle (7b-C4 : ``texte_a_dire``
est retiré du retour, rangé dans le constat caché) ; le code ne la dit lui-même que dans le repli du lot 6
(L06-28). Mot pour mot : les phrases que B12 écrit (« Qu'est-ce que je vous mets ? », « Je vous mets autre chose ? ») ; les autres sont celles que le
module rend déjà (``QUESTION_MANQUE`` du guichet du banc). Une valeur portée par une question (la variante, l'accord sur le récapitulatif) n'a pas
de phrase propre : c'est la question qui la porte (``None``).
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from typing import Any

from enum import StrEnum

from api.services.mots_dits import liste_dite


class Manque(StrEnum):
    """Ce qui manque à une commande : une liste fermée. La valeur est le mot que l'état montre au modèle ; la décision lit le membre, jamais ces mots."""

    MODE = "le mode de retrait"  # suivi de ses choix entre parenthèses dans l'état : « le mode de retrait (à emporter ou en livraison) »
    ADRESSE_ET_COMMUNE = "l'adresse de livraison (numéro, rue et commune)"
    COMMUNE = "la commune de livraison"
    VOIE = "l'adresse (numéro et rue)"
    ARTICLES = "les articles"
    VARIANTE = "une variante à choisir"
    AUTRE_CHOSE = "d'autres articles, ou qu'elle dise qu'elle a tout dit"
    ACCORD = "son accord sur le récapitulatif"
    PAIEMENT = "le moyen de paiement"
    TELEPHONE = "le numéro de téléphone"
    PRENOM = "le prénom"
    CONSIGNE_LIVREUR = "une consigne pour le livreur"


MODE = Manque.MODE  # nom gardé : ``porte`` passe ce membre à ``phrase_du_manque`` pour les autres modes ouverts

PHRASES_DU_MANQUE: dict[Manque, str | None] = {
    Manque.MODE: None,  # la phrase se fait des modes ouverts : ``phrase_du_manque``
    Manque.ADRESSE_ET_COMMUNE: "Quelle est l'adresse de livraison ?",
    Manque.COMMUNE: "Dans quelle commune ?",
    Manque.VOIE: "Quelle est l'adresse de livraison ?",
    Manque.ARTICLES: "Qu'est-ce que je vous mets ?",
    Manque.VARIANTE: None,  # portée par la question variante du module
    Manque.AUTRE_CHOSE: "Je vous mets autre chose ?",
    Manque.ACCORD: None,  # portée par la question récapitulatif
    Manque.PAIEMENT: "Vous réglez comment ?",
    Manque.TELEPHONE: "Quel est votre numéro de téléphone ?",
    Manque.PRENOM: "À quel nom je mets la commande ?",
    Manque.CONSIGNE_LIVREUR: "Une consigne pour le livreur ?",
}
PORTEES_PAR_UNE_QUESTION = frozenset(k for k, v in PHRASES_DU_MANQUE.items() if v is None and k is not Manque.MODE)


def phrase_du_manque(manque: Manque | None, modes: list[str] | tuple[str, ...] | None = None) -> str | None:
    """La phrase de ce qui manque, mot pour mot ; ``None`` : rien ne manque, ou c'est une question qui le porte. ``modes`` : les libellés des modes ouverts."""
    if manque is Manque.MODE:
        dits = list(modes or ())
        return f"{liste_dite(dits).capitalize()} ?" if dits else None
    return PHRASES_DU_MANQUE.get(manque) if manque else None


def texte_a_dire(p: dict[str, Any]) -> str | None:
    """La phrase de ce qui manque ENSUITE pour ce panier, quand aucune question n'attend : ce que le repli dit (le modèle n'en reçoit que le fait ``manque``)."""
    from api.services.commande import etat_pour_le_modele as E

    if CONV.question_de(p):
        return None
    manque, modes = E.ce_qui_manque(p, p.get(E.CLE_CONNU) or {})
    return phrase_du_manque(manque, modes)


def valeur_du_manque(p: dict[str, Any]) -> str | None:
    """La valeur fermée de ce qui manque ENSUITE pour ce panier, quand aucune question n'attend et qu'une phrase la dirait (C5 : la relance du modèle la reçoit comme un fait)."""
    from api.services.commande import etat_pour_le_modele as E

    if CONV.question_de(p):
        return None
    manque, modes = E.ce_qui_manque(p, p.get(E.CLE_CONNU) or {})
    return str(manque.value) if manque and phrase_du_manque(manque, modes) else None
