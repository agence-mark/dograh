"""[.mark] Lot 7b-C3 : les textes de secours de la réservation (feuille : rien de ``services.reservation`` n'y est importé, la base et le moteur la lisent tous deux).

Un texte de secours est la phrase qu'un refus ou une question portait déjà dans ``suggestion`` : le modèle ne la reçoit plus (R = A, le repli du code ne la dit que lorsque le
modèle s'est tu deux fois sur le refus). Chaque fonction est pure et ne lit que les faits du refus (plus les mots dits des nombres) : ``resultat.suggestion == texte(faits)`` est ce que
prouve le test de chaque refus. Un texte qui lit une valeur absente des faits la fait ajouter au refus.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

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
    return "Pour un groupe de cette taille, il faut appeler le restaurant."


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
