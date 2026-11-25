"""[.mark] Lot 7b-C3 : le fichier de secours de la réservation est une feuille. La base le lit comme le moteur ; il n'importe rien de ``services.reservation`` (sinon la base
importerait le moteur, et le moteur la base)."""

from __future__ import annotations

import ast

from api.outils import inventaire_rustines as I

CHEMIN = "services/reservation/textes_de_secours.py"


def _imports(source: str) -> list[str]:
    modules: list[str] = []
    for noeud in ast.walk(ast.parse(source)):
        if isinstance(noeud, ast.ImportFrom) and noeud.module:
            modules += [noeud.module] + [f"{noeud.module}.{a.name}" for a in noeud.names]
        elif isinstance(noeud, ast.Import):
            modules += [a.name for a in noeud.names]
    return modules


def test_le_fichier_de_secours_de_la_reservation_n_importe_rien_de_la_reservation():
    modules = _imports((I.RACINE_API / CHEMIN).read_text(encoding="utf-8"))
    assert not [m for m in modules if m.startswith("api.services.reservation")], modules
    assert all(m.startswith(("api.services.mots_dits", "__future__", "collections", "typing")) for m in modules), modules


def test_le_test_voit_un_import_du_moteur():
    assert [m for m in _imports("from api.services.reservation import moteur") if m.startswith("api.services.reservation")]
