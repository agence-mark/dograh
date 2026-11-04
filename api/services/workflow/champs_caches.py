"""[.mark] RA-A (R1, audit du 04/11) : les réglages d'étape que le code du builder ne porte pas.

Le code lu par ``get_workflow_code`` ne montre que les champs du formulaire généré. Les champs
``spec_exclude`` du DTO (``retour_au_principal``, ``travail_de_fond``, ``fins``...) n'y sont pas, donc
``save_workflow`` les perdait à chaque aller-retour. Ici, après ``reconcile_positions``, on les reprend
du brouillon précédent : par (type, nom) pour les étapes, par (source, cible, libellé) pour les liaisons.

Une étape ou une liaison supprimée dans le code reste supprimée (on ne ressuscite rien : on ne copie
que dans ce que le code a posé). Un champ visible du formulaire n'est jamais repris : c'est le code qui
fait foi. Un champ caché que le code poserait quand même l'emporte aussi.
"""

from __future__ import annotations

import copy
from typing import Any

from api.services.workflow.dto import EdgeDataDTO, get_node_data_model
from api.services.workflow.node_specs import all_specs


def _champs_visibles() -> dict[str, set[str]]:
    return {s.name: {p.name for p in (s.properties or [])} for s in all_specs()}


def champs_caches(type_noeud: str, visibles: dict[str, set[str]] | None = None) -> set[str]:
    """Champs du DTO de ce type que le formulaire généré (donc le code) ne porte pas."""
    modele = get_node_data_model(type_noeud)
    if modele is None:
        return set()
    visibles = visibles if visibles is not None else _champs_visibles()
    return set(modele.model_fields) - visibles.get(type_noeud, set())


def _cle(noeud: dict[str, Any]) -> tuple[str, str]:
    return (noeud.get("type") or "", ((noeud.get("data") or {}).get("name") or "").strip())


def fusionner_champs_caches(
    nouveau: dict[str, Any], precedent: dict[str, Any] | None
) -> dict[str, Any]:
    """Reporte dans ``nouveau`` les champs cachés de ``precedent`` (modifie et renvoie ``nouveau``)."""
    if not precedent:
        return nouveau
    visibles = _champs_visibles()

    # Étapes : (type, nom) ; à égalité de clé, la n-ième occurrence répond à la n-ième.
    anciennes: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for n in precedent.get("nodes") or []:
        anciennes.setdefault(_cle(n), []).append(n)
    curseur: dict[tuple[str, str], int] = {}
    ancien_id_de: dict[str, str] = {}  # id du nouveau nœud -> id du nœud précédent
    for noeud in nouveau.get("nodes") or []:
        cle = _cle(noeud)
        if not cle[1]:
            continue  # sans nom, rien ne dit de quelle étape il s'agit : on ne devine pas
        rang = curseur.get(cle, 0)
        candidats = anciennes.get(cle, [])
        if rang >= len(candidats):
            continue
        curseur[cle] = rang + 1
        ancien = candidats[rang]
        ancien_id_de[noeud["id"]] = ancien["id"]
        donnees = noeud.setdefault("data", {})
        for champ in champs_caches(cle[0], visibles):
            valeur = (ancien.get("data") or {}).get(champ)
            if valeur is not None and champ not in donnees:
                donnees[champ] = copy.deepcopy(valeur)

    # Liaisons : (source, cible, libellé) lus dans le graphe précédent.
    anciennes_liaisons: dict[tuple[str, str, str], dict[str, Any]] = {}
    for e in precedent.get("edges") or []:
        anciennes_liaisons.setdefault(
            (e["source"], e["target"], (e.get("data") or {}).get("label") or ""), e
        )
    caches_liaison = set(EdgeDataDTO.model_fields) - {"label", "condition"}
    for liaison in nouveau.get("edges") or []:
        source = ancien_id_de.get(liaison["source"])
        cible = ancien_id_de.get(liaison["target"])
        if source is None or cible is None:
            continue
        ancienne = anciennes_liaisons.get((source, cible, (liaison.get("data") or {}).get("label") or ""))
        if ancienne is None:
            continue
        donnees = liaison.setdefault("data", {})
        for champ in caches_liaison:
            valeur = (ancienne.get("data") or {}).get(champ)
            if valeur is not None and champ not in donnees:
                donnees[champ] = copy.deepcopy(valeur)
    return nouveau
