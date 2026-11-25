"""[.mark] Les phrases que le CODE dit mot pour mot dans la commande : UNE place, chacune avec l'exception du plan qui la permet
(plan final Partie 1, lot 1, n° 82, 86, L2).

« C'est le modèle qui parle, sauf exception » (Evan, 17/11 et 23/11). Le code ne dit mot pour mot que : la relecture, le total, le numéro, la
confirmation, le fait accompli qui engage (enregistrée, annulée), les phrases réglables à l'écran (DC4, DC10). Ranger une phrase ici ne la rend PAS permise : chaque entrée nomme son exception, et un test refuse toute exception hors de cette liste fermée.
Les phrases du code qui ne relèvent d'aucune exception sont dans ``api/outils/phrases-a-rendre-au-modele.md`` (le lot 7 les rend au modèle).
"""

from __future__ import annotations

from dataclasses import dataclass

EXCEPTION_RELECTURE = "relecture"
EXCEPTION_TOTAL = "total"
EXCEPTION_NUMERO = "numero"
EXCEPTION_CONFIRMATION = "confirmation"
EXCEPTION_FAIT_ACCOMPLI = "fait accompli qui engage"
EXCEPTION_DC4 = "DC4"
EXCEPTIONS_DU_PLAN = frozenset({EXCEPTION_RELECTURE, EXCEPTION_TOTAL, EXCEPTION_NUMERO, EXCEPTION_CONFIRMATION, EXCEPTION_FAIT_ACCOMPLI, EXCEPTION_DC4})


@dataclass(frozen=True)
class PhraseDuCode:
    texte: str
    exception: str


PHRASES = {
    "reservation_enregistree": PhraseDuCode("C'est réservé pour {personnes}, {quand}, au nom de {prenom}.", EXCEPTION_FAIT_ACCOMPLI),  # 7b-C3 : la réservation faite engage ; dite par le code (``avant``)
    "reservation_modifiee": PhraseDuCode("C'est modifié : {quand}, {personnes}.", EXCEPTION_FAIT_ACCOMPLI),
    "reservation_annulee": PhraseDuCode("C'est annulé.", EXCEPTION_FAIT_ACCOMPLI),
    "relecture_de_la_reservation": PhraseDuCode("Je vous réserve pour {personnes}, {quand}, au nom de {prenom}. {question}", EXCEPTION_RELECTURE),  # 7b-C3 : la relecture de la réservation, avec la question du numéro réglée à l'écran si elle existe
    "relecture_du_changement": PhraseDuCode("Je change votre réservation : {changes}. C'est bon ?", EXCEPTION_RELECTURE),
    "annulation_de_la_reservation": PhraseDuCode("Je peux aussi la déplacer. Vous voulez annuler la réservation {quand} pour {personnes} ?", EXCEPTION_DC4),  # B5 : le déplacement est offert par la question du code, règle du métier
    "quel_numero_je_note": PhraseDuCode("Quel numéro je note ?", EXCEPTION_NUMERO),  # DC10 : après un refus du numéro proposé, une seule fois ; le numéro est une valeur que le code porte
    "numero_affiche_propose": PhraseDuCode("Je note le numéro qui s'affiche, c'est bon ?", EXCEPTION_NUMERO),  # défaut de la question du registre ``numero_affiche`` (le réglage ``question_numero_affiche`` passe avant)
    "relecture_complete": PhraseDuCode("Je vous relis : {corps}. Cela fait {total}. C'est bon ?", EXCEPTION_RELECTURE),  # LA relecture, la première fois : tout est relu, avec le total
    "relecture_apres_changement": PhraseDuCode("{changes}Cela fait maintenant {total}. C'est bon ?", EXCEPTION_RELECTURE),  # une correction : seulement ce qui a changé, avec le total
    "ligne_passe_a": PhraseDuCode("{nom} passe à {quantite}", EXCEPTION_RELECTURE),  # un morceau de ce qui a changé, relu
    "note_de_moitie": PhraseDuCode("sans {ingredient} sur la moitié {moitie}", EXCEPTION_RELECTURE),  # écrite sur la ligne, relue par le code dans la relecture, imprimée au ticket
}

def reservation_enregistree(*, personnes: str, quand: str, prenom: str) -> str:
    """La réservation vient d'être enregistrée : ``personnes`` (« deux personnes ») et ``quand`` sont déjà dits."""
    return PHRASES["reservation_enregistree"].texte.format(personnes=personnes, quand=quand, prenom=prenom)


def reservation_modifiee(*, quand: str, personnes: str) -> str:
    return PHRASES["reservation_modifiee"].texte.format(quand=quand, personnes=personnes)


def reservation_annulee() -> str:
    return PHRASES["reservation_annulee"].texte


def relecture_de_la_reservation(*, personnes: str, quand: str, prenom: str, question: str | None = None) -> str:
    """La relecture avant d'enregistrer : ``question`` est celle que le restaurant a réglée (numéro qui s'affiche), sinon « C'est bon ? »."""
    return PHRASES["relecture_de_la_reservation"].texte.format(personnes=personnes, quand=quand, prenom=prenom, question=question or "C'est bon ?")


def relecture_du_changement(changes: str) -> str:
    """Le récapitulatif d'un changement : ``changes`` ce qui change, déjà dit."""
    return PHRASES["relecture_du_changement"].texte.format(changes=changes)


def annulation_de_la_reservation(*, quand: str, personnes: str) -> str:
    """La question avant d'annuler : elle offre aussi le déplacement."""
    return PHRASES["annulation_de_la_reservation"].texte.format(quand=quand, personnes=personnes)


def note_de_moitie(*, ingredient: str, moitie: str) -> str:
    """Le retrait d'un ingrédient sur une seule moitié : la note de la ligne, relue à la personne dans la relecture."""
    return PHRASES["note_de_moitie"].texte.format(ingredient=ingredient, moitie=moitie)


def quel_numero_je_note() -> str:
    return PHRASES["quel_numero_je_note"].texte


def numero_affiche_propose(reglee: str | None = None) -> str:
    """La question du numéro qui s'affiche : celle que le restaurant a réglée (``question_numero_affiche``), sinon la phrase de base."""
    return (reglee or "").strip() or PHRASES["numero_affiche_propose"].texte


def relecture_complete(*, corps: str, total: str) -> str:
    """La relecture entière : ``corps`` les lignes, le mode, l'heure et ce qui est offert, déjà dits ; ``total`` le montant en lettres."""
    return PHRASES["relecture_complete"].texte.format(corps=corps, total=total)


def relecture_apres_changement(*, changes: str, total: str) -> str:
    """La relecture après une correction : ``changes`` ce qui a changé (déjà dit, avec son point et son espace, ou vide), puis le total."""
    return PHRASES["relecture_apres_changement"].texte.format(changes=changes, total=total)


def ligne_passe_a(*, nom: str, quantite: str) -> str:
    return PHRASES["ligne_passe_a"].texte.format(nom=nom, quantite=quantite)
