"""[.mark] Clôture de la Partie 1, lot B2 (audit du code M3, M4) : ce qui est dû à la personne, constaté à la sortie de TOUTE fiche, commande et
réservation (revue d'ingénierie, point 6 : même faute, même traitement).

Deux constats, posés dans le retour, lus par la parole (``actions_communes.parole``) :
* ``texte_a_dire`` : ce qui manque, quand aucune question n'attend, à la sortie d'une fiche refusée, rejouée ou exécutée (avant : seulement
  exécutée sans refus ; 42 cas rouges du test des combinaisons). Une seule place, une seule fonction par métier ;
* ``rien_change`` : la fiche n'a rien changé de ce que la personne vit ; elle vaut une phrase sans outil (règle 2 : trace 508, « C'est noté » sur
  cinq fiches vides de suite).
"""

from __future__ import annotations

import copy
from typing import Any, Callable

RIEN_CHANGE = "rien_change"
A_FAIRE_RIEN_CHANGE = "ta fiche n'a rien changé : ta phrase n'a pas été dite ; réponds à ce que la personne vient de dire"
# La tenue interne (registre des questions, mémoire des fiches, tour) : elle bouge sans que rien ne change pour la personne.
TENUE = ("tour_de_l_appel", "question", "questions_ouvertes", "numeros_des_questions", "prochain_q", "hesitations_nees", "fiches_executees",
         "version")  # B4 : le compteur de version du panier bouge sur un changement sans effet (« mettez-en deux » quand il y en a deux)


def ce_qui_se_voit(dossier: dict[str, Any]) -> Any:
    """L'état du dossier tel que la personne le vit (sans la tenue interne), et la question posée (numéro, texte) : deux valeurs égales avant et
    après une fiche = elle n'a rien changé."""
    q = dossier.get("question") if isinstance(dossier.get("question"), dict) else {}
    return copy.deepcopy({**{k: v for k, v in dossier.items() if k not in TENUE}, "question": (q.get("id"), q.get("texte"))})


def constater(retour: dict[str, Any], vu_avant: Any, dossier: dict[str, Any], texte_du_manque: Callable[[dict[str, Any]], str | None]) -> dict[str, Any]:
    """Pose ce qui est dû dans le retour d'une fiche (``texte_a_dire``, ``rien_change``). ⛔ Ne lève jamais : dans le doute, le retour tel quel."""
    try:
        if not isinstance(dossier.get("question"), dict) and not retour.get("texte_a_dire"):
            phrase = texte_du_manque(dossier)
            if phrase:
                retour["texte_a_dire"] = phrase
        if not retour.get("refus") and retour.get("statut") != "REJETEE" and ce_qui_se_voit(dossier) == vu_avant:
            retour[RIEN_CHANGE] = True
            retour["a_faire"] = " ; ".join(x for x in (A_FAIRE_RIEN_CHANGE, retour.get("a_faire")) if x)
    except Exception:  # noqa: BLE001
        pass
    return retour
