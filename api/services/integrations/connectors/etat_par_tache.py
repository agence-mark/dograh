"""[.mark] Module Restauration, lot 7 (W21) : un ÉTAT PAR TÂCHE déclaré (ses champs, ses compteurs), remis à zéro à chaque nouvelle tâche.

Une tâche est une suite de gestes qui mène à un résultat (une commande, une réservation). L'état vit dans la fiche de l'appel (``CLE``). Les champs et
les compteurs sont DÉCLARÉS par un ``Modele`` : écrire un champ non déclaré est une erreur de programmation (``ValueError``), jamais une clé qui s'ajoute
sans bruit. ``commencer`` avec un identifiant de tâche différent de la tâche en cours remet tout à zéro ; le même identifiant ne touche à rien.
La tâche en cours est lue par les mesures (``mesures.tache_en_cours``) : chaque mesure dit de quelle tâche elle vient.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CLE = "etat_par_tache"


@dataclass(frozen=True)
class Modele:
    champs: tuple[str, ...] = ()
    compteurs: tuple[str, ...] = ()


def _neuf(modele: Modele, tache: str, rang: int) -> dict[str, Any]:
    return {"tache": tache, "rang": rang, "champs": {c: None for c in modele.champs}, "compteurs": {c: 0 for c in modele.compteurs}}


def commencer(fiche: dict | None, modele: Modele, tache: str) -> dict[str, Any]:
    """L'état de la tâche ``tache`` : le même si elle est déjà en cours, un état à zéro sinon. Sans fiche : un état jetable."""
    if not isinstance(fiche, dict):
        return _neuf(modele, tache, 1)
    actuel = fiche.get(CLE)
    if isinstance(actuel, dict) and actuel.get("tache") == tache and set(actuel.get("champs", {})) == set(modele.champs):
        return actuel
    rang = int(actuel.get("rang", 0)) + 1 if isinstance(actuel, dict) else 1
    fiche[CLE] = _neuf(modele, tache, rang)
    return fiche[CLE]


def noter(etat: dict[str, Any], champ: str, valeur: Any) -> None:
    if champ not in etat["champs"]:
        raise ValueError(f"Champ de tâche non déclaré : {champ!r}")
    etat["champs"][champ] = valeur


def compter(etat: dict[str, Any], compteur: str, de: int = 1) -> int:
    if compteur not in etat["compteurs"]:
        raise ValueError(f"Compteur de tâche non déclaré : {compteur!r}")
    etat["compteurs"][compteur] += de
    return etat["compteurs"][compteur]
