"""[.mark] Builder partie 3, sous-lot 3 (SE-12 / D-4) : « Ce qui change » de la fenêtre Publier, ligne par ligne, avant et après.

Compare le BROUILLON à la version publiée : une ligne par étape ajoutée, retirée ou changée (une ligne par champ changé, avec
le texte avant et le texte après), par liaison et par réglage de l'agent. Pur : rien n'est lu en base ici, rien n'est écrit.
Les valeurs sont raccourcies (``LONGUEUR_MAX``) et tout champ au nom de secret est remplacé par ``***`` (défense en profondeur).
Les genres sont des identifiants neutres : l'écran les traduit (jamais de texte français côté serveur).
"""

from __future__ import annotations

import json
from typing import Any

LIGNES_MAX = 60
LONGUEUR_MAX = 600
SENT_UN_SECRET = ("api_key", "token", "secret", "password", "credential")
# Champs de position ou de mise en page : un déplacement dans le graphe n'est pas un changement de l'agent.
IGNORES = frozenset({"position", "selected", "dragging", "measured", "width", "height"})


def _texte(valeur: Any) -> str:
    if valeur is None:
        return ""
    brut = valeur if isinstance(valeur, str) else json.dumps(valeur, ensure_ascii=False, sort_keys=True, default=str)
    return brut if len(brut) <= LONGUEUR_MAX else brut[:LONGUEUR_MAX] + "…"


def _masque(champ: str, valeur: Any) -> Any:
    return "***" if any(m in champ.lower() for m in SENT_UN_SECRET) else valeur


def _noeuds(graphe: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {str(n.get("id")): n for n in (graphe or {}).get("nodes") or [] if isinstance(n, dict)}


def _liaisons(graphe: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {
        str(e.get("id") or f"{e.get('source')}-{e.get('target')}"): e for e in (graphe or {}).get("edges") or [] if isinstance(e, dict)
    }


def _nom(noeud: dict[str, Any]) -> str:
    return str((noeud.get("data") or {}).get("name") or noeud.get("id") or "?")


def _ligne(genre: str, ou: str, champ: str | None = None, avant: Any = None, apres: Any = None) -> dict[str, Any]:
    return {"genre": genre, "ou": ou, "champ": champ, "avant": _texte(_masque(champ or "", avant)), "apres": _texte(_masque(champ or "", apres))}


def calculer(
    brouillon: dict[str, Any] | None,
    publie: dict[str, Any] | None,
    configurations_brouillon: dict[str, Any] | None = None,
    configurations_publiees: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """``lignes`` : les changements (au plus ``LIGNES_MAX``) ; ``total`` : leur nombre réel."""
    lignes: list[dict[str, Any]] = []
    nouveaux, anciens = _noeuds(brouillon), _noeuds(publie)
    for identifiant, noeud in nouveaux.items():
        if identifiant not in anciens:
            lignes.append(_ligne("node_added", _nom(noeud)))
            continue
        ancien_data, nouveau_data = anciens[identifiant].get("data") or {}, noeud.get("data") or {}
        for champ in sorted((set(ancien_data) | set(nouveau_data)) - IGNORES):
            if ancien_data.get(champ) != nouveau_data.get(champ):
                lignes.append(_ligne("node_changed", _nom(noeud), champ, ancien_data.get(champ), nouveau_data.get(champ)))
    for identifiant, noeud in anciens.items():
        if identifiant not in nouveaux:
            lignes.append(_ligne("node_removed", _nom(noeud)))
    nouvelles, anciennes = _liaisons(brouillon), _liaisons(publie)
    decrire = lambda e: f"{e.get('source')} -> {e.get('target')}"  # noqa: E731
    for identifiant, liaison in nouvelles.items():
        if identifiant not in anciennes:
            lignes.append(_ligne("link_added", decrire(liaison)))
        elif (liaison.get("data") or {}) != (anciennes[identifiant].get("data") or {}):
            lignes.append(_ligne("link_changed", decrire(liaison), "data", anciennes[identifiant].get("data"), liaison.get("data")))
    for identifiant, liaison in anciennes.items():
        if identifiant not in nouvelles:
            lignes.append(_ligne("link_removed", decrire(liaison)))
    avant_c, apres_c = configurations_publiees or {}, configurations_brouillon or {}
    for cle in sorted(set(avant_c) | set(apres_c)):
        if avant_c.get(cle) != apres_c.get(cle):
            lignes.append(_ligne("setting_changed", cle, cle, avant_c.get(cle), apres_c.get(cle)))
    return {"lignes": lignes[:LIGNES_MAX], "total": len(lignes)}
