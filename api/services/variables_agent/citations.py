"""[.mark] U3 bis (E62) : les variables CITÉES dans les textes d'un agent, et celles que le catalogue ne connaît pas.

Pur : aucune base, rien de levé. Le moteur (``utils/template_renderer``) ne change pas : un texte cite ``{{cle}}`` ou
``{{cle | repli}}``. On lit tous les textes du graphe et des réglages (prompts, première réplique, accueil, contenu d'un
webhook, phrases de patience...) : ce que le moteur rend, le catalogue le connaît ou la publication est refusée.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from api.services.etiquettes_prompt.familles import est_une_etiquette
from api.utils.template_renderer import TEMPLATE_VAR_PATTERN, is_builtin_variable

_MOTIF = re.compile(TEMPLATE_VAR_PATTERN)

# Des familles ouvertes : le moteur lit n'importe quelle clé sous ces racines (contexte de l'appel, résultats extraits).
RACINES_OUVERTES = frozenset({"initial_context", "gathered_context"})


@dataclass(frozen=True)
class Citation:
    cle: str
    champ: str  # chemin lisible du champ qui la cite
    etape: str | None  # nom de l'étape, quand le champ est celui d'une étape
    avec_repli: bool = False


def _parcourir(valeur: Any, chemin: str, etape: str | None):
    if isinstance(valeur, str):
        yield chemin, etape, valeur
    elif isinstance(valeur, dict):
        for k, v in valeur.items():
            yield from _parcourir(v, f"{chemin}.{k}" if chemin else str(k), etape)
    elif isinstance(valeur, list):
        for i, v in enumerate(valeur):
            yield from _parcourir(v, f"{chemin}[{i}]", etape)


def textes_de(workflow_json: dict | None, configurations: dict | None):
    """(chemin, nom de l'étape, texte) de tous les textes de l'agent."""
    for noeud in (workflow_json or {}).get("nodes", []) or []:
        if not isinstance(noeud, dict):
            continue
        donnees = noeud.get("data") or {}
        nom = donnees.get("name") if isinstance(donnees, dict) else None
        yield from _parcourir(donnees, f"nodes[{noeud.get('id')}]", nom if isinstance(nom, str) else None)
    yield from _parcourir(configurations or {}, "configurations", None)


def cles_citees(texte: str) -> list[tuple[str, bool]]:
    """Les clés d'un texte, avec « a un repli ». Les variables du moteur (heure, jour) sont écartées."""
    sortie = []
    for m in _MOTIF.finditer(texte or ""):
        cle = m.group(1).strip()
        if is_builtin_variable(cle) or est_une_etiquette(cle):  # lot 8 : une étiquette d'objet a son propre contrôle
            continue
        sortie.append((cle, m.group(2) is not None))
    return sortie


def citations_de(workflow_json: dict | None, configurations: dict | None) -> list[Citation]:
    sortie: list[Citation] = []
    for chemin, etape, texte in textes_de(workflow_json, configurations):
        for cle, repli in cles_citees(texte):
            sortie.append(Citation(cle=cle, champ=chemin, etape=etape, avec_repli=repli))
    return sortie


def est_connue(cle: str, connues: set[str] | frozenset[str]) -> bool:
    racine = cle.split(".")[0]
    return cle in connues or racine in RACINES_OUVERTES or racine in connues


def inconnues(citations: list[Citation], connues: set[str] | frozenset[str]) -> list[Citation]:
    return [c for c in citations if not est_connue(c.cle, connues)]
