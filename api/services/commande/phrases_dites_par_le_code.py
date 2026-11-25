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
    "annulation_confirmee": PhraseDuCode("Je vous confirme l'annulation de votre commande.", EXCEPTION_FAIT_ACCOMPLI),  # DC4, second temps : l'annulation faite engage
    "annulee_en_cours": PhraseDuCode("Je ne l'enregistre pas.", EXCEPTION_FAIT_ACCOMPLI),  # L2 : la commande en cours est annulée avant son enregistrement : le fait qui engage
    "annulation_demandee": PhraseDuCode("Vous êtes sûr de vouloir annuler votre commande{de_montant} ?", EXCEPTION_DC4),  # texte de secours du repli seulement (Q2 = A : le modèle pose la question) ; sa place dépend de la question R
    "changement_avec_total": PhraseDuCode("C'est changé : votre commande fait maintenant {total}.", EXCEPTION_TOTAL),
    "changement_sans_total": PhraseDuCode("C'est changé dans votre commande.", EXCEPTION_FAIT_ACCOMPLI),
    "enregistree_avec_delai": PhraseDuCode("Votre commande est enregistrée, elle sera {etat} {quand}.", EXCEPTION_FAIT_ACCOMPLI),
    "enregistree_retrouvee_quand": PhraseDuCode("Votre commande est enregistrée pour {quand}.", EXCEPTION_FAIT_ACCOMPLI),
    "enregistree_retrouvee": PhraseDuCode("Votre commande est enregistrée.", EXCEPTION_FAIT_ACCOMPLI),
    "deja_enregistree_pour": PhraseDuCode("Votre commande est déjà enregistrée pour {quand}.", EXCEPTION_FAIT_ACCOMPLI),  # le panier (ou l'anti-doublon) retombe sur une commande déjà prise : le fait accompli qui engage
    "deja_enregistree": PhraseDuCode("Votre commande est déjà enregistrée.", EXCEPTION_FAIT_ACCOMPLI),
}

TEXTE_ANNULATION_CONFIRMEE = PHRASES["annulation_confirmee"].texte
TEXTE_ANNULEE_EN_COURS = PHRASES["annulee_en_cours"].texte


def annulation_demandee(montant: str | None) -> str:
    """DC4, premier temps : le total de la commande enregistrée, en lettres."""
    return PHRASES["annulation_demandee"].texte.format(de_montant=f" de {montant}" if montant else "")


def changement(total: str | None) -> str:
    """La commande enregistrée vient d'être changée en caisse : son nouveau total quand il est connu."""
    return PHRASES["changement_avec_total"].texte.format(total=total) if total else PHRASES["changement_sans_total"].texte


def enregistree_avec_delai(etat: str, quand: str) -> str:
    return PHRASES["enregistree_avec_delai"].texte.format(etat=etat, quand=quand)


def deja_enregistree(quand_dit: str | None) -> str:
    """« Votre commande est déjà enregistrée » (avec l'heure annoncée quand elle est connue) : dite par la fin de la commande et par l'anti-doublon de la source."""
    return PHRASES["deja_enregistree_pour"].texte.format(quand=quand_dit) if quand_dit else PHRASES["deja_enregistree"].texte


def enregistree_retrouvee(quand_dit: str | None) -> str:
    return PHRASES["enregistree_retrouvee_quand"].texte.format(quand=quand_dit) if quand_dit else PHRASES["enregistree_retrouvee"].texte
