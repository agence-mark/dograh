"""[.mark] Chantier Partie 1, lot 4 (M13 ; B12, décision 1) : les phrases de ce qui manque à la commande, une par valeur fermée de « manque ».

La valeur fermée est celle de l'état (``etat_pour_le_modele.ce_qui_manque_ensuite``, vocabulaire de B8). La phrase est proposée par le code dans
``texte_a_dire`` (« une phrase proposée par le code, que le modèle peut dire », glossaire) ; le code ne la dit lui-même que dans le repli du lot 6
(L06-28). Mot pour mot : les phrases que B12 écrit (« Qu'est-ce que je vous mets ? », « Je vous mets autre chose ? ») ; les autres sont celles que le
module rend déjà (``QUESTION_MANQUE`` du guichet du banc). Une valeur portée par une question (la variante, l'accord sur le récapitulatif) n'a pas
de phrase propre : c'est la question qui la porte (``None``).
"""

from __future__ import annotations

from typing import Any

from api.services.mots_dits import liste_dite

MODE = "le mode de retrait"  # suivi de ses choix entre parenthèses : « le mode de retrait (à emporter ou en livraison) »

PHRASES_DU_MANQUE: dict[str, str | None] = {
    MODE: None,  # la phrase se fait des modes ouverts : ``phrase_du_manque``
    "l'adresse de livraison (numéro, rue et commune)": "Quelle est l'adresse de livraison ?",
    "la commune de livraison": "Dans quelle commune ?",
    "l'adresse (numéro et rue)": "Quelle est l'adresse de livraison ?",
    "les articles": "Qu'est-ce que je vous mets ?",
    "une variante à choisir": None,  # portée par la question variante du module
    "d'autres articles, ou qu'elle dise qu'elle a tout dit": "Je vous mets autre chose ?",
    "d'autres articles, ou qu'elle dise que c'est tout": "Je vous mets autre chose ?",
    "son accord sur le récapitulatif": None,  # portée par la question récapitulatif
    "le moyen de paiement": "Vous réglez comment ?",
    "le numéro de téléphone": "Quel est votre numéro de téléphone ?",
    "le prénom": "À quel nom je mets la commande ?",
    "une consigne pour le livreur": "Une consigne pour le livreur ?",
}
PORTEES_PAR_UNE_QUESTION = frozenset(k for k, v in PHRASES_DU_MANQUE.items() if v is None and k != MODE)


def valeur_fermee(manque: str) -> str | None:
    """La valeur fermée d'un « manque » de l'état (le mode porte ses choix entre parenthèses) ; ``None`` : hors de la liste fermée."""
    if manque.startswith(MODE):
        return MODE
    return manque if manque in PHRASES_DU_MANQUE else None


def phrase_du_manque(manque: str | None, modes: list[str] | None = None) -> str | None:
    """La phrase de ce qui manque, mot pour mot ; ``None`` : rien ne manque, ou c'est une question qui le porte. ``modes`` : les libellés des modes."""
    if not manque:
        return None
    valeur = valeur_fermee(manque)
    if valeur == MODE:
        dits = modes or [m.strip() for m in manque[len(MODE):].strip(" ()").replace(" ou ", ", ").split(",") if m.strip()]
        return f"{liste_dite(dits).capitalize()} ?" if dits else None
    return PHRASES_DU_MANQUE.get(valeur) if valeur else None


def texte_a_dire(p: dict[str, Any]) -> str | None:
    """La phrase de ce qui manque ENSUITE pour ce panier, quand aucune question n'attend : ce que le retour propose dans ``texte_a_dire``."""
    from api.services.commande import etat_pour_le_modele as E

    if p.get("question"):
        return None
    return phrase_du_manque(E.ce_qui_manque_ensuite(p, p.get(E.CLE_CONNU) or {}))
