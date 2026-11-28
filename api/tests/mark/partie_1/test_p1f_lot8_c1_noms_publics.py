"""[.mark] Lot 8, 8c-1 (76) : un nom lu par un autre module est public. Aucun module de ``services/`` ou de ``db/`` n'importe un nom privé (``_nom``)
d'un autre module de la liste ci-dessous : ils ont été rendus publics, leurs lecteurs suivis."""

from __future__ import annotations

import ast
from pathlib import Path

RACINE_API = Path(__file__).resolve().parents[3]
NOMS_RENDUS_PUBLICS = {"_quand_dit", "_heure_dite", "_avec", "_racines", "_groupes_a_remplir", "_option_dite", "_un_seul_candidat"}


def _imports_prives() -> list[str]:
    trouves: list[str] = []
    for dossier in ("services", "db"):
        for fichier in sorted((RACINE_API / dossier).rglob("*.py")):
            for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
                if isinstance(noeud, ast.ImportFrom):
                    for alias in noeud.names:
                        if alias.name in NOMS_RENDUS_PUBLICS:
                            trouves.append(f"{fichier.relative_to(RACINE_API).as_posix()}:{noeud.lineno} importe {alias.name}")
    return trouves


def test_aucun_module_n_importe_un_nom_rendu_public_sous_son_ancien_nom():
    assert _imports_prives() == []
