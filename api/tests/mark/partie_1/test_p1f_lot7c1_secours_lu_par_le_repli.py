"""[.mark] Lot 7b-C1 (point 3 de l'audit C0), puis C7 B9 : plus aucun catalogue de secours, plus aucun lecteur.

Un texte de secours était une phrase que le code ne disait plus (lot 7b-C5) et qui ne revenait jamais au modèle ; C7 a traduit chaque information en fait (statut, manque,
faits bruts), puis B9 supprime les catalogues (décision d'Evan 25/11 8 h 45 : le code ne compose aucune phrase ; 10 h : « pas juste une suppression »). Aucun fichier
``textes_de_secours*.py`` ne reste ; ``phrases_du_manque.py`` ne garde que la valeur fermée de ce qui manque (``Manque``, ``valeur_du_manque``…), jamais une phrase.
"""

from __future__ import annotations

import ast
import re

from api.outils import inventaire_rustines as I

CATALOGUE = re.compile(r"(?:^|/)(?:textes_de_secours[^/]*|phrases_du_manque)\.py$")
SECOURS = re.compile(r"(?:^|/)textes_de_secours[^/]*\.py$")
# la valeur fermée de ce qui manque : pas un texte (C5 : la relance du modèle la lit)
LIBRES = frozenset({"Manque", "PORTEES_PAR_UNE_QUESTION", "valeur_du_manque", "VALEURS_DU_MANQUE"})


def _chemin(f) -> str:
    return str(f.relative_to(I.RACINE_API)).replace("\\", "/")


def _catalogues() -> list[str]:
    return sorted(_chemin(f) for d in ("services", "db") for f in (I.RACINE_API / d).rglob("*.py") if CATALOGUE.search(_chemin(f)))


def _module(chemin: str) -> str:
    return "api." + chemin[:-3].replace("/", ".")


def importeurs_des_textes() -> set[tuple[str, str, str]]:
    """Chaque ``(catalogue, importeur, nom)`` du code hors tests : ``nom`` est le nom importé, ou ``*`` quand le module entier est importé."""
    modules = {_module(c): c for c in _catalogues()}
    trouves: set[tuple[str, str, str]] = set()
    for d in ("services", "db", "routes", "tasks", "mcp_server", "utils"):
        if not (I.RACINE_API / d).exists():
            continue
        for f in (I.RACINE_API / d).rglob("*.py"):
            importeur = _chemin(f)
            for noeud in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                if isinstance(noeud, ast.ImportFrom) and noeud.module:
                    for alias in noeud.names:
                        direct = modules.get(noeud.module)
                        if direct and alias.name not in LIBRES:
                            trouves.add((direct, importeur, alias.name))
                        entier = modules.get(f"{noeud.module}.{alias.name}")
                        if entier:
                            trouves.add((entier, importeur, "*"))
                elif isinstance(noeud, ast.Import):
                    trouves.update((modules[a.name], importeur, "*") for a in noeud.names if a.name in modules)
    return trouves


def _noms_des_catalogues_du_manque() -> dict[str, set[str]]:
    """Les noms de haut niveau de chaque ``phrases_du_manque.py`` hors des valeurs fermées libres (et des imports)."""
    noms: dict[str, set[str]] = {}
    for c in _catalogues():
        if SECOURS.search(c):
            continue
        arbre = ast.parse((I.RACINE_API / c).read_text(encoding="utf-8"))
        definis = {n.name for n in arbre.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        definis |= {t.id for n in arbre.body if isinstance(n, (ast.Assign, ast.AnnAssign)) for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)}
        noms[c] = definis - LIBRES
    return noms


def test_aucun_module_ne_lit_un_catalogue_de_secours():
    assert not sorted(importeurs_des_textes()), "un texte de secours est encore lu : " + "; ".join(map(str, sorted(importeurs_des_textes())))


def test_aucun_catalogue_de_secours_ne_reste():
    assert not [c for c in _catalogues() if SECOURS.search(c)], [c for c in _catalogues() if SECOURS.search(c)]


def test_le_catalogue_du_manque_ne_garde_que_la_valeur_fermee():
    """``PHRASES_DU_MANQUE`` et ``phrase_du_manque`` sont partis ; seule la valeur fermée reste (aucune phrase)."""
    restes = {c: sorted(n) for c, n in _noms_des_catalogues_du_manque().items() if n}
    assert not restes, restes
