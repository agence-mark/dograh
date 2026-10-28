"""[.mark] passages-fiables (lot G) : les lignes des pages « À trier » et « Alertes » (et de la route que le portail lira).

Prend les lignes que ``db/tri_client`` a lues (bornées, scopées par organisation) et en fait une ligne par signalement ou par
alerte. Rien n'est recopié : tout vient du run.
"""

from __future__ import annotations

from typing import Any

from api.services.tri import donnees


def _date(valeur: Any) -> str | None:
    return valeur.isoformat() if hasattr(valeur, "isoformat") else (str(valeur) if valeur else None)


def _en_tete(ligne: dict) -> dict:
    return {
        "run_id": ligne["run_id"],
        "workflow_id": ligne["workflow_id"],
        "workflow_nom": ligne["workflow_nom"],
        "cree_le": _date(ligne["cree_le"]),
    }


def lignes_de_tri(runs: list[dict], statut: str | None = None) -> list[dict]:
    """Une ligne par signalement (agent ou code), avec son statut de tri. ``statut`` : ne garde que celui-là."""
    sortie = []
    for run in runs:
        for s in donnees.lire_les_signalements(run["extrait"]):
            etat = donnees.statut_d_un_signalement(run["annotations"], s["id"])
            if statut is None or etat == statut:
                sortie.append({**_en_tete(run), **s, "statut": etat})
    return sortie


def lignes_d_alertes(runs: list[dict]) -> list[dict]:
    sortie = []
    for run in runs:
        for a in donnees.lire_les_alertes(run["extrait"]):
            sortie.append({**_en_tete(run), **a})
    return sortie
