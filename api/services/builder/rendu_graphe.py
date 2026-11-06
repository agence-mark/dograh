"""[.mark] Builder, lot M (pièce 4 de Cognigy, licence MIT) : le graphe d'un agent rendu PAR LE CODE, en texte et en Mermaid.

Aucun jeton, aucun appel de modèle : le même graphe donne toujours le même rendu. Sert au builder (pour « voir » ce qu'il
construit sans relire du code) et à une personne (le Mermaid se colle dans n'importe quel éditeur compatible).
"""

from __future__ import annotations

import re
from typing import Any

LIBELLE_MAX = 60


def _nom(noeud: dict[str, Any]) -> str:
    donnees = noeud.get("data") or {}
    return str(donnees.get("name") or noeud.get("id") or "?")[:LIBELLE_MAX]


def _liaisons_de(graphe: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    sortantes: dict[str, list[dict[str, Any]]] = {}
    for liaison in graphe.get("edges") or []:
        sortantes.setdefault(str(liaison.get("source")), []).append(liaison)
    return sortantes


def _etiquette(liaison: dict[str, Any]) -> str:
    return str((liaison.get("data") or {}).get("label") or "")[:LIBELLE_MAX]


def en_texte(graphe: dict[str, Any] | None) -> str:
    """Un arbre lisible : chaque nœud une fois, ses sorties dessous. Un nœud déjà montré est rappelé par « (voir plus haut) »."""
    graphe = graphe or {}
    noeuds = {str(n.get("id")): n for n in graphe.get("nodes") or []}
    if not noeuds:
        return "(empty graph)"
    sortantes = _liaisons_de(graphe)
    cibles = {str(e.get("target")) for e in graphe.get("edges") or []}
    departs = [i for i, n in noeuds.items() if n.get("type") == "startCall"]
    racines = departs + [i for i in noeuds if i not in cibles and i not in departs] or list(noeuds)[:1]
    lignes = [f"{len(noeuds)} node(s), {len(graphe.get('edges') or [])} link(s)"]
    montres: set[str] = set()

    def ligne_du_noeud(identifiant: str) -> str:
        noeud = noeuds[identifiant]
        return f"[{identifiant}] {noeud.get('type', '?')} \"{_nom(noeud)}\""

    def descendre(identifiant: str, marge: str) -> None:
        montres.add(identifiant)
        for rang, liaison in enumerate(sortantes.get(identifiant, [])):
            derniere = rang == len(sortantes[identifiant]) - 1
            cible = str(liaison.get("target"))
            branche = "`-" if derniere else "|-"
            etiquette = f"({_etiquette(liaison)}) " if _etiquette(liaison) else ""
            if cible not in noeuds:
                lignes.append(f"{marge}{branche}{etiquette}-> [{cible}] (missing node)")
            elif cible in montres:
                lignes.append(f"{marge}{branche}{etiquette}-> [{cible}] (see above)")
            else:
                lignes.append(f"{marge}{branche}{etiquette}-> {ligne_du_noeud(cible)}")
                descendre(cible, marge + ("   " if derniere else "|  "))

    for racine in racines:
        if racine in montres:
            continue
        lignes.append(ligne_du_noeud(racine))
        descendre(racine, "")
    seuls = [i for i in noeuds if i not in montres]
    if seuls:
        lignes.append("Not reachable from the start:")
        lignes.extend(f"  {ligne_du_noeud(i)}" for i in seuls)
    return "\n".join(lignes)


def _mermaid_texte(texte: str) -> str:
    return re.sub(r'["\[\]{}|<>]', " ", texte).strip() or "-"


def _mermaid_id(identifiant: str) -> str:
    return "n" + re.sub(r"\W", "_", identifiant)


def en_mermaid(graphe: dict[str, Any] | None) -> str:
    graphe = graphe or {}
    lignes = ["flowchart TD"]
    for noeud in graphe.get("nodes") or []:
        identifiant = str(noeud.get("id"))
        lignes.append(f'    {_mermaid_id(identifiant)}["{_mermaid_texte(str(noeud.get("type", "?")))}: {_mermaid_texte(_nom(noeud))}"]')
    for liaison in graphe.get("edges") or []:
        source, cible = _mermaid_id(str(liaison.get("source"))), _mermaid_id(str(liaison.get("target")))
        etiquette = _etiquette(liaison)
        lignes.append(f"    {source} -->|{_mermaid_texte(etiquette)}| {cible}" if etiquette else f"    {source} --> {cible}")
    return "\n".join(lignes)
