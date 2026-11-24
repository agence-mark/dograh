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
import json
from typing import Any, Callable

from loguru import logger


RIEN_CHANGE = "rien_change"
A_FAIRE_RIEN_CHANGE = "ta fiche n'a rien changé : ta phrase n'a pas été dite ; réponds à ce que la personne vient de dire"
# La tenue interne (registre des questions, mémoire des fiches, tour) : elle bouge sans que rien ne change pour la personne.
TENUE = ("tour_de_l_appel", "question", "questions_ouvertes", "numeros_des_questions", "prochain_q", "hesitations_nees", "fiches_executees",
         "version", "prochaine_ligne", "relecture", "boucle", "hesitation_fermee", "allergie_donnee_avant", "derniere_question_fermee")  # B4 : le compteur de version du panier bouge sur un changement sans effet (« mettez-en deux » quand il y en a deux)


def ce_qui_se_voit(dossier: dict[str, Any]) -> Any:
    """L'état du dossier tel que la personne le vit (sans la tenue interne), et la question posée (numéro, texte) : deux valeurs égales avant et
    après une fiche = elle n'a rien changé."""
    q = dossier.get("question") if isinstance(dossier.get("question"), dict) else {}
    vue = {k: v for k, v in dossier.items() if k not in TENUE}
    if isinstance(vue.get("lignes"), list):
        vue["lignes"] = [{k: v for k, v in l.items() if k != "n"} if isinstance(l, dict) else l for l in vue["lignes"]]  # le numéro d'une ligne est de la tenue : vider puis redire la même ne change rien
    return copy.deepcopy({**vue, "question": (q.get("id"), q.get("texte"))})


def _articles_par_ref(lignes: Any) -> dict[str, int]:
    """Les articles d'un dossier (référence → quantité totale), sans leurs précisions : de quoi dire si la commande a avancé (RC6)."""
    compte: dict[str, int] = {}
    for l in lignes or []:
        if isinstance(l, dict):
            compte[str(l.get("ref"))] = compte.get(str(l.get("ref")), 0) + int(l.get("quantite") or 0)
    return compte


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
        from api.services.actions_communes import journal_du_dit as J

        q = dossier.get("question") if isinstance(dossier.get("question"), dict) else {}
        bloquant = (retour.get("faits") or {}).get("fait_bloquant")
        signature = [q.get("texte"), json.dumps(bloquant, sort_keys=True, default=str) if bloquant else None, retour.get("raison")]
        memes_lignes = _articles_par_ref((vu_avant or {}).get("lignes")) == _articles_par_ref(ce_qui_se_voit(dossier).get("lignes"))  # la commande n'avance pas : mêmes articles, mêmes quantités
        if J.boucle(dossier, signature, memes_lignes) and J.A_FAIRE_SORTIE not in str(retour.get("a_faire") or ""):
            retour["a_faire"] = " ; ".join(x for x in (J.A_FAIRE_SORTIE, retour.get("a_faire")) if x)  # RC6 : la même chose trois fois sans issue : la sortie
    except Exception:  # noqa: BLE001
        logger.exception("[.mark] du : la sortie d'une boucle n'a pas pu être lue")
    return retour
