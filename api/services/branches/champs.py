"""[.mark] Partie 3, SA-L3c (05 § 12) : fusionner et mettre à jour, CHAMP PAR CHAMP (fusion à trois, pure, sans base).

Trois états d'un agent : la **base** (la version d'où la branche est partie), la **source** (ce qu'on ramène) et la **cible** (ce qui
reçoit). Chaque champ est comparé aux trois :

| La source | La cible | Statut | Résultat sans choix |
|---|---|---|---|
| = cible | | ``identique`` | rien à faire |
| change | = base | ``reprise`` | la source (seule à avoir bougé) |
| = base | change | ``gardee`` | la cible (seule à avoir bougé) |
| change | change autrement | ``conflit`` | **aucun** : la personne choisit à l'écran, champ par champ |

Jamais « le plus récent gagne » en silence : un conflit sans choix refuse la fusion.

Les champs : une étape (son entrée sans le prompt), le prompt de chaque étape, chaque liaison, chaque réglage (premier niveau de
``workflow_configurations``), chaque variable de contexte. Une étape présente aux trois endroits a son prompt à part ; une étape
ajoutée ou retirée quelque part est un seul champ (avec son prompt), pour qu'un prompt ne survive jamais à son étape. Un
déplacement sur le canevas n'est pas un changement.

⛔ Les valeurs rendues à l'écran sont masquées et raccourcies (``lisible``) : aucune clé de réglage ne sort en clair.
"""

from __future__ import annotations

import copy
import json
from typing import Any

ABSENT = {"__absent__": True}  # marque « ce champ n'existe pas de ce côté » (jamais une valeur réelle)
CLES_SECRETES = ("key", "token", "secret", "password", "mot_de_passe", "authorization")
CLE_PHRASES = "phrases_regles"
LONGUEUR_LISIBLE = 240
LONGUEUR_PROMPT = 4000

FAMILLES = ("graphe", "prompts", "reglages", "phrases", "variables")


def _canonique(valeur: Any) -> str:
    return json.dumps(valeur, sort_keys=True, ensure_ascii=False, default=str)


def _sans_position(noeud: dict[str, Any]) -> dict[str, Any]:
    reste = {k: copy.deepcopy(v) for k, v in noeud.items() if k not in ("position", "positionAbsolute", "selected", "dragging", "measured", "width", "height")}
    return reste


def _identifiant_de_liaison(liaison: dict[str, Any]) -> str:
    return str(liaison.get("id") or f"{liaison.get('source')}->{liaison.get('target')}")


