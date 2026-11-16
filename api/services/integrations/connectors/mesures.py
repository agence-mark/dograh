"""[.mark] Module Restauration, lot 7 (W13) : les MESURES écrites par les outils, pour savoir pourquoi un appel n'aboutit pas (le Dashboard du lot 23 les lit).

Une mesure est une ligne de la fiche de l'appel, sous ``CLE``, jamais un texte libre :
``{"mesure": "<nom>", "outil": "<connecteur.action>", "tache": "<id de tâche ou None>", "detail": "<valeur de liste fermée ou None>"}``.
Les noms sont une liste fermée (``NOMS``) : une mesure hors liste n'est pas écrite (le Dashboard ne compte jamais une faute de frappe).
Aucun mot de métier ici : le mécanisme commun écrit et lit ; ce que chaque outil mesure est dit par son module (``restauration/mesures.py``).
⛔ Ne lève jamais : une mesure perdue ne casse pas l'appel.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

CLE = "mesures_des_outils"
CLE_TACHE = "etat_par_tache"  # la tâche en cours, écrite par ``etat_par_tache``

NOMS = frozenset(
    {
        # Commun à tous les outils (W21) : le type d'un échec, un délai dépassé, un échec répété.
        "outil.echec", "outil.delai_depasse", "outil.echec_repete", "outil.nom_rattache", "outil.nom_refuse",
        # Commande
        "commande.hors_zone", "commande.minimum_non_atteint", "commande.rupture", "commande.hors_catalogue", "commande.fermeture",
        "commande.moyen_refuse", "commande.enregistree", "commande.transmise", "commande.remise_appliquee", "commande.indisponible",
        # Réservation
        "reservation.enregistree", "reservation.complet", "reservation.refusee", "reservation.indisponible",
        # Service
        "service.passage_de_main", "service.message_laisse", "service.info_inconnue",
    }
)


def tache_en_cours(fiche: Any) -> str | None:
    etat = fiche.get(CLE_TACHE) if isinstance(fiche, dict) else None
    return str(etat.get("tache")) if isinstance(etat, dict) and etat.get("tache") else None


def ecrire(fiche: Any, mesure: str, outil: str, detail: str | None = None) -> bool:
    """Écrit une mesure. ``False`` : hors liste fermée, ou pas de fiche (un essai isolé)."""
    try:
        if mesure not in NOMS or not isinstance(fiche, dict):
            return False
        liste = fiche.setdefault(CLE, [])
        if not isinstance(liste, list):
            liste = fiche[CLE] = []
        liste.append({"mesure": mesure, "outil": outil, "tache": tache_en_cours(fiche), "detail": detail})
        return True
    except Exception:  # noqa: BLE001
        return False


def lues(fiche: Any) -> list[dict[str, Any]]:
    brut = fiche.get(CLE) if isinstance(fiche, dict) else None
    return [m for m in brut if isinstance(m, dict) and m.get("mesure") in NOMS] if isinstance(brut, list) else []


def compte(fiche: Any) -> dict[str, int]:
    """Le décompte par nom de mesure (ce que le Dashboard additionne d'un appel à l'autre)."""
    return dict(Counter(m["mesure"] for m in lues(fiche)))
