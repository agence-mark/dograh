"""[.mark] Les phrases que le CODE dit mot pour mot dans la commande : UNE place, chacune avec l'exception du plan qui la permet
(plan final Partie 1, lot 1, n° 82, 86, L2).

« C'est le modèle qui parle, sauf exception » (Evan, 17/11 et 23/11). Le code ne dit mot pour mot que : la relecture, le total, le numéro, la
confirmation, le fait accompli qui engage (enregistrée, annulée), les phrases réglables à l'écran (DC4, DC10) et le repli quand le modèle n'a pas la main
(panne). Ranger une phrase ici ne la rend PAS permise : chaque entrée nomme son exception, et un test refuse toute exception hors de cette liste fermée.
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
EXCEPTION_DC5 = "DC5"
EXCEPTION_PANNE = "repli : le modèle n'a pas la main"
EXCEPTIONS_DU_PLAN = frozenset({EXCEPTION_RELECTURE, EXCEPTION_TOTAL, EXCEPTION_NUMERO, EXCEPTION_CONFIRMATION, EXCEPTION_FAIT_ACCOMPLI, EXCEPTION_DC4,
                                EXCEPTION_DC5, EXCEPTION_PANNE})


@dataclass(frozen=True)
class PhraseDuCode:
    texte: str
    exception: str


PHRASES = {
    "nouvelle_commande": PhraseDuCode("Votre commande est annulée, je ne peux plus rien y ajouter. Voulez-vous en passer une nouvelle ?", EXCEPTION_DC5),
    "annulation_confirmee": PhraseDuCode("Je vous confirme l'annulation de votre commande.", EXCEPTION_DC4),
    "annulation_demandee": PhraseDuCode("Vous êtes sûr de vouloir annuler votre commande{de_montant} ?", EXCEPTION_DC4),
    "changement_avec_total": PhraseDuCode("C'est changé : votre commande fait maintenant {total}.", EXCEPTION_TOTAL),
    "changement_sans_total": PhraseDuCode("C'est changé dans votre commande.", EXCEPTION_FAIT_ACCOMPLI),
    "enregistree_avec_delai": PhraseDuCode("Votre commande est enregistrée, elle sera {etat} {quand}.", EXCEPTION_FAIT_ACCOMPLI),
    "enregistree_retrouvee_quand": PhraseDuCode("Votre commande est enregistrée pour {quand}.", EXCEPTION_FAIT_ACCOMPLI),
    "enregistree_retrouvee": PhraseDuCode("Votre commande est enregistrée.", EXCEPTION_FAIT_ACCOMPLI),
    "panne_commande_transmise": PhraseDuCode("Je n'arrive pas à enregistrer votre commande pour le moment. Je la transmets à l'équipe, qui vous rappelle.", EXCEPTION_PANNE),
    "panne_sans_commande": PhraseDuCode("Je n'arrive pas à faire cela pour le moment.", EXCEPTION_PANNE),
}

TEXTE_NOUVELLE_COMMANDE = PHRASES["nouvelle_commande"].texte
TEXTE_ANNULATION_CONFIRMEE = PHRASES["annulation_confirmee"].texte
PANNE_COMMANDE_TRANSMISE = PHRASES["panne_commande_transmise"].texte
PANNE_SANS_COMMANDE = PHRASES["panne_sans_commande"].texte


def annulation_demandee(montant: str | None) -> str:
    """DC4, premier temps : le total de la commande enregistrée, en lettres."""
    return PHRASES["annulation_demandee"].texte.format(de_montant=f" de {montant}" if montant else "")


def changement(total: str | None) -> str:
    """La commande enregistrée vient d'être changée en caisse : son nouveau total quand il est connu."""
    return PHRASES["changement_avec_total"].texte.format(total=total) if total else PHRASES["changement_sans_total"].texte


def enregistree_avec_delai(etat: str, quand: str) -> str:
    return PHRASES["enregistree_avec_delai"].texte.format(etat=etat, quand=quand)


def enregistree_retrouvee(quand_dit: str | None) -> str:
    return PHRASES["enregistree_retrouvee_quand"].texte.format(quand=quand_dit) if quand_dit else PHRASES["enregistree_retrouvee"].texte