def _noeuds(definition: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {str(n.get("id")): n for n in ((definition or {}).get("nodes") or []) if isinstance(n, dict) and n.get("id") is not None}


def _liaisons(definition: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {_identifiant_de_liaison(e): e for e in ((definition or {}).get("edges") or []) if isinstance(e, dict)}


class Etat:
    """Un côté de la fusion : son graphe, ses réglages, ses variables."""

    def __init__(self, graphe: dict[str, Any] | None, reglages: dict[str, Any] | None, variables: dict[str, Any] | None):
        self.graphe = copy.deepcopy(graphe) if isinstance(graphe, dict) else {"nodes": [], "edges": []}
        self.reglages = copy.deepcopy(reglages) if isinstance(reglages, dict) else {}
        self.variables = copy.deepcopy(variables) if isinstance(variables, dict) else {}


def aplatir(etat: Etat, communes: set[str]) -> dict[str, Any]:
    """Tous les champs d'un côté : ``{clé: valeur}`` ; une clé absente est un champ qui n'existe pas de ce côté."""
    champs: dict[str, Any] = {}
    for identifiant, noeud in _noeuds(etat.graphe).items():
        entree = _sans_position(noeud)
        if identifiant in communes:
            donnees = dict(entree.get("data") or {})
            prompt = donnees.pop("prompt", None)
            entree["data"] = donnees
            champs[f"etape:{identifiant}"] = entree
            if prompt is not None:
                champs[f"prompt:{identifiant}"] = prompt
        else:
            champs[f"etape:{identifiant}"] = entree
    for identifiant, liaison in _liaisons(etat.graphe).items():
        champs[f"liaison:{identifiant}"] = copy.deepcopy(liaison)
    for cle, valeur in etat.reglages.items():
        champs[f"{'phrases' if cle == CLE_PHRASES else 'reglage'}:{cle}"] = copy.deepcopy(valeur)
    for cle, valeur in etat.variables.items():
        champs[f"variable:{cle}"] = copy.deepcopy(valeur)
    return champs


def famille_de(cle: str) -> str:
    genre = cle.split(":", 1)[0]
    return {"etape": "graphe", "liaison": "graphe", "prompt": "prompts", "reglage": "reglages", "phrases": "phrases", "variable": "variables"}[genre]


def _masquer(valeur: Any, cle_parente: str = "") -> Any:
    if isinstance(valeur, dict):
        return {k: _masquer(v, k) for k, v in valeur.items()}
    if isinstance(valeur, list):
        return [_masquer(v, cle_parente) for v in valeur]
    if isinstance(valeur, str) and any(m in cle_parente.lower() for m in CLES_SECRETES):
        return "••••"
    return valeur


def lisible(cle: str, valeur: Any) -> str | None:
    """Ce que l'écran montre d'un champ : ``None`` si absent. Les prompts en entier (bornés), le reste masqué et raccourci."""
    if valeur == ABSENT:
        return None
    if cle.startswith("prompt:"):
        texte = str(valeur)
        return texte if len(texte) <= LONGUEUR_PROMPT else texte[:LONGUEUR_PROMPT] + "…"
    if cle.startswith("etape:") and isinstance(valeur, dict):
        valeur = {"type": valeur.get("type"), **(valeur.get("data") or {})}
        if isinstance(valeur.get("prompt"), str):
            valeur["prompt"] = valeur["prompt"][:LONGUEUR_LISIBLE]
    texte = _canonique(_masquer(valeur)) if not isinstance(valeur, str) else valeur
    return texte if len(texte) <= LONGUEUR_LISIBLE else texte[:LONGUEUR_LISIBLE] + "…"


def _libelle(cle: str, base: dict[str, Any], source: dict[str, Any], cible: dict[str, Any]) -> str:
    genre, _, reste = cle.partition(":")
    if genre in ("etape", "prompt"):
        for cote in (cible, source, base):
            entree = cote.get(f"etape:{reste}")
            if isinstance(entree, dict) and (entree.get("data") or {}).get("name"):
                return str(entree["data"]["name"])
        return reste
    if genre == "liaison":
        for cote in (cible, source, base):
            entree = cote.get(cle)
            if isinstance(entree, dict):
                etiquette = (entree.get("data") or {}).get("label")
                return str(etiquette) if etiquette else f"{entree.get('source')} → {entree.get('target')}"
    return reste


def comparer(base: Etat, source: Etat, cible: Etat) -> list[dict[str, Any]]:
    """Les champs qui diffèrent quelque part, avec leur statut. Un champ identique des deux côtés n'est pas listé."""
    ids = [set(_noeuds(e.graphe)) for e in (base, source, cible)]
    communes = ids[0] & ids[1] & ids[2]
    b, s, c = aplatir(base, communes), aplatir(source, communes), aplatir(cible, communes)
    lignes = []
    for cle in sorted(set(b) | set(s) | set(c), key=lambda k: (famille_de(k), k)):
        vb, vs, vc = b.get(cle, ABSENT), s.get(cle, ABSENT), c.get(cle, ABSENT)
        if _canonique(vs) == _canonique(vc):
            continue
        if _canonique(vc) == _canonique(vb):
            statut = "reprise"
        elif _canonique(vs) == _canonique(vb):
            statut = "gardee"
        else:
            statut = "conflit"
        lignes.append(
            {
                "cle": cle,
                "famille": famille_de(cle),
                "libelle": _libelle(cle, b, s, c),
                "statut": statut,
                "avant": lisible(cle, vb),
                "source": lisible(cle, vs),
                "cible": lisible(cle, vc),
            }
        )
    return lignes


class ChoixIncomplet(ValueError):
    """Un conflit sans choix, ou un choix sur un champ inconnu."""


def resoudre(base: Etat, source: Etat, cible: Etat, choix: dict[str, str]) -> Etat:
    """L'état fusionné. ``choix`` : ``{clé: "source" | "cible"}``, obligatoire pour chaque conflit, permis pour les autres champs."""
    lignes = {ligne["cle"]: ligne for ligne in comparer(base, source, cible)}
    inconnus = [cle for cle in choix if cle not in lignes]
    if inconnus:
        raise ChoixIncomplet(f"Unknown field(s): {sorted(inconnus)[:5]}")
    if any(v not in ("source", "cible") for v in choix.values()):
        raise ChoixIncomplet("A choice is 'source' or 'cible'")
    manquants = [cle for cle, ligne in lignes.items() if ligne["statut"] == "conflit" and cle not in choix]
    if manquants:
        raise ChoixIncomplet(f"Every conflict needs a choice: {len(manquants)} left")

    ids = [set(_noeuds(e.graphe)) for e in (base, source, cible)]
    communes = ids[0] & ids[1] & ids[2]
    s, c = aplatir(source, communes), aplatir(cible, communes)
    retenu: dict[str, Any] = dict(c)  # on part de la cible
    for cle, ligne in lignes.items():
        cote = choix.get(cle) or ("source" if ligne["statut"] == "reprise" else "cible")
        valeur = (s if cote == "source" else c).get(cle, ABSENT)
        if valeur == ABSENT:
            retenu.pop(cle, None)
        else:
            retenu[cle] = valeur
    return _reconstruire(retenu, communes, source, cible, base)


def _reconstruire(retenu: dict[str, Any], communes: set[str], source: Etat, cible: Etat, base: Etat) -> Etat:
    positions: dict[str, Any] = {}
    for etat in (cible, source, base):  # la position de la cible d'abord : un déplacement n'est jamais perdu
        for identifiant, noeud in _noeuds(etat.graphe).items():
            positions.setdefault(identifiant, noeud.get("position"))
    noeuds = []
    dans_la_cible = [str(n.get("id")) for n in (cible.graphe.get("nodes") or []) if isinstance(n, dict)]
    ordre = dans_la_cible + sorted(
        {cle.split(":", 1)[1] for cle in retenu if cle.startswith("etape:")} - set(dans_la_cible)
    )
    for identifiant in ordre:
        entree = retenu.get(f"etape:{identifiant}")
        if entree is None:
            continue
        noeud = copy.deepcopy(entree)
        if identifiant in communes:
            donnees = dict(noeud.get("data") or {})
            prompt = retenu.get(f"prompt:{identifiant}")
            if prompt is not None:
                donnees["prompt"] = prompt
            noeud["data"] = donnees
        if positions.get(identifiant) is not None:
            noeud["position"] = copy.deepcopy(positions[identifiant])
        noeuds.append(noeud)
    liaisons = [copy.deepcopy(v) for k, v in retenu.items() if k.startswith("liaison:")]
    reglages = {k.split(":", 1)[1]: copy.deepcopy(v) for k, v in retenu.items() if k.startswith(("reglage:", "phrases:"))}
    variables = {k.split(":", 1)[1]: copy.deepcopy(v) for k, v in retenu.items() if k.startswith("variable:")}
    graphe = {**{k: copy.deepcopy(v) for k, v in cible.graphe.items() if k not in ("nodes", "edges")}, "nodes": noeuds, "edges": liaisons}
    return Etat(graphe, reglages, variables)


def problemes(graphe: dict[str, Any]) -> list[dict[str, Any]]:
    """Ce qui rendrait le graphe fusionné incohérent (liaison vers une étape retirée, identifiant en double)."""
    sortie = []
    ids = [str(n.get("id")) for n in graphe.get("nodes") or [] if isinstance(n, dict)]
    for doublon in sorted({i for i in ids if ids.count(i) > 1}):
        sortie.append({"code": "etape_en_double", "cle": f"etape:{doublon}"})
    presents = set(ids)
    for liaison in graphe.get("edges") or []:
        manque = [x for x in (liaison.get("source"), liaison.get("target")) if str(x) not in presents]
        if manque:
            sortie.append({"code": "liaison_orpheline", "cle": f"liaison:{_identifiant_de_liaison(liaison)}"})
    return sortie
