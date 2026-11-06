"""[.mark] U3 sexies point 2 : le filtrage de la réponse d'un outil HTTP et sa copie dans la fiche de l'appel."""

from __future__ import annotations

from typing import Any

ABSENT = object()


def lire_le_chemin(donnees: Any, chemin: str) -> Any:
    """La valeur au chemin pointé (``client.id``, ``items.0.nom``), ``ABSENT`` s'il n'existe pas."""
    courant = donnees
    for cle in str(chemin).split("."):
        if isinstance(courant, dict) and cle in courant:
            courant = courant[cle]
        elif isinstance(courant, list) and cle.isdigit() and int(cle) < len(courant):
            courant = courant[int(cle)]
        else:
            return ABSENT
    return courant


def _poser(cible: dict[str, Any], chemin: list[str], valeur: Any) -> None:
    for cle in chemin[:-1]:
        cible = cible.setdefault(cle, {})
    cible[chemin[-1]] = valeur


def filtrer(donnees: Any, chemins: list[str] | None) -> Any:
    """Ne garde que les chemins demandés. Liste vide : la réponse entière. Un chemin absent est simplement omis."""
    chemins = [c for c in (chemins or []) if str(c).strip()]
    if not chemins:
        return donnees
    gardees: dict[str, Any] = {}
    for chemin in chemins:
        valeur = lire_le_chemin(donnees, chemin)
        if valeur is not ABSENT:
            _poser(gardees, str(chemin).split("."), valeur)
    return gardees


def copier_dans_la_fiche(
    donnees: Any, copies: list[dict[str, Any]] | None, fiche: dict[str, Any] | None
) -> dict[str, Any]:
    """Recopie dans ``fiche`` les valeurs de la réponse (lue en entier, avant tout filtrage). Rend ce qui a été copié.
    Une valeur absente ne copie rien (la clé de la fiche n'est ni créée ni effacée)."""
    copiees: dict[str, Any] = {}
    for copie in copies or []:
        valeur = lire_le_chemin(donnees, str(copie.get("chemin") or ""))
        cle = str(copie.get("cle") or "")
        if valeur is ABSENT or not cle:
            continue
        copiees[cle] = valeur
        if isinstance(fiche, dict):
            fiche[cle] = valeur
    return copiees
