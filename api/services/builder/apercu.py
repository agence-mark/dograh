"""[.mark] Builder, lot M (pièce 4 de Cognigy, licence MIT) : l'aperçu SANS EFFET avant de revenir à une version.

Dit ce qui sera perdu (ce que le brouillon actuel a de plus ou de différent) et ce qui sera retrouvé, avant que la personne
confirme. Ne lit que le brouillon actuel et l'instantané : rien n'est écrit. La restauration elle-même (``revue.restaurer``)
n'est pas changée.
"""

from __future__ import annotations

from typing import Any

from api.services.builder import brouillon, instantane, revue, stock

LISTE_MAX = 40


def _noeuds(graphe: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {str(n.get("id")): n for n in (graphe or {}).get("nodes") or []}


def _liaisons(graphe: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {str(e.get("id") or f"{e.get('source')}-{e.get('target')}"): e for e in (graphe or {}).get("edges") or []}


def _nom(noeud: dict[str, Any]) -> str:
    return str((noeud.get("data") or {}).get("name") or noeud.get("id") or "?")


def _champs_differents(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    donnees_a, donnees_b = a.get("data") or {}, b.get("data") or {}
    return sorted(c for c in set(donnees_a) | set(donnees_b) if donnees_a.get(c) != donnees_b.get(c))


def _decrire_liaison(liaison: dict[str, Any]) -> str:
    return f"{liaison.get('source')} -> {liaison.get('target')}"


# Identifiants neutres du ``genre`` d'une ligne : l'écran les traduit (jamais de texte français côté serveur).
GENRES = ("node_added", "node_changed", "node_removed", "link_added", "link_changed", "link_removed")


def comparer(actuel: dict[str, Any] | None, cible: dict[str, Any] | None) -> dict[str, Any]:
    """``sera_perdu`` : ce qui est dans l'actuel et pas (ou pas pareil) dans la cible ; ``sera_retrouve`` : l'inverse."""
    ici, la = _noeuds(actuel), _noeuds(cible)
    perdu: list[dict[str, Any]] = []
    retrouve: list[dict[str, Any]] = []
    inchanges = 0
    for identifiant, noeud in ici.items():
        if identifiant not in la:
            perdu.append({"genre": "node_added", "cible": identifiant, "nom": _nom(noeud)})
            continue
        champs = _champs_differents(noeud, la[identifiant])
        if champs:
            perdu.append({"genre": "node_changed", "cible": identifiant, "nom": _nom(noeud), "champs": champs})
        else:
            inchanges += 1
    for identifiant, noeud in la.items():
        if identifiant not in ici:
            retrouve.append({"genre": "node_removed", "cible": identifiant, "nom": _nom(noeud)})
    ici_l, la_l = _liaisons(actuel), _liaisons(cible)
    for identifiant, liaison in ici_l.items():
        if identifiant not in la_l:
            perdu.append({"genre": "link_added", "cible": identifiant, "nom": _decrire_liaison(liaison)})
        elif (liaison.get("data") or {}) != (la_l[identifiant].get("data") or {}):
            perdu.append({"genre": "link_changed", "cible": identifiant, "nom": _decrire_liaison(liaison)})
    for identifiant, liaison in la_l.items():
        if identifiant not in ici_l:
            retrouve.append({"genre": "link_removed", "cible": identifiant, "nom": _decrire_liaison(liaison)})
    return {
        "sera_perdu": perdu[:LISTE_MAX],
        "sera_retrouve": retrouve[:LISTE_MAX],
        "total_perdu": len(perdu),
        "total_retrouve": len(retrouve),
        "inchanges": inchanges,
    }


async def apercu_de_la_restauration(organisation: int, workflow: Any, numero: int, user: Any = None) -> dict[str, Any]:
    ligne = await stock.lire(organisation, revue._cle(workflow.id, numero))  # noqa: SLF001
    if ligne is None or not ligne.get("avant") or ligne.get("branche") != await revue._branche_ouverte(workflow.id):  # noqa: SLF001
        raise revue.ErreurRevue(f"Unknown version: {numero}.")  # SA-L3c : l'instantané d'une autre branche
    actuel, version = await brouillon.source_courante(workflow)
    # Sous-lot 7 : famille par famille, ce qui est gardé et ce qui changerait (des noms et des comptes, jamais une valeur).
    maintenant = await instantane.capturer(organisation, workflow, user=user)
    return {
        "numero": numero,
        "cause": ligne.get("cause"),
        "date": ligne.get("date"),
        "version_actuelle": version,
        "familles": instantane.comparer_les_familles(ligne, maintenant),
        **comparer(actuel, ligne["avant"]),
    }
