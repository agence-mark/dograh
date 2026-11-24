"""[.mark] Clôture de la Partie 1, lot B5 (inventaire C6, audit des textes § 2.4) : le retour d'une fiche, allégé au moment où il part vers le modèle.

Le retour portait des clés que le modèle n'utilise jamais : le code INSEE, le code postal et le département de la commune, l'identifiant d'une zone ou
d'un article, les montants en centimes (``total``, ``sous_total``, ``frais``, ``minimum``), le délai en minutes, ``numero_s_affiche``, la liste des
cases liées non exécutées. Elles grossissaient l'historique et mettaient des chiffres sous ses yeux, qu'il recopiait (« a_dire : jamais un prix »).
Ce que la personne doit entendre de chiffré, le code le dit lui-même (relecture, total, prix, minimum, délai).

Le code garde le retour entier (la parole, le constat, les tests le lisent) : seule la COPIE envoyée au modèle est allégée. La question en attente
(son numéro, son texte) et les refus (leur consigne) ne sont jamais touchés. ⛔ Ne lève jamais : dans le doute, le retour tel quel.
"""

from __future__ import annotations

import copy
from typing import Any

# Jamais utiles au modèle, où qu'elles soient.
CLES_RETIREES = frozenset({
    "insee", "code_postal", "departement", "sous_total", "frais", "gratuite_des", "numero_s_affiche", "cases_non_executees_car_liees", "etoile",
    "plusieurs_tailles",
})
# Retirées quand elles portent un nombre (un montant en centimes, des minutes, un identifiant) : leur texte, s'il y en a un, reste.
CLES_CHIFFREES = frozenset({"total", "minimum", "delai", "montant", "id", "ref"})
# Jamais touchés : la question en attente et les refus (leurs consignes).
SOUS_ARBRES_GARDES = frozenset({"question", "refus"})
CLE_DU = "du_de_la_fiche"  # lot 7a : le constat du code (``du.Du``), lu par la parole, jamais par le modèle


def _alleger(valeur: Any) -> Any:
    if isinstance(valeur, dict):
        sortie = {}
        for cle, v in valeur.items():
            if cle == CLE_DU:
                continue
            if cle in SOUS_ARBRES_GARDES:
                sortie[cle] = v
            elif cle in CLES_RETIREES or (cle in CLES_CHIFFREES and isinstance(v, (int, float)) and not isinstance(v, bool)):
                continue
            elif cle in ("ref",) and isinstance(v, str):
                continue
            else:
                sortie[cle] = _alleger(v)
        return sortie
    if isinstance(valeur, list):
        return [_alleger(v) for v in valeur]
    return valeur


def pour_le_modele(retour: Any) -> Any:
    """La copie du retour d'une fiche que le modèle lit ; le retour lui-même n'est jamais modifié."""
    try:
        return _alleger(copy.deepcopy(retour)) if isinstance(retour, dict) else retour
    except Exception:  # noqa: BLE001
        return retour
