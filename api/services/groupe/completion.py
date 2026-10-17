"""[.mark] Lot 2 d'orchestrateur-trois-cerveaux (D5, D6) : compléter les agents d'un groupe.

Les groupes existants (créés avant l'étape de retour et les deux sorties) n'ont ni l'une ni les
autres. Ce module ajoute, **sans jamais rien retirer ni réécrire** :

- à un **collègue** (``agent_principal_id``) qui a une étape « retour au principal » mais aucun
  nœud de fin : un nœud de fin ``Fin``, relié depuis chaque étape qui mène au retour (la deuxième
  sortie : clore l'appel) ;
- à un **accueil** (``agents_specialises`` non vide) sans étape de retour : une étape de retour
  (``etape_de_retour``), reliée vers chaque nœud de fin de l'accueil, qui porte les mêmes outils de
  passation que son étape de qualification (pour pouvoir repasser la main).

Les étapes posées portent le prompt ``À rédiger avec Evan.`` (jamais un prompt rédigé seul) et leurs
portes la même condition : tant que ce texte n'est pas remplacé, l'étape de retour n'est pas choisie
(``etape_de_retour_du_graphe``) et le nœud de fin n'est jamais pris par un modèle qui n'a pas de raison
de le faire : un groupe complété se comporte comme avant. La fonction est pure (aucune base),
idempotente (rejouée, elle ne rajoute rien) et rend la liste de ce qu'elle a ajouté.
"""

from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping

from api.services.groupe.passations import (
    A_REDIGER,
    MARQUEUR_ETAPE_DE_RETOUR,
    MARQUEUR_RETOUR,
)

NOM_DE_LA_FIN = "Fin"
NOM_DE_LA_REPRISE = "Reprise"


def _donnees(noeud: Mapping[str, Any]) -> Mapping[str, Any]:
    d = noeud.get("data")
    return d if isinstance(d, Mapping) else {}


def _id_libre(noeuds: Iterable[Mapping[str, Any]]) -> str:
    """Le plus petit entier au-dessus des identifiants numériques du graphe (les gabarits en
    numérotent leurs nœuds), sinon un identifiant dérivé du nombre de nœuds."""
    pris = {str(n.get("id")) for n in noeuds}
    numeriques = [int(i) for i in pris if i.isdigit()]
    candidat = (max(numeriques) + 1) if numeriques else len(pris) + 1
    while str(candidat) in pris:
        candidat += 1
    return str(candidat)


def _position_sous(noeuds: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    """Une position en dessous du nœud le plus bas du graphe, alignée sur le premier."""
    hauts = [
        (n.get("position") or {}) for n in noeuds if isinstance(n.get("position"), Mapping)
    ]
    if not hauts:
        return {"x": 175, "y": 60}
    return {
        "x": hauts[0].get("x", 175),
        "y": max(float(p.get("y", 0)) for p in hauts) + 200,
    }


def _arete(graphe: Mapping[str, Any], source: str, cible: str, nom: str) -> dict:
    """Une porte de ``source`` vers ``cible``. Le nom d'une porte est unique dans son étape (c'est le
    nom de la fonction que le modèle appelle) : un nom déjà pris reçoit un numéro."""
    pris = {
        str((a.get("data") or {}).get("label") or "").strip().casefold()
        for a in graphe.get("edges") or []
        if isinstance(a, dict) and str(a.get("source")) == source
    }
    libelle, n = nom, 2
    while libelle.strip().casefold() in pris:
        libelle, n = f"{nom} {n}", n + 1
    return {
        "id": f"{source}-{cible}",
        "source": source,
        "target": cible,
        "data": {"label": libelle, "condition": A_REDIGER},
    }


def completer_un_collegue(definition: Mapping[str, Any] | None) -> tuple[dict, list[str]]:
    """Le graphe d'un collègue avec son nœud de fin, s'il lui manque. Sans étape « retour au
    principal », ou avec déjà un nœud de fin : rien."""
    graphe = copy.deepcopy(dict(definition or {}))
    noeuds = [n for n in graphe.get("nodes") or [] if isinstance(n, dict)]
    retours = [n for n in noeuds if _donnees(n).get(MARQUEUR_RETOUR) is True]
    if not retours or any(n.get("type") == "endCall" for n in noeuds):
        return graphe, []
    ids_retours = {str(n.get("id")) for n in retours}
    sources = []
    for arete in graphe.get("edges") or []:
        if isinstance(arete, dict) and str(arete.get("target")) in ids_retours:
            source = str(arete.get("source"))
            if source not in ids_retours and source not in sources:
                sources.append(source)
    if not sources:
        return graphe, []
    identifiant = _id_libre(noeuds)
    graphe.setdefault("nodes", []).append(
        {
            "id": identifiant,
            "type": "endCall",
            "position": _position_sous(noeuds),
            "data": {
                "name": NOM_DE_LA_FIN,
                "prompt": A_REDIGER,
                "is_end": True,
                "allow_interrupt": False,
                "add_global_prompt": False,
            },
        }
    )
    graphe.setdefault("edges", [])
    for source in sources:
        graphe["edges"].append(_arete(graphe, source, identifiant, NOM_DE_LA_FIN))
    return graphe, [f"nœud de fin « {NOM_DE_LA_FIN} » relié depuis {len(sources)} étape(s)"]


def completer_un_accueil(
    definition: Mapping[str, Any] | None, outils_de_passation: Iterable[str] = ()
) -> tuple[dict, list[str]]:
    """Le graphe d'un accueil avec son étape de retour, s'il lui en manque une. Elle est reliée
    vers chaque nœud de fin et porte ``outils_de_passation`` (les outils de passation de l'accueil)."""
    graphe = copy.deepcopy(dict(definition or {}))
    noeuds = [n for n in graphe.get("nodes") or [] if isinstance(n, dict)]
    if any(_donnees(n).get(MARQUEUR_ETAPE_DE_RETOUR) is True for n in noeuds):
        return graphe, []
    if not any(n.get("type") == "startCall" for n in noeuds):
        return graphe, []
    identifiant = _id_libre(noeuds)
    donnees: dict[str, Any] = {
        "name": NOM_DE_LA_REPRISE,
        "prompt": A_REDIGER,
        "allow_interrupt": False,
        "add_global_prompt": True,
        MARQUEUR_ETAPE_DE_RETOUR: True,
    }
    outils = [u for u in dict.fromkeys(outils_de_passation) if isinstance(u, str)]
    if outils:
        donnees["tool_uuids"] = outils
    graphe.setdefault("nodes", []).append(
        {
            "id": identifiant,
            "type": "agentNode",
            "position": _position_sous(noeuds),
            "data": donnees,
        }
    )
    graphe.setdefault("edges", [])
    fins = [n for n in noeuds if n.get("type") == "endCall"]
    for fin in fins:
        graphe["edges"].append(
            _arete(
                graphe,
                identifiant,
                str(fin.get("id")),
                str(_donnees(fin).get("name") or NOM_DE_LA_FIN),
            )
        )
    return graphe, [
        f"étape de retour « {NOM_DE_LA_REPRISE} » reliée vers {len(fins)} nœud(s) de fin, "
        f"{len(outils)} outil(s) de passation"
    ]
