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
